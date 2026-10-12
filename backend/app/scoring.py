from datetime import date
from difflib import SequenceMatcher
from .calendar import BusinessCalendar

PROFILES = {
    "ledger_razorpay": {"amount": 0.60, "date": 0.25, "method": 0.10, "name": 0.05},
    "settlement_bank": {
        "amount": 0.50,
        "reference": 0.25,
        "date": 0.15,
        "direction": 0.07,
        "name": 0.03,
    },
    "direct_bank": {"amount": 0.65, "date": 0.25, "direction": 0.07, "name": 0.03},
}


def comparable(left, right):
    if right.get("event_type"):
        payment_ids = [r["id"] for r in right.get("members", [right])]
        return [
            ("payment_id", "members.id" if right.get("members") else "id", payment_ids),
            ("order_id", "order_id", [right.get("order_id")]),
        ]
    return [("reference", "reference", [right.get("reference")])]


def shared(left, right):
    return [
        (key, field)
        for key, field, values in comparable(left, right)
        if left.get(key) and left[key] in values
    ]


def contradictory(left, right):
    return [
        key
        for key, _, values in comparable(left, right)
        if left.get(key) and any(values) and left[key] not in values
    ]


def candidates(left, rights, profile, window=7):
    out = []
    for r in rights:
        if profile == "ledger_razorpay" and r.get("event_type") != "payment":
            continue
        if profile != "ledger_razorpay" and r.get("direction") != "credit":
            continue
        days = abs(
            (date.fromisoformat(r["date"]) - date.fromisoformat(left["date"])).days
        )
        amount_diff = abs(left["amount"] - r["amount"])
        if shared(left, r) or (
            days <= window and amount_diff <= max(100, left["amount"] // 5)
        ):
            out.append(r)
    return out


def score(left, right, profile, calendar=None):
    calendar = calendar or BusinessCalendar()
    weights = PROFILES[profile]
    a, b = left["amount"], right["amount"]
    delta = b - a
    days = (date.fromisoformat(right["date"]) - date.fromisoformat(left["date"])).days
    business = calendar.difference(
        date.fromisoformat(left["date"]), date.fromisoformat(right["date"])
    )
    values = {
        "amount": max(0.0, 1 - abs(delta) / max(abs(a), 1)),
        "date": max(0.0, 1 - abs(business) / 8),
    }
    if profile == "ledger_razorpay":
        values["method"] = (
            (1.0 if left.get("method") == right.get("method") else 0.0)
            if left.get("method") and right.get("method")
            else None
        )
    else:
        values["direction"] = 1.0 if right.get("direction") == "credit" else 0.0
    values["name"] = (
        SequenceMatcher(
            None, left.get("name", "").lower(), right.get("name", "").lower()
        ).ratio()
        if left.get("name") and right.get("name")
        else None
    )
    if "reference" in weights:
        values["reference"] = (
            float(left["reference"] == right["reference"])
            if left.get("reference") and right.get("reference")
            else None
        )
    available = sum(w for key, w in weights.items() if values.get(key) is not None)
    breakdown = {
        key: {
            "weight": w,
            "value": values.get(key),
            "effective_weight": w / available if values.get(key) is not None else 0,
        }
        for key, w in weights.items()
    }
    result = (
        sum(
            w * values[key] for key, w in weights.items() if values.get(key) is not None
        )
        / available
    )
    return {
        "score": round(result * 100, 2),
        "breakdown": breakdown,
        "difference": delta,
        "relative_difference": round(abs(delta) / max(abs(a), 1), 6),
        "calendar_days": days,
        "business_days": business,
        "shared_references": shared(left, right),
        "contradictions": contradictory(left, right),
        "missing_evidence": [k for k in weights if values.get(k) is None],
    }
