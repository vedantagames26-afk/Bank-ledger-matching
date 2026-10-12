"""Seeded synthetic dataset; no records or references are real bank/API claims."""

from pathlib import Path
import csv
import json
from datetime import date, timedelta
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.calendar import BusinessCalendar

ROOT = Path(__file__).resolve().parents[1]


def write(name, rows):
    with (ROOT / "data" / (name + ".csv")).open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def money(p):
    return f"{p // 100}.{p % 100:02d}" if p >= 0 else "-" + money(-p)


def generate():
    cal = BusinessCalendar()
    ledger, events, settlements, bank = [], [], [], []
    for i in range(160):
        amount = 150000 + i * 7313
        day = date(2026, 1, 1) + timedelta(days=i // 5)
        lid, order, pid, sid = (
            f"L{i:03}",
            f"order_demo_{i:03}",
            f"pay_demo_{i:03}",
            f"setl_demo_{i // 5:02}",
        )
        if i == 0:
            amount = 1000000
        if i == 1:
            amount = 800000
        if i in (8, 9):
            amount = 222222
        name = f"Customer {i:03}"
        row = dict(
            id=lid,
            date=day.isoformat(),
            amount=money(amount),
            channel="razorpay",
            order_id=order,
            payment_id="",
            reference="",
            method="upi" if i % 2 else "card",
            name=name,
        )
        ledger.append(row)
        if i == 3:
            continue
        base = dict(
            id=pid,
            date=day.isoformat(),
            amount=money(amount),
            event_type="payment",
            status="captured",
            order_id=order,
            settlement_id=sid,
            fee=money(amount * 2 // 100),
            tax=money((amount * 2 // 100) * 18 // 100),
            method=row["method"],
            name=name,
        )
        if i == 0:
            for j, part in enumerate((400000, 600000)):
                e = base.copy()
                e.update(
                    id=pid + "_" + str(j),
                    amount=money(part),
                    fee=money(part * 2 // 100),
                    tax=money(part * 2 // 100 * 18 // 100),
                )
                events.append(e)
            continue
        if i == 1:
            base["amount"] = "4000.00"
            base["fee"] = "80.00"
            base["tax"] = "14.40"
        if i == 2:
            base["status"] = "failed"
        if i == 4:
            base["amount"] = money(amount + 7500)
        if i == 5:
            base["name"] = "Different trading entity"
        if i == 6:
            row["order_id"] = ""
            base["order_id"] = ""
        if i in (8, 9):
            row["order_id"] = ""
            base["order_id"] = ""
            base["name"] = row["name"] = ""
            base["method"] = row["method"] = "upi"
        if i == 10:
            events.append(base.copy())
            events.append(base.copy())
            continue
        if i == 12:
            base["date"] = (day + timedelta(days=20)).isoformat()
        if i == 11:
            base["order_id"] = "order_contradictory"
            row["payment_id"] = pid
        events.append(base)
    for i in range(15):
        events.append(
            dict(
                id=f"rfnd_demo_{i:02}",
                date=(date(2026, 1, 3) + timedelta(days=i)).isoformat(),
                amount="100.00",
                event_type="refund",
                status="processed",
                order_id="",
                settlement_id=f"setl_demo_{i:02}",
                fee="0.00",
                tax="0.00",
                method="",
                name="Synthetic refund",
            )
        )
    for i in range(8):
        events.append(
            dict(
                id=f"adj_demo_{i:02}",
                date=(date(2026, 1, 3) + timedelta(days=i)).isoformat(),
                amount="25.00",
                event_type="adjustment",
                status="processed",
                order_id="",
                settlement_id=f"setl_demo_{i:02}",
                fee="0.00",
                tax="0.00",
                method="",
                name="Synthetic adjustment",
            )
        )
    for i in range(5):
        events.append(
            dict(
                id=f"failed_extra_{i}",
                date="2026-01-10",
                amount="3000.00",
                event_type="payment",
                status="failed",
                order_id="",
                settlement_id="",
                fee="0.00",
                tax="0.00",
                method="upi",
                name="Failed attempt",
            )
        )
    from backend.app.ingestion import paise

    for i in range(32):
        sid = f"setl_demo_{i:02}"
        group = [e for e in events if e["settlement_id"] == sid]
        unique = {e["id"]: e for e in group}.values()
        net = 0
        for e in unique:
            if e["status"] == "failed":
                continue
            a = paise(e["amount"])
            fee = paise(e["fee"])
            tax = paise(e["tax"])
            net += (-a if e["event_type"] == "refund" else a) - fee - tax
        captured = date(2026, 1, 1) + timedelta(days=i)
        settled = cal.add(captured, 2)
        if i == 7:
            settled = cal.add(settled, 4)
        reference = f"SYNTHUTR{i:09}" if i != 4 else ""
        settlements.append(
            dict(
                id=sid,
                date=settled.isoformat(),
                amount=money(net),
                reference=reference,
                name="Demo merchant",
                status="processed",
            )
        )
        if i == 5:
            continue
        bank_amount = net - 12000 if i == 1 else net
        narration = (
            f"NEFT / PG settlement / Demo merchant {sid}"
            if i % 2
            else f"IMPS / merchant payout {sid}"
        )
        bank.append(
            dict(
                **{
                    "Row ID": f"BSET{i:02}",
                    "Value Date": settled.isoformat(),
                    "Post Date": settled.isoformat(),
                    "Details": narration,
                    "Ref No/Cheque No": reference,
                    "Debit": "0.00",
                    "Credit": money(bank_amount),
                    "Balance": "0.00",
                }
            )
        )
        if i == 3:
            b = bank[-1].copy()
            b["Row ID"] = "BAMB03"
            bank.append(b)
    for i in range(20):
        day = (date(2026, 1, 2) + timedelta(days=i)).isoformat()
        a = 330000 + i * 19879
        ledger.append(
            dict(
                id=f"D{i:03}",
                date=day,
                amount=money(a),
                channel="direct",
                order_id="",
                payment_id="",
                reference="",
                method="bank",
                name=f"Wholesale client {i}",
            )
        )
        bank.append(
            dict(
                **{
                    "Row ID": f"BDIR{i:02}",
                    "Value Date": day,
                    "Post Date": day,
                    "Details": f"NEFT Wholesale client {i}",
                    "Ref No/Cheque No": "",
                    "Debit": "0.00",
                    "Credit": money(a),
                    "Balance": "0.00",
                }
            )
        )
    for i in range(100):
        day = date(2026, 1, 1) + timedelta(days=i % 40)
        credit = i % 4 == 0
        a = 23000 + i * 1397
        bank.append(
            dict(
                **{
                    "Row ID": f"BOTHER{i:03}",
                    "Value Date": day.isoformat(),
                    "Post Date": (
                        day + timedelta(days=1 if i % 7 == 0 else 0)
                    ).isoformat(),
                    "Details": [
                        "UPI / supplier invoice",
                        "IMPS / rent transfer",
                        "Utility / electricity",
                        "NEFT / unrelated business credit",
                    ][i % 4],
                    "Ref No/Cheque No": f"SYNTHREF{i}" if i % 6 else "",
                    "Debit": money(0 if credit else a),
                    "Credit": money(a if credit else 0),
                    "Balance": "0.00",
                }
            )
        )
    bank.sort(key=lambda b: (b["Post Date"], b["Row ID"]))
    balance = 50000000
    for b in bank:
        balance += paise(b["Credit"]) - paise(b["Debit"])
        b["Balance"] = money(balance)
    for name, rows in [
        ("internal_ledger", ledger),
        ("razorpay_recon", events),
        ("razorpay_settlements", settlements),
        ("bank_statement", bank),
    ]:
        write(name, rows)
    expected = {
        "ledger": {
            "L000": "MATCHED",
            "L001": "PARTIAL",
            "L002": "FAILED",
            "L003": "UNMATCHED",
            "L004": "REVIEW",
            "L005": "MATCHED",
            "L006": "MATCHED",
            "L008": "REVIEW",
            "L009": "REVIEW",
            "L010": "REVIEW",
            "L011": "REVIEW",
            "L012": "DELAYED",
            "D000": "MATCHED",
        },
        "settlements": {
            "setl_demo_00": "MATCHED",
            "setl_demo_01": "REVIEW",
            "setl_demo_02": "REVIEW",
            "setl_demo_04": "MATCHED",
            "setl_demo_03": "REVIEW",
            "setl_demo_05": "UNMATCHED",
            "setl_demo_07": "DELAYED",
        },
        "opening_balance_paise": 50000000,
        "synthetic": True,
    }
    (ROOT / "data" / "expected_results.json").write_text(
        json.dumps(expected, indent=2) + "\n"
    )
    print(
        {
            k: len(v)
            for k, v in [
                ("ledger", ledger),
                ("events", events),
                ("settlements", settlements),
                ("bank", bank),
            ]
        }
    )


if __name__ == "__main__":
    generate()
