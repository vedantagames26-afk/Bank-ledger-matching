import csv
import io
import json


def safe(value):
    text = str(value if value is not None else "")
    if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
        return "'" + text
    return text


def csv_bytes(rows, fields=None):
    fields = fields or (list(rows[0]) if rows else ["id"])
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow(
            {
                k: safe(json.dumps(v) if isinstance(v, (dict, list)) else v)
                for k, v in r.items()
            }
        )
    return output.getvalue().encode("utf-8-sig")


REPORTS = [
    "matched",
    "review",
    "unmatched_ledger",
    "unmatched_events",
    "unmatched_settlements",
    "unmatched_bank",
    "partial",
    "duplicates",
    "variances",
    "audit",
]


def report_rows(run, kind):
    if kind == "unmatched_events":
        return run["unmatched_events"]
    if kind == "unmatched_bank":
        rows = {r["row_id"]: r for r in run["unmatched_bank"]}
        for c in run["cases"]:
            if (
                c["profile"] != "ledger_razorpay"
                and c.get("effective_status", c["status"]) == "UNMATCHED"
                and c["right"]
            ):
                rows[c["right"]["row_id"]] = c["right"]
        return list(rows.values())
    selected = []
    for c in run["cases"]:
        s = c.get("effective_status", c["status"])
        ok = (
            kind == "matched"
            and s == "MATCHED"
            or kind == "review"
            and s in ("REVIEW", "DELAYED")
            or kind == "unmatched_ledger"
            and c["profile"] != "settlement_bank"
            and s in ("UNMATCHED", "FAILED")
            or kind == "unmatched_settlements"
            and c["profile"] == "settlement_bank"
            and s == "UNMATCHED"
            or kind == "partial"
            and s == "PARTIAL"
            or kind == "duplicates"
            and (
                s == "DUPLICATE"
                or c["left"].get("duplicate")
                or any(o["record"].get("duplicate") for o in c["alternatives"])
            )
            or kind == "variances"
            and c["evidence"]
            and c["evidence"]["difference"] != 0
        )
        if ok:
            selected.append(
                {
                    "case_id": c["id"],
                    "profile": c["profile"],
                    "source_id": c["left"]["id"],
                    "source_row": c["left"]["row_id"],
                    "candidate_id": c["right"]["id"] if c["right"] else "",
                    "status": s,
                    "automated_status": c["automated_status"],
                    "source_amount_paise": c["left"]["amount"],
                    "candidate_amount_paise": c["right"]["amount"]
                    if c["right"]
                    else "",
                    "difference_paise": c["evidence"]["difference"]
                    if c["evidence"]
                    else "",
                    "evidence_score": c["evidence"]["score"] if c["evidence"] else "",
                    "residual_paise": c["residual"],
                    "reason": c["reason"],
                    "review": c.get("review"),
                }
            )
    return selected
