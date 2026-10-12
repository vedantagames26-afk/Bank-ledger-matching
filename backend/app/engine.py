"""Deterministic reconciliation with globally constrained one-to-one allocation."""

from copy import deepcopy
from datetime import date
from scipy.optimize import linear_sum_assignment
import numpy as np
from .calendar import BusinessCalendar
from .scoring import candidates, score, shared, PROFILES

DEFAULT_CONFIG = {
    "settlement_working_days": 2,
    "candidate_window_days": 7,
    "accept_score": 90,
    "ambiguity_margin": 4,
    "holidays": {},
    "weekend_days": [5, 6],
    "method_settlement_days": {},
    "currency": "INR",
    "timezone": "Asia/Kolkata",
    "weights": PROFILES,
}


def case(
    left,
    profile,
    right=None,
    evidence=None,
    alternatives=None,
    status="UNMATCHED",
    reason="No plausible candidate in configured search window",
):
    return {
        "id": profile + ":" + left["row_id"],
        "profile": profile,
        "left": left,
        "right": right,
        "evidence": evidence,
        "alternatives": alternatives or [],
        "status": status,
        "automated_status": status,
        "reason": reason,
        "residual": max(0, left["amount"] - (right["amount"] if right else 0)),
        "recommended_action": "Verify source references and amounts before accepting."
        if status != "MATCHED"
        else "No action required.",
    }


def global_match(lefts, rights, profile, config, calendar):
    if not lefts:
        return []
    index = {r["row_id"]: i for i, r in enumerate(rights)}
    scores = np.full((len(lefts), len(rights) + len(lefts)), -10000.0)
    scores[:, len(rights) :] = 0
    evaluations = []
    for i, l in enumerate(lefts):
        options = []
        current_profile = l.get("_match_profile", profile)
        if l.get("duplicate"):
            evaluations.append([])
            continue
        for r in candidates(
            l, rights, current_profile, config["candidate_window_days"]
        ):
            e = score(l, r, current_profile, calendar)
            option = {"record": r, "evidence": e}
            options.append(option)
            if not r.get("duplicate") and r.get("status") != "failed":
                utility = e["score"] - 55 + (50 if shared(l, r) else 0)
                if (e["contradictions"] or e["difference"] != 0) and not shared(l, r):
                    utility = -1
                scores[i, index[r["row_id"]]] = utility
        evaluations.append(
            sorted(
                options,
                key=lambda o: (
                    bool(o["evidence"]["shared_references"]),
                    o["evidence"]["score"],
                ),
                reverse=True,
            )
        )
    rows, columns = linear_sum_assignment(scores, maximize=True)
    assignments = dict(zip(rows.tolist(), columns.tolist()))
    results = []
    for i, l in enumerate(lefts):
        options = evaluations[i]
        current_profile = l.get("_match_profile", profile)
        j = assignments[i]
        if l.get("duplicate"):
            results.append(
                case(
                    l,
                    current_profile,
                    alternatives=options[:5],
                    status="DUPLICATE",
                    reason="Duplicate source identifier or row; no automatic allocation",
                )
            )
            continue
        if j >= len(rights) or scores[i, j] <= 0:
            status = (
                "FAILED"
                if any(
                    o["record"].get("status") == "failed" and shared(l, o["record"])
                    for o in options
                )
                else "REVIEW"
                if any(
                    (
                        o["evidence"]["shared_references"]
                        or (
                            not o["evidence"]["contradictions"]
                            and o["evidence"]["difference"] == 0
                            and index[o["record"]["row_id"]] not in assignments.values()
                        )
                    )
                    for o in options
                )
                else "UNMATCHED"
            )
            reason = (
                "Related failed payment: no successful collection"
                if status == "FAILED"
                else "Candidates quarantined or allocated to stronger global evidence"
                if options
                else "No plausible candidate in configured search window"
            )
            results.append(
                case(
                    l,
                    current_profile,
                    alternatives=options[:5],
                    status=status,
                    reason=reason,
                )
            )
            continue
        r = rights[j]
        e = score(l, r, current_profile, calendar)
        plausible = [
            o
            for o in options
            if o["record"]["row_id"] != r["row_id"]
            and not o["record"].get("duplicate")
            and o["record"].get("status") != "failed"
            and o["evidence"]["difference"] == 0
            and not o["evidence"]["contradictions"]
        ]
        ambiguous = any(
            o["evidence"]["score"] >= e["score"] - config["ambiguity_margin"]
            and (not e["shared_references"] or o["evidence"]["shared_references"])
            for o in plausible
        )
        status, reason = (
            "MATCHED",
            "Exact financial amount, compatible dates, sufficient evidence and no competing allocation",
        )
        if e["difference"] != 0:
            status, reason = (
                "REVIEW",
                "Unexplained amount difference; reference evidence does not override financial discrepancy",
            )
        elif e["contradictions"]:
            status, reason = "REVIEW", "Contradictory comparable references"
        elif ambiguous:
            status, reason = (
                "REVIEW",
                "Multiple plausible candidates within the evidence margin",
            )
        elif abs(e["business_days"]) > 2:
            status, reason = (
                "DELAYED",
                "Outside configured working-day window; cause is unverified",
            )
        elif e["score"] < config["accept_score"]:
            status, reason = "REVIEW", "Insufficient evidence for automatic acceptance"
        results.append(case(l, current_profile, r, e, options[:5], status, reason))
    return results


