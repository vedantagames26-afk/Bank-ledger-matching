"""Strict CSV normalization. Money is represented as integer INR paise."""

import csv
import io
import hashlib
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation

SOURCES = (
    "internal_ledger",
    "razorpay_recon",
    "razorpay_settlements",
    "bank_statement",
)
REQUIRED = {
    "internal_ledger": ["id", "date", "amount", "channel"],
    "razorpay_recon": ["id", "date", "amount", "event_type", "status"],
    "razorpay_settlements": ["id", "date", "amount"],
    "bank_statement": ["id", "value_date", "post_date", "debit", "credit", "balance"],
}
ALIASES = {
    "Value Date": "value_date",
    "Post Date": "post_date",
    "Details": "name",
    "Ref No/Cheque No": "reference",
    "Debit": "debit",
    "Credit": "credit",
    "Balance": "balance",
    "Row ID": "id",
}
MONEY = ("amount", "fee", "tax", "debit", "credit", "balance")
METHODS = {
    "upi": "upi",
    "unified payments interface": "upi",
    "credit card": "card",
    "debit card": "card",
    "card": "card",
    "neft": "bank",
    "imps": "bank",
    "bank": "bank",
    "netbanking": "netbanking",
    "wallet": "wallet",
    "emi": "emi",
}


class ValidationError(ValueError):
    pass


def paise(value):
    try:
        number = Decimal(str(value).replace(",", "").strip())
        if not number.is_finite() or number * 100 != (number * 100).to_integral_value():
            raise ValidationError(
                "Money must be finite with at most two decimal places"
            )
        if abs(number) > Decimal("100000000000"):
            raise ValidationError("Amount exceeds supported limit")
        return int(number * 100)
    except (InvalidOperation, ValueError) as exc:
        raise ValidationError("Invalid money value") from exc


def iso(value):
    try:
        return date.fromisoformat(value.strip()).isoformat()
    except (ValueError, AttributeError) as exc:
        raise ValidationError("Date must be YYYY-MM-DD") from exc


def ingest(source, content, mapping=None):
    if source not in SOURCES:
        raise ValidationError("Unknown source")
    if len(content) > 5 * 1024 * 1024:
        raise ValidationError("CSV exceeds 5 MB limit")
    try:
        text = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text), strict=True)
        headers = reader.fieldnames or []
        raw = list(reader)
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ValidationError("Malformed UTF-8 CSV") from exc
    if len(raw) > 10000:
        raise ValidationError("CSV exceeds 10,000 row limit")
    mapping = mapping or {}
    mapped = [mapping.get(h, ALIASES.get(h, h.strip())) for h in headers]
    if len(set(mapped)) != len(mapped):
        raise ValidationError("Ambiguous column mapping or repeated headers")
    missing = set(REQUIRED[source]) - set(mapped)
    if missing:
        raise ValidationError("Missing columns: " + ", ".join(sorted(missing)))
    records, rejected = [], []
    for idx, original in enumerate(raw, 2):
        try:
            if None in original or any(v is None for v in original.values()):
                raise ValidationError("Column count does not match header")
            r = {mapped[i]: original[h].strip() for i, h in enumerate(headers)}
            if any(
                not r.get(k)
                for k in REQUIRED[source]
                if not (source == "bank_statement" and k in ("debit", "credit"))
            ):
                raise ValidationError("Required value is empty")
            r["row_id"] = f"{source}:{idx}"
            r["original"] = original
            for key in MONEY:
                if key in r:
                    r[key] = (
                        paise(r[key]) if r[key] or key not in ("debit", "credit") else 0
                    )
            for key in ("date", "value_date", "post_date"):
                if r.get(key):
                    r[key] = iso(r[key])
            if source == "bank_statement":
                if (
                    r["debit"] < 0
                    or r["credit"] < 0
                    or bool(r["debit"]) == bool(r["credit"])
                ):
                    raise ValidationError(
                        "Exactly one positive debit or credit is required"
                    )
                r["amount"] = r["credit"] or r["debit"]
                r["direction"] = "credit" if r["credit"] else "debit"
                r["date"] = r["post_date"]
            elif source == "razorpay_recon":
                if r["event_type"] not in (
                    "payment",
                    "refund",
                    "adjustment",
                    "reversal",
                ):
                    raise ValidationError("Unsupported event type")
                if r["status"] not in ("captured", "failed", "processed", "pending"):
                    raise ValidationError("Unsupported event status")
                if r["event_type"] != "adjustment" and r["amount"] < 0:
                    raise ValidationError("Negative event amount")
            elif r["amount"] < 0:
                raise ValidationError("Negative amount")
            if any(r.get(k, 0) < 0 for k in ("fee", "tax")):
                raise ValidationError("Negative fee or tax")
            if source == "internal_ledger" and r["channel"] not in (
                "razorpay",
                "direct",
            ):
                raise ValidationError("Channel must be razorpay or direct")
            if r.get("expected_date"):
                r["expected_date"] = iso(r["expected_date"])
            r["method"] = METHODS.get(r.get("method", "").lower(), "")
            records.append(r)
        except ValidationError as exc:
            rejected.append({"line": idx, "original": original, "error": str(exc)})
    counts = Counter(r["id"] for r in records)
    fingerprints = Counter(
        tuple(sorted((k, str(v)) for k, v in r["original"].items())) for r in records
    )
    for r in records:
        fp = tuple(sorted((k, str(v)) for k, v in r["original"].items()))
        r["duplicate"] = counts[r["id"]] > 1 or fingerprints[fp] > 1
    warnings = []
    if source == "bank_statement":
        for prev, row in zip(records, records[1:]):
            if prev["balance"] + row["credit"] - row["debit"] != row["balance"]:
                warnings.append(
                    {
                        "row_id": row["row_id"],
                        "error": "Running balance does not reconcile",
                    }
                )
    return {
        "source": source,
        "sha256": hashlib.sha256(content).hexdigest(),
        "headers": headers,
        "records": records,
        "rejected": rejected,
        "warnings": warnings,
        "accepted": len(records),
        "rejected_count": len(rejected),
        "duplicate_count": sum(r["duplicate"] for r in records),
    }
