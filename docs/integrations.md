# Optional integration contracts

Official Razorpay documentation was fetched during implementation and read on **13 October 2026 (Asia/Kolkata)**. No merchant credentials were present and no live merchant connection was attempted. Network restrictions initially blocked the documentation; the corrected domain configuration allowed Razorpay verification. A guessed reconciliation URL returned 404 and was not used; the actual documented route below was verified.

| Capability | Verified official documentation | Contract implemented |
|---|---|---|
| Authentication | https://razorpay.com/docs/api/authentication/ | HTTPS Basic authentication, key ID and secret; credentials stay server-side |
| Payment collection | https://razorpay.com/docs/api/payments/fetch-all-payments/ | GET `/v1/payments`; `from`, `to` UNIX seconds; count ≤100, skip pagination |
| Settlements | https://razorpay.com/docs/api/settlements/fetch-all/ | GET `/v1/settlements`; from/to, count 1–100 and skip; id, amount, status, fees, tax, utr, created_at |
| Settlement reconciliation | https://razorpay.com/docs/api/settlements/fetch-recon/ | GET `/v1/settlements/recon/combined`; required year/month, optional day, count ≤1000, skip |
| Webhook validation | https://razorpay.com/docs/webhooks/validate-test/ | Hex HMAC-SHA256 of **raw bytes**, webhook secret as key, `X-Razorpay-Signature` |
| Idempotency/order | Same webhook documentation | Unique `x-razorpay-event-id`; duplicate delivery expected; event order not guaranteed |

Recon fields verified include entity_id, type (payment/refund/transfer/adjustment), debit, credit, amount, currency, fee, tax, on_hold, settled, created_at, settled_at, settlement_id, payment_id, settlement_utr, order_id and method. Missing fields are not manufactured. Canonical ingestion intentionally does not claim to be an automatic lossless adapter for all these event types.

**Critical interpretation:** the documented recon payment example has gross amount 100000, credit 97100 and fee 2900. The credit is already net in that example. Subtracting the same fee again would double-count it. `created_at` on a settlement is creation time; it is not automatically a settlement receipt/value date. Fetched records are therefore staged as raw immutable snapshots with an export, rather than silently imported into the canonical synthetic charge model.

The client rejects malformed collection/amount fields and non-INR currency, preserves raw items, bounds pagination at 20 pages and returns no partial import if the safety limit is reached. Narrow the date range if needed. 401/403 and other failures produce sanitized messages. 429 and selected 5xx errors retry at most twice, honoring numeric Retry-After up to five seconds or using bounded exponential delays. TLS remains verified; redirects are not followed with Basic credentials. Status tracks whether an explicit request was really tested and succeeded.

Webhook receipts authenticate before parsing; valid events are deduplicated transactionally. A repeated event ID with a different digest returns 409. Current and optional previous secrets support rotation/retries. Only metadata/digest/outcome is stored; raw payload contents aren't echoed or logged. Outcomes say `recorded_not_applied`: receipts are not a complete reconciliation report and do not mutate collections based on arrival order. Public delivery requires appropriate HTTPS hosting and account configuration; this loopback demo is not publicly reachable.

## Gemini

The application uses `google-genai`, a configurable account-available `GEMINI_MODEL`, the documented SDK structured response schema interface, explicit on-demand requests and a 15-second timeout. Responses validate case identity and actual source-row citations against a strict Pydantic schema. Invalid responses, missing configuration, quota exhaustion and SDK errors safely fall back to rules. The reasoning confidence field is separate from deterministic evidence score; fallback uses zero for **no LLM reasoning**, not a financial match score.

No model availability or real inference was tested without a key. Consult https://ai.google.dev/gemini-api/docs and your account before enabling; model names and free-tier limits may change. The current client disables further calls in the process session on quota/error and never repeats a daily-quota failure. Restart after correcting configuration or after quota resets. Cache/quota are process-local and are not advertised as a durable daily quota tracker.
