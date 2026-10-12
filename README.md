# ClearLedger — Bank ledger matching

An evidence-driven financial reconciliation application for an Indian merchant: internal ledger → Razorpay payment events → settlements → bank statement, plus direct ledger → bank payments. FastAPI, React/TypeScript, SQLite and local synthetic CSVs. Core operation is free and requires no API credentials.

This is a working **local single-user demonstration**, not an assessed production banking deployment. Source evidence, original values, financial differences and human overrides stay traceable. Scores indicate evidence support, not calibrated probabilities.

## Install and start

Requirements: Linux, Python 3.12+, Node.js 24 LTS and npm. The cloud environment already provides these. From the project root:

```bash
./scripts/install.sh
./scripts/start.sh
```

The frontend listens on loopback port **5173** and the API on **8000**. In ordinary local development, open the frontend in your browser; `/docs` on the API provides OpenAPI/Swagger. The cloud onboarding UI does not provide localhost web previews. `start.sh` checks the API, frontend and frontend API proxy; repeated starts reuse the managed processes. Logs and process records live in `runtime/`. Stop only these managed processes with `./scripts/stop.sh`.

For interactive terminals with reload:

```bash
.venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
# In another terminal:
cd frontend
npm run dev
```

Do not run interactive servers alongside the managed servers on the same ports. The environment is already isolated; use its existing checkout, without creating a worktree.

## Demo workflow

1. Click **Run demo reconciliation**. This creates a new immutable run, not a destructive reset.
2. View the dashboard's computed counts and switch between the three reconciliation relationships.
3. Open `L004` for a referenced amount discrepancy; `L000` for a split; `L001` for a partial collection; `setl_demo_03` for competing bank credits.
4. Investigate evidence. Without a Gemini key, this returns a clearly labelled rule-based explanation.
5. Record a review decision with a reviewer name and reason. Automated results remain intact.
6. Download review, variance, residual, unmatched, duplicate or audit CSV reports.

Upload **all four** sources under Import data for your own run. Map original column headers to canonical fields using the mapping editor, validate and inspect the preview. Rejected rows require explicit acknowledgement to exclude them from reconciliation; they remain archived and reportable. Bank debit/credit cells may be empty on the inactive side. Every source must contain accepted records. Demo and user files are never mixed implicitly.

## Test and check

```bash
.venv/bin/pytest -q
.venv/bin/ruff check --select F backend tests scripts
.venv/bin/ruff format --check backend tests scripts
npm run test --prefix frontend
npm run build --prefix frontend
# Start servers before HTTP/browser checks:
./scripts/start.sh
.venv/bin/python scripts/smoke.py
npm run test:e2e --prefix frontend
```

Browser tests use system Chromium at `/usr/bin/chromium`. Set `CHROMIUM_PATH` to another installed Chromium executable if necessary. Browser tests create synthetic runs/imports and review notes in the current local runtime. Backend tests use a separate temporary database and mock external services. They never call live Gemini or Razorpay.

## Synthetic sources and observed results

The four primary files are `data/internal_ledger.csv`, `data/razorpay_recon.csv`, `data/razorpay_settlements.csv` and `data/bank_statement.csv`. They contain **180 ledger records, 189 events, 32 settlements and 152 bank transactions**. All customers, references, narration conventions, fees, merchant settings and bank activity are synthetic. The running balance starts at ₹5,00,000 and is generated arithmetically.

The default deterministic run produces **212 relationship decisions**: 198 matched, 8 review, 2 unmatched, 2 delayed, 1 partial and 1 failed. Relationship decisions are not unique transaction counts and must not be added to source counts. Outstanding ledger residual is ₹9,596.95; proposed settlement-to-bank differences total ₹120.00. Human decisions can change current review statuses; dashboard financial totals remain explicitly labelled as automated/proposed results.

`data/expected_results.json` independently specifies the seeded outcomes. [Seeded scenarios](docs/scenarios.md) explains their evidence and tests. `scripts/generate_demo.py` reproduces the synthetic CSVs deterministically; it rewrites only the demo files and should never be pointed at user imports.

## Optional configuration

