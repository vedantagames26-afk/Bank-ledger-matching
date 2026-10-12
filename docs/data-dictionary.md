# Canonical CSV data dictionary

All files are UTF-8 with a header row. Required columns must exist; dates are ISO `YYYY-MM-DD`. Currency is INR. **CSV monetary cells are rupees** with no more than two decimal places. **API normalized records and reports labelled `_paise` use integer paise.** Raw Razorpay exports keep the original documented subunit fields.

| Source | Required columns | Optional evidence |
|---|---|---|
| internal_ledger | id, date, amount, channel | order_id, payment_id, reference, method, name, expected_date |
| razorpay_recon | id, date, amount, event_type, status | order_id, settlement_id, fee, tax, method, name |
| razorpay_settlements | id, date, amount | reference, name, status |
| bank_statement | id, value_date, post_date, debit, credit, balance | reference, name |

`id` is the source's identifier, not a universal shared transaction ID. A stable generated `row_id` is `{source}:{CSV-line-number}`; it identifies duplicate rows individually. `original` retains each imported cell and header. Input hashes distinguish snapshots. Duplicate identifiers or identical original rows are flagged, never deleted.

Ledger `date` is the payment/collection comparison date; map the correct field rather than using an invoice creation date blindly. `channel` is `razorpay` or `direct`. `order_id` means a **genuine shared Razorpay order ID**, not an arbitrary internal invoice ID. `payment_id` means a genuine Razorpay payment identifier. An invoice is represented by a ledger record; order grouping remains a separate association based on explicit shared IDs.

Gateway `event_type`: payment, refund, adjustment or reversal. Status: captured, failed, processed or pending. `amount` is nonnegative except signed adjustments. Fees/taxes must be explicitly supplied to validate settlement arithmetic; absence is unknown, not proof of zero. These canonical columns define separate charges and are **not** a universal mapping for every Razorpay report. Transaction-level `settlement_id` identifies the actual group; absent relationships are not guessed.

Settlement `amount` is authoritative net, not gross collections. `date` must be the appropriate settlement date supplied by the source; it cannot automatically be inferred from `created_at`. `reference` is its genuine UTR if available. A non-processed settlement cannot be automatically accepted.

Bank aliases supported without mapping: `Row ID`, `Value Date`, `Post Date`, `Details`, `Ref No/Cheque No`, `Debit`, `Credit`, `Balance`. Blank inactive debit/credit cells become zero; exactly one side must be positive. Negative values or both-sided/zero-sided entries are rejected. `date` in normalized bank records is posting date; value date is preserved separately. `balance` is post-transaction running balance; the first row alone cannot establish the opening balance for arbitrary imports.

Method aliases explicitly map credit/debit card → card, unified payments interface → upi, NEFT/IMPS → bank. Recognized wallet/netbanking/EMI labels remain distinct. Unknown labels stay in originals and are unavailable normalized evidence.

The local calendar API configuration accepts, for example:

```json
{
  "settlement_working_days": 2,
  "weekend_days": [5, 6],
  "method_settlement_days": {"upi": 2, "card": 2},
  "holidays": {
    "2026-01-06": {
      "verified": true,
      "source": "controlled test fixture; not a real bank holiday",
      "verified_at": "2026-01-01"
    }
  }
}
```

That example is **hypothetical test evidence**, not a real holiday assertion. Supply the appropriate state/bank/product calendar with authoritative provenance in a real workflow. A holiday without verification/source/date does not explain a delay.
