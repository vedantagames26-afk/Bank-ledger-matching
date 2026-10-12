from datetime import date
from pathlib import Path
import json
import pytest
from backend.app.calendar import BusinessCalendar
from backend.app.engine import (
    DEFAULT_CONFIG,
    global_match,
    settlement_integrity,
    reconcile,
)
from backend.app.scoring import PROFILES, candidates, score
from backend.app.ingestion import paise


def record(ident="a", amount=10000, **kw):
    kw.setdefault("fee", 0)
    kw.setdefault("tax", 0)
    return dict(
        id=ident,
        row_id=ident,
        date="2026-01-05",
        amount=amount,
        original={},
        duplicate=False,
        **kw,
    )


@pytest.mark.parametrize("profile", PROFILES)
def test_weights(profile):
    assert sum(PROFILES[profile].values()) == pytest.approx(1)


@pytest.mark.parametrize("profile", PROFILES)
def test_exact_amount_date(profile):
    left = record(name="Entity", method="upi")
    right = record(
        "b",
        name="Entity",
        method="upi",
        direction="credit",
        event_type="payment",
        status="captured",
    )
    e = score(left, right, profile)
    assert e["difference"] == 0 and e["calendar_days"] == 0 and e["score"] >= 95


@pytest.mark.parametrize("profile", PROFILES)
def test_missing_reference_not_zero(profile):
    e = score(record(), record("b", direction="credit"), profile)
    assert e["score"] > 85
    if profile == "settlement_bank":
        assert "reference" in e["missing_evidence"]


def test_different_names():
    left = record(name="Retailer", method="upi", payment_id="b")
    right = record(
        "b",
        name="Another company",
        method="upi",
        event_type="payment",
        status="captured",
    )
    r = global_match(
        [left], [right], "ledger_razorpay", DEFAULT_CONFIG, BusinessCalendar()
    )[0]
    assert r["status"] == "MATCHED"


def test_reference_preserves_amount_discrepancy():
    left = record(reference="UTR")
    right = record("b", amount=20000, reference="UTR", direction="credit")
    assert candidates(left, [right], "settlement_bank") == [right]
    result = global_match(
        [left], [right], "settlement_bank", DEFAULT_CONFIG, BusinessCalendar()
    )[0]
    assert result["status"] == "REVIEW" and result["evidence"]["difference"] == 10000


def test_ambiguity():
    r = global_match(
        [record()],
        [record("b", direction="credit"), record("c", direction="credit")],
        "settlement_bank",
        DEFAULT_CONFIG,
        BusinessCalendar(),
    )[0]
    assert r["status"] == "REVIEW"


def test_global_does_not_steal():
    left = [record("weak"), record("strong", reference="UTR")]
    right = [record("only", direction="credit", reference="UTR")]
    results = global_match(
        left, right, "settlement_bank", DEFAULT_CONFIG, BusinessCalendar()
    )
    assert results[1]["right"]["id"] == "only" and results[0]["right"] is None


def test_no_bank_reuse(result):
    allocations = [
        c["right"]["row_id"]
        for c in result["cases"]
        if c["right"] and c["profile"] != "ledger_razorpay"
    ]
    assert len(allocations) == len(set(allocations))


def test_no_payment_reuse(result):
    allocated = []
    for c in result["cases"]:
        if c["profile"] == "ledger_razorpay" and c["right"]:
            allocated += [r["row_id"] for r in c["right"].get("members", [c["right"]])]
    assert len(allocated) == len(set(allocated))


def test_weekend():
    assert BusinessCalendar().add(date(2026, 1, 2), 2) == date(2026, 1, 6)


def test_verified_configured_holiday():
    cal = BusinessCalendar(
        {
            "2026-01-06": {
                "verified": True,
                "source": "controlled test fixture, not a real holiday",
                "verified_at": "2026-01-01",
            }
        }
    )
    assert cal.add(date(2026, 1, 2), 2) == date(2026, 1, 7)


@pytest.mark.parametrize(
    "holiday",
    [
        {"verified": False, "source": "rumour", "verified_at": "today"},
        {"verified": True},
        {"verified": True, "source": "missing verification date"},
    ],
)
def test_unverified_holiday(holiday):
    cal = BusinessCalendar({"2026-01-06": holiday})
    assert cal.add(date(2026, 1, 2), 2) == date(2026, 1, 6)


def test_business_difference():
    cal = BusinessCalendar()
    assert cal.difference(date(2026, 1, 2), date(2026, 1, 6)) == 2
    assert cal.difference(date(2026, 1, 6), date(2026, 1, 2)) == -2


def test_settlement_arithmetic():
    events = [
        record(
            "p",
            amount=10000,
            event_type="payment",
            status="captured",
            settlement_id="s",
            fee=200,
            tax=36,
        ),
        record(
            "r", amount=1000, event_type="refund", status="processed", settlement_id="s"
        ),
        record(
            "a",
            amount=-100,
            event_type="adjustment",
            status="processed",
            settlement_id="s",
        ),
        record(
            "f", amount=90000, event_type="payment", status="failed", settlement_id="s"
        ),
    ]
    info = settlement_integrity(
        record("s", amount=8664), events, BusinessCalendar(), DEFAULT_CONFIG
    )
    assert (
        info["calculated_net"] == 8664
        and info["gross"] == 10000
        and info["refunds"] == 1000
        and not info["problems"]
    )


