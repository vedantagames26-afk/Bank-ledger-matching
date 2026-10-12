# Verification evidence

Observed on **13 October 2026 (Asia/Kolkata)** in `/workspace/Bank-ledger-matching`. This documents the current machine; environment publication and restoration in a new task have not been verified.

| Check | Observed outcome |
|---|---|
| `scripts/install.sh` | Passed using pinned Python dependencies and `npm ci`; frontend production build passed |
| `pytest -q` | **98 passed**, no failures or skips; one Starlette/httpx test-client deprecation warning |
| `ruff check --select F backend tests scripts` | Passed |
| `ruff format --check backend tests scripts` | Passed |
| `pip check` | No broken requirements |
| `npm run test --prefix frontend` | **5 passed** |
| `npm run test:e2e --prefix frontend` | **3 passed** using real system Chromium |
| `npm run build --prefix frontend` | TypeScript and production bundling passed |
| Managed stop/start and repeated start | Both services restarted; repeated startup reused them; API proxy verified |
| `scripts/smoke.py` | HTTP-created demo run matched the independent expected fixture; matched CSV download and rule-based investigation passed |
| CSV ingestion | All four demo sources had zero rejected rows and zero balance warnings; two duplicate gateway rows intentionally retained |
| Git scope | Original checkout contained only README; application, tests, manifests, lockfiles, docs and demo data are intentional new files; local runtime/caches/secrets are ignored |

Browser checks exercised demo execution, actual API integration, source counts, search/filter interaction, match details, rule-based investigation with Gemini disabled, persisted review notes, CSV download, all four file uploads/preview, uploaded reconciliation, optional Razorpay state, responsive mobile navigation and return-to-top behaviour. Dashboard screenshots were captured and visually inspected. They are local artifacts in `runtime/dashboard.png` and `runtime/dashboard-settings.png`, not public previews.

Backend/domain tests include exact/missing-reference evidence, names differing, referenced amount contradictions, grouped settlement arithmetic, fees/taxes/refunds/adjustments, weekend/verified-fixture/unverified calendars, partial/split payments, failed events, duplicate quarantine, no double counting, no bank/payment reuse, global assignment, coherent bank balances, malformed/missing/duplicate CSVs, column mapping, safe exports, immutable snapshots, audit decisions, Gemini disabled/quota/malformed handling and persisted explanations. Read-only Razorpay transport and webhook tests use deterministic mocks/signatures, not real accounts.

The final default HTTP demo produced:

- 180 ledger records, 189 gateway events, 32 settlements and 152 bank rows.
- 212 relationship cases: **198 MATCHED, 8 REVIEW, 2 UNMATCHED, 2 DELAYED, 1 PARTIAL, 1 FAILED**.
- ₹9,596.95 outstanding ledger residual, including unresolved/failed/quarantined collections.
- ₹11,48,952.48 authoritative expected settlement net.
- ₹11,31,944.88 proposed associated bank credits; ₹10,76,813.66 automatically confirmed credits.
- ₹120.00 absolute proposed bank-credit discrepancy.
- All 100 unrelated bank entries stayed unallocated and visible.

The original input SHA-256 hashes are:

```text
internal_ledger     fe548f9a41aada1c5a2b06c799df4405889f1e604c350d60340a0dbc91422347
razorpay_recon      16da9ec105cacccfb3f513bb080250071b099710e81734e657671cedbeafd36a
razorpay_settlements af0aa8a5cb75b1cc7830528dd5609dbac20cbeaaf23d1ad39e2ebc4f4990c3b2
bank_statement     054be1143dd614d46795e8690f543cf70f4a0bfb97dcf2bccfbd7353dc6b98ec
```

No actual secret file was created, no secret values were printed, and no credential values are part of the source or saved environment scripts. No live Gemini inference, merchant Razorpay connection, real webhook delivery or externally verified Indian holiday feed was tested. The hypothetical holiday fixture is labelled; it is not a real calendar assertion. Live reports preserve raw API semantics and require deliberate adaptation before canonical reconciliation. Split/combined bank settlement allocations and assessed multi-user production security remain outside this version.

Reusable cloud configuration was saved successfully: `install_script` runs the tested installation helper; `start_skill` documents existing-checkout use, service restart/readiness, the HTTP smoke check, test commands and credential/calendar limits. The final custom domain additions are `razorpay.com`, `api.razorpay.com`, `ai.google.dev` and `generativelanguage.googleapis.com`; existing package-manager presets are preserved. Unneeded browser/holiday research additions were removed. No secret requirements or values were added. Review/save in environment settings, then publish to preserve the prepared filesystem snapshot. Draft saving did not itself publish or prove fresh-task restoration.