def settlement_integrity(settlement, events, calendar, config):
    relevant = [r for r in events if r.get("settlement_id") == settlement["id"]]
    gross = fee = tax = refunds = adjustments = 0
    counted = set()
    problems = []
    payments = []
    for e in relevant:
        if e.get("duplicate") or e["id"] in counted:
            problems.append("Duplicate event quarantined: " + e["row_id"])
            continue
        counted.add(e["id"])
        kind = e["event_type"]
        if e["status"] in ("captured", "processed") and any(
            k not in e for k in ("fee", "tax")
        ):
            problems.append("Missing fee or tax evidence: " + e["row_id"])
        if e.get("on_hold") or e.get("settled") is False:
            problems.append("Held or unsettled event: " + e["row_id"])
            continue
        if kind == "payment" and e["status"] == "captured":
            gross += e["amount"]
            payments.append(e)
            fee += e.get("fee", 0)
            tax += e.get("tax", 0)
        elif kind in ("refund", "reversal") and e["status"] == "processed":
            refunds += e["amount"]
            fee += e.get("fee", 0)
            tax += e.get("tax", 0)
        elif kind == "adjustment" and e["status"] == "processed":
            adjustments += e["amount"]
            fee += e.get("fee", 0)
            tax += e.get("tax", 0)
    computed = gross - fee - tax - refunds + adjustments
    if not relevant:
        problems.append("No constituent events: net calculation cannot be validated")
    if computed != settlement["amount"]:
        problems.append("Calculated net differs from authoritative settlement amount")
    expected = None
    if payments:
        expected = max(
            calendar.add(
                date.fromisoformat(p["date"]),
                config.get("method_settlement_days", {}).get(
                    p.get("method"), config["settlement_working_days"]
                ),
            )
            for p in payments
        ).isoformat()
    delay = (
        calendar.difference(
            date.fromisoformat(expected), date.fromisoformat(settlement["date"])
        )
        if expected
        else None
    )
    return {
        "gross": gross,
        "fees": fee,
        "taxes": tax,
        "refunds": refunds,
        "adjustments": adjustments,
        "calculated_net": computed,
        "authoritative_net": settlement["amount"],
        "integrity_difference": settlement["amount"] - computed,
        "transaction_count": len(relevant),
        "events": relevant,
        "problems": problems,
        "expected_date": expected,
        "settlement_delay_business_days": delay,
    }