def test_no_double_counting():
    payment = record(
        "p", amount=10000, event_type="payment", status="captured", settlement_id="s"
    )
    info = settlement_integrity(
        record("s"), [payment, payment], BusinessCalendar(), DEFAULT_CONFIG
    )
    assert info["calculated_net"] == 10000 and info["problems"]


def test_split_and_partial(result):
    cases = {c["left"]["id"]: c for c in result["cases"]}
    assert (
        cases["L000"]["status"] == "MATCHED"
        and len(cases["L000"]["right"]["members"]) == 2
    )
    assert cases["L000"]["right"]["amount"] == cases["L000"]["left"]["amount"]
    assert cases["L001"]["status"] == "PARTIAL" and cases["L001"]["residual"] == 400000


def test_arbitrary_subset_not_split():
    data = {
        "internal_ledger": [record("l", amount=10000, channel="razorpay")],
        "razorpay_recon": [
            record("a", amount=4000, event_type="payment", status="captured"),
            record("b", amount=6000, event_type="payment", status="captured"),
        ],
        "razorpay_settlements": [],
        "bank_statement": [],
    }
    r = reconcile(data)
    assert r["cases"][0]["status"] != "MATCHED"


def test_failed_not_allocated(result):
    assert (
        next(c for c in result["cases"] if c["left"]["id"] == "L002")["status"]
        == "FAILED"
    )
    assert all(
        c["right"].get("status") != "failed" for c in result["cases"] if c["right"]
    )


def test_direct_without_utr(result):
    c = next(c for c in result["cases"] if c["left"]["id"] == "D000")
    assert (
        c["profile"] == "direct_bank"
        and c["status"] == "MATCHED"
        and not c["left"]["reference"]
    )


def test_unrelated_bank_visible(result):
    assert (
        len([r for r in result["unmatched_bank"] if r["id"].startswith("BOTHER")])
        == 100
    )


def test_duplicate_events_preserved(dataset, result):
    assert len([r for r in dataset["razorpay_recon"] if r["id"] == "pay_demo_010"]) == 2
    assert all(
        r["duplicate"] for r in dataset["razorpay_recon"] if r["id"] == "pay_demo_010"
    )
    c = next(c for c in result["cases"] if c["left"]["id"] == "setl_demo_02")
    assert c["status"] == "REVIEW" and c["settlement"]["problems"]


def test_bank_balance(dataset):
    balance = json.loads(Path("data/expected_results.json").read_text())[
        "opening_balance_paise"
    ]
    for r in dataset["bank_statement"]:
        balance += r["credit"] - r["debit"]
        assert balance == r["balance"]
    assert len(dataset["bank_statement"]) >= 100


def test_money_precision():
    assert paise("0.10") + paise("0.20") == 30


def test_metrics_derive_from_results(result, dataset):
    assert result["metrics"]["matched"] == sum(
        c["status"] == "MATCHED" for c in result["cases"]
    )
    assert result["metrics"]["expected_settlement"] == sum(
        r["amount"] for r in dataset["razorpay_settlements"]
    )


def test_expected_fixture(result):
    expected = json.loads(Path("data/expected_results.json").read_text())
    cases = {c["left"]["id"]: c for c in result["cases"]}
    for key in ("ledger", "settlements"):
        for ident, status in expected[key].items():
            assert cases[ident]["status"] == status, (ident, cases[ident]["reason"])


def test_duplicate_ledger_does_not_steal():
    left = [record("bad", duplicate_override=True), record("good")]
    left[0]["duplicate"] = True
    results = global_match(
        left,
        [record("bank", direction="credit")],
        "direct_bank",
        DEFAULT_CONFIG,
        BusinessCalendar(),
    )
    assert results[0]["status"] == "DUPLICATE" and results[1]["right"]["id"] == "bank"


def test_missing_charges_prevent_integrity_claim():
    payment = record("p", event_type="payment", status="captured", settlement_id="s")
    del payment["fee"]
    assert settlement_integrity(
        record("s"), [payment], BusinessCalendar(), DEFAULT_CONFIG
    )["problems"]


def test_method_cycle_override():
    payment = record(
        "p", event_type="payment", status="captured", settlement_id="s", method="card"
    )
    config = {**DEFAULT_CONFIG, "method_settlement_days": {"card": 3}}
    info = settlement_integrity(record("s"), [payment], BusinessCalendar(), config)
    assert info["expected_date"] == "2026-01-08"


def test_explicit_split_provenance(result):
    c = next(c for c in result["cases"] if c["left"]["id"] == "L000")
    assert c["right"]["id"].startswith("allocation:")
    assert c["right"]["members"][0]["original"]["amount"] == "4000.00"
    assert c["right"]["amount"] == 1000000


def test_deterministic_no_mutation(dataset):
    from copy import deepcopy

    original = deepcopy(dataset)
    assert reconcile(dataset) == reconcile(dataset)
    assert dataset == original