Copy `.env.example` to `.env` locally and enter values securely. `.env`, uploads and SQLite files are ignored by Git. The frontend never receives API keys. Existing environment variables take precedence over `.env`. Restart the backend after changing credentials.

**Gemini:** set `GEMINI_API_KEY`, `GEMINI_MODEL` (a model available to your account) and optionally `GEMINI_REQUEST_LIMIT` (default 10 outbound requests per process session). The maintained `google-genai` SDK is used. Investigation is explicit and advisory, with structured schema validation, source-ID validation, minimal input, a timeout, caching, quota limits and safe fallbacks. Confirm your account's current availability and quotas; no live model was tested without credentials. Optional use sends a limited evidence summary to Google and may incur charges under your account's terms. Core reconciliation never depends on it.

**Razorpay:** set your own authorized `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` for explicit read-only fetching under Settings. Payments, settlements and reconciliation reports use verified official endpoints with pagination, date filters, Basic authentication and bounded retries. Connection status becomes connected only after a successful real request. Raw fetched records are archived separately and exportable; they are **not automatically converted to canonical CSV inputs**. Account permissions and report availability may restrict access. See [verified integration contracts](docs/integrations.md) before interpreting API fee/tax or timestamp fields.

For signed webhook receipts set `RAZORPAY_WEBHOOK_SECRET`; optional `RAZORPAY_WEBHOOK_PREVIOUS_SECRET` supports retries after secret rotation. Receipts are verified against raw bytes, deduplicated by event ID and audited. They do not change reconciliation inputs or overwrite financial states, so out-of-order deliveries cannot roll back collections. This local loopback server must be deployed behind authenticated infrastructure and an appropriate public HTTPS endpoint before actual webhook delivery.

An optional `RECON_ACCESS_TOKEN` protects financial API operations; enter the same value in Settings' session access field. Reviewer names are local audit labels, not authenticated identities. Do not expose the development servers publicly or treat this token as a multi-user access-control system.

## Structure and documentation

```text
backend/app/          API, strict ingestion, scoring, assignment, calendar,
                      SQLite repository, reports and optional integrations
frontend/src/         React dashboard, imports, evidence dialog, review,
                      reports, settings and typed API client
frontend/e2e/         Real-browser workflow checks
data/                 Four synthetic CSVs and expected-results fixture
tests/                Domain, ingestion, API and integration tests
scripts/              Install, managed startup/stop, synthetic generator
docs/                 Architecture, data dictionary, scenarios, integrations,
                      troubleshooting and verification evidence
runtime/              Ignored local SQLite, original uploads, logs, screenshots
```

Read [architecture and accounting policy](docs/architecture.md), [data dictionary](docs/data-dictionary.md), [troubleshooting](docs/troubleshooting.md) and [verification report](docs/verification.md).

## Practical limits

- No externally verified Indian bank-holiday calendar is bundled. Demo uses a **configured** Saturday/Sunday non-working policy and T+2 cycle, not an assertion that these are universal bank or merchant rules. Verified/local-evidence holiday inputs and per-method cycles are supported by the API, recorded per run and tested offline. Do not label a hypothetical fixture as a verified real holiday.
- Split/partial invoice allocation requires a genuine, exclusive order relationship. Arbitrary subset-sum matching is deliberately avoided. Split bank credits or one bank credit covering several settlements require an allocation model beyond this version and remain review/unmatched.
- Canonical CSV settlement accounting uses explicitly separate gross, fee, tax, refund and signed adjustment components. Raw API recon credit/debit amounts may already be net; don't subtract fees again or treat a settlement creation timestamp as a bank date. Unsupported transfer/foreign-currency schemas require explicit adaptation.
- CSVs: UTF-8, 5 MB, 10,000 import rows. Reconciliation: up to 1,500 ledger/settlement and 3,000 bank/event rows per source. This bounds the dense global assignment; larger production datasets need a sparse solver.
- SQLite and append-only application audit records are local persistence, not a tamper-proof regulatory ledger. Multi-user identity, roles, encryption/key management, production deployment, retention policies and security assessment are separate work.
- Live credentials and a current holiday source were not supplied. Their real-world behaviour has not been verified; mocked integration tests are identified as such.