def reconcile(datasets, supplied=None):
    config = deepcopy(DEFAULT_CONFIG)
    config.update(supplied or {})
    calendar = BusinessCalendar(
        config["holidays"], tuple(config.get("weekend_days", [5, 6]))
    )
    ledgers, events, settlements, bank = (
        datasets[k]
        for k in (
            "internal_ledger",
            "razorpay_recon",
            "razorpay_settlements",
            "bank_statement",
        )
    )
    results = []
    consumed = set()
    remaining = []
    # Split/partial grouping requires genuine shared order ID, never arbitrary subset sums.
    for l in [r for r in ledgers if r["channel"] == "razorpay"]:
        grouped = [
            r
            for r in events
            if l.get("order_id")
            and r.get("order_id") == l["order_id"]
            and r["event_type"] == "payment"
            and r["status"] == "captured"
            and not r.get("duplicate")
            and abs(
                (date.fromisoformat(r["date"]) - date.fromisoformat(l["date"])).days
            )
            <= config["candidate_window_days"]
        ]
        exclusive = (
            l.get("order_id")
            and sum(x.get("order_id") == l["order_id"] for x in ledgers) == 1
        )
        total = sum(r["amount"] for r in grouped)
        if (
            exclusive
            and not l.get("duplicate")
            and grouped
            and (len(grouped) > 1 or total < l["amount"])
        ):
            group = deepcopy(grouped[0])
            group["amount"] = total
            group["members"] = grouped
            if len(grouped) > 1:
                group["id"] = "allocation:" + l["order_id"]
                group["row_id"] = "allocation:" + l["row_id"]
                group["original"] = {
                    "allocation_type": "computed sum, not an original source row",
                    "member_row_ids": ",".join(r["row_id"] for r in grouped),
                }
                group["date"] = max(r["date"] for r in grouped)
                for field in ("method", "name"):
                    group[field] = (
                        grouped[0].get(field, "")
                        if len({r.get(field, "") for r in grouped}) == 1
                        else ""
                    )
            e = score(l, group, "ledger_razorpay", calendar)
            status = (
                "PARTIAL"
                if total < l["amount"]
                else "MATCHED"
                if total == l["amount"]
                and not e["contradictions"]
                and e["score"] >= config["accept_score"]
                and abs(e["business_days"]) <= 2
                else "REVIEW"
            )
            c = case(
                l,
                "ledger_razorpay",
                group,
                e,
                status=status,
                reason="Shared order supports multiple payment allocations"
                if len(grouped) > 1
                else "Partial collection: residual remains outstanding",
            )
            results.append(c)
            consumed.update(r["row_id"] for r in grouped)
        else:
            remaining.append(l)
    results += global_match(
        remaining,
        [r for r in events if r["row_id"] not in consumed],
        "ledger_razorpay",
        config,
        calendar,
    )
    bank_cases = global_match(
        [{**r, "_match_profile": "settlement_bank"} for r in settlements]
        + [
            {**r, "_match_profile": "direct_bank"}
            for r in ledgers
            if r["channel"] == "direct"
        ],
        bank,
        "settlement_bank",
        config,
        calendar,
    )
    settlement_cases = [c for c in bank_cases if c["profile"] == "settlement_bank"]
    for c in settlement_cases:
        integrity = settlement_integrity(c["left"], events, calendar, config)
        c["settlement"] = integrity
        if (
            c["left"].get("status")
            and c["left"]["status"] != "processed"
            and c["status"] == "MATCHED"
        ):
            c["status"] = c["automated_status"] = "REVIEW"
            c["reason"] = (
                "Settlement status is not processed; bank evidence requires review"
            )
        if integrity["problems"] and c["status"] == "MATCHED":
            c["status"] = c["automated_status"] = "REVIEW"
            c["reason"] = "; ".join(integrity["problems"])
        elif (integrity["settlement_delay_business_days"] or 0) > 0 and c[
            "status"
        ] == "MATCHED":
            c["status"] = c["automated_status"] = "DELAYED"
            c["reason"] = (
                "Settlement later than configured T+2 working-day expectation; cause unverified"
            )
    claimed_bank = {c["right"]["row_id"] for c in settlement_cases if c["right"]}
    direct = [c for c in bank_cases if c["profile"] == "direct_bank"]
    results += settlement_cases + direct
    used_events = set(consumed)
    for c in results:
        if c["profile"] == "ledger_razorpay" and c["right"]:
            used_events.add(c["right"]["row_id"])
    claimed_bank.update(c["right"]["row_id"] for c in direct if c["right"])
    statuses = {}
    for c in results:
        c["recommended_action"] = (
            "No action required."
            if c["status"] == "MATCHED"
            else "Verify source references, financial amounts and missing evidence before accepting."
        )
        statuses[c["status"]] = statuses.get(c["status"], 0) + 1
    metrics = {
        "ledger_count": len(ledgers),
        "event_count": len(events),
        "settlement_count": len(settlements),
        "bank_count": len(bank),
        "statuses": statuses,
        "matched": statuses.get("MATCHED", 0),
        "review": sum(
            v
            for k, v in statuses.items()
            if k not in ("MATCHED", "UNMATCHED", "FAILED")
        ),
        "unmatched": statuses.get("UNMATCHED", 0),
        "outstanding_residual": sum(
            c["residual"] for c in results if c["profile"] != "settlement_bank"
        ),
        "expected_settlement": sum(r["amount"] for r in settlements),
        "associated_bank_credits": sum(
            c["right"]["amount"] for c in settlement_cases if c["right"]
        ),
        "confirmed_bank_credits": sum(
            c["right"]["amount"]
            for c in settlement_cases
            if c["right"] and c["status"] == "MATCHED"
        ),
        "unexplained_variance": sum(
            abs(c["evidence"]["difference"]) for c in settlement_cases if c["evidence"]
        ),
    }
    return {
        "config": config,
        "cases": results,
        "metrics": metrics,
        "unmatched_events": [r for r in events if r["row_id"] not in used_events],
        "unmatched_bank": [r for r in bank if r["row_id"] not in claimed_bank],
    }
