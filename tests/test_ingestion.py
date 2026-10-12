import pytest
from backend.app.ingestion import ingest, paise, ValidationError
from backend.app.reports import csv_bytes


@pytest.mark.parametrize("value", ["NaN", "Infinity", "bad", "12.001", ""])
def test_invalid_money(value):
    with pytest.raises(ValidationError):
        paise(value)


@pytest.mark.parametrize(
    "csv",
    [
        b"id,date,amount,channel\nx,2026-99-01,10,razorpay\n",
        b"id,date,amount,channel\nx,2026-01-01,no,razorpay\n",
        b"id,date,amount,channel\nx,2026-01-01,-5,razorpay\n",
        b"id,date,amount,channel\nx,2026-01-01,10,unknown\n",
        b"id,date,amount,channel\nx,2026-01-01,10,razorpay,extra\n",
    ],
)
def test_rejected_preserves_original(csv):
    result = ingest("internal_ledger", csv)
    assert (
        result["rejected_count"] == 1
        and result["accepted"] == 0
        and result["rejected"][0]["original"]
    )


def test_missing_columns():
    with pytest.raises(ValidationError, match="Missing columns"):
        ingest("internal_ledger", b"id,date\n")


def test_ambiguous_headers():
    with pytest.raises(ValidationError, match="Ambiguous"):
        ingest("internal_ledger", b"id,id,date,amount,channel\n")


def test_duplicate_rows():
    result = ingest(
        "internal_ledger",
        b"id,date,amount,channel\nx,2026-01-01,10,razorpay\nx,2026-01-01,10,razorpay\n",
    )
    assert result["accepted"] == 2 and result["duplicate_count"] == 2


def test_custom_mapping():
    result = ingest(
        "internal_ledger",
        b"Invoice,Day,Value,Route\nx,2026-01-01,10,direct\n",
        {"Invoice": "id", "Day": "date", "Value": "amount", "Route": "channel"},
    )
    assert (
        result["records"][0]["amount"] == 1000
        and result["records"][0]["original"]["Value"] == "10"
    )


def test_bad_utf8():
    with pytest.raises(ValidationError):
        ingest("internal_ledger", b"\xff")


def test_bad_direction():
    r = ingest(
        "bank_statement",
        b"id,value_date,post_date,debit,credit,balance\nx,2026-01-01,2026-01-01,10,10,100\n",
    )
    assert r["rejected_count"] == 1


def test_formula_safe():
    value = csv_bytes([{"value": ' =HYPERLINK("evil")'}]).decode("utf-8-sig")
    assert "' =HYPERLINK" in value


def test_empty_amount_not_zero():
    r = ingest("internal_ledger", b"id,date,amount,channel\nx,2026-01-01,,direct\n")
    assert r["rejected_count"] == 1 and not r["records"]
