# Architecture and accounting policy

CSV ingestion preserves original cells and produces a canonical record with source-row identity, integer paise, ISO dates, explicit direction and duplicate flags. Each import gets a SHA-256 content hash and immutable database payload; original bytes are archived under a generated identifier, never the uploaded filename. Every run stores all normalized and original snapshots, hashes, configuration, candidate alternatives and automated results. Human decisions append an overlay and an audit entry transactionally; they never update the automated payload.

The API is a thin orchestrator over independent ingestion, calendar, scoring, matching, repository, report and investigation modules. SQLite connections are per operation with WAL and transactional review decisions. FastAPI produces the OpenAPI schema. React communicates through the same-origin Vite proxy, handles loading/error/empty states, and derives presentation from API results.

## Evidence and allocation

Three profiles preserve the requested starting weights:

| Relationship | Amount | Reference | Date | Method/direction | Name |
|---|---:|---:|---:|---:|---:|
| Ledger → gateway payment | 60% | Additional genuine-reference evidence | 25% | 10% | 5% |
| Settlement → bank credit | 50% | 25% | 15% | 7% | 3% |
| Direct ledger → bank credit | 65% | Additional genuine-reference evidence | 25% | 7% | 3% |

Unavailable fields are excluded and available weights normalized. Amount agreement is `max(0, 1 - abs(candidate-source)/max(abs(source),1))`. Date support declines linearly across eight working days. Names use a bounded string-similarity ratio and are never a hard gate. Unknown methods are unavailable evidence; an explicitly different comparable method is contradictory method evidence, not an invented mapping. A score may naturally reach 100 on complete exact evidence, but status never assigns an arbitrary score.

Candidate discovery retains genuine reference relationships even when amounts or dates disagree. Without a shared reference it uses a configurable ±7 calendar-day window and a 20% amount window (minimum ₹1). These are discovery boundaries, not acceptance tolerances. Only captured payment events are eligible for allocation; failed attempts remain visible among evidence candidates. Refunds are not ledger payment candidates.

Global assignment uses SciPy's Hungarian solver with dummy unmatched columns. Both direct payments and settlements compete in one bank assignment using their own profiles, so earlier iteration cannot steal a stronger allocation. Utility is evidence score minus 55 plus a 50-point bonus for genuine shared references. A contradictory reference or amount difference without shared reference remains visible as an alternative, but does not reserve money. The bonus selects which evidence to investigate; it never changes accounting status or erases a variance.

Invoice groups require an exclusive genuine shared order, date compatibility and successful nonduplicate payment events. Equal sums become split allocations; smaller sums remain partial with residuals. No arbitrary combinations are searched simply to make arithmetic match. A payment or bank row cannot be reused across independent allocations.

## Status gates

| Status | Policy |
|---|---|
| MATCHED | Exact paise agreement, ≥90 evidence score, no comparable reference contradiction, no close exact-amount competing candidate, compatible dates and settlement integrity |
| REVIEW | Financial discrepancy with reference evidence; ambiguous competitors within four score points; contradictory references; insufficient evidence; incomplete/duplicate settlement components |
| PARTIAL | Supported exclusive order collection below the invoice amount; residual remains |
| DUPLICATE | Duplicate source row/identifier quarantined from allocation |
| FAILED | Genuine related failed payment without a successful allocation |
| DELAYED | Accepted financial relationship outside the date policy, or settlement later than its configured working-day expectation; cause unverified |
| UNMATCHED | No eligible unallocated candidate; alternatives may still be shown |

Automatic matching accepts no unexplained amount tolerance. A UTR match cannot override even a small difference. Manual confirmation records a human judgement and preserves the original difference and automated status.

## Financial integrity

Canonical settled payment contribution is gross minus separate fee minus separate tax. Processed refunds/reversals subtract their amount and any separately reported fee/tax; processed signed adjustments add their amount and subtract their separate charges. Failed/pending events contribute no collected money. Held/unsettled events are excluded with a visible integrity problem. Duplicate events are quarantined; repeated IDs are never counted twice. Missing charge fields prevent an automatic integrity claim. Authoritative settlement net is preserved and compared with the calculated net, never replaced by it.

Bank records have exactly one positive debit or credit. Value and posting dates are stored separately. Consecutive running balances are validated in input order; the demo also tests its explicit opening balance. Warnings remain visible in ingestion snapshots. Dashboard totals label proposed associations separately from automatically confirmed credits.

The calendar defaults are synthetic merchant settings. Per-method settlement cycles, non-working weekdays and verified holiday evidence can be provided per run. A holiday affects dates only when it has `verified: true`, a source and a verification date; this is a caller assertion backed by local evidence, not a remote verification service. Calendar days, working days, capture-related dates, settlement dates and bank value/posting dates remain distinct in source/evidence views.

## Security and privacy

Same-origin financial API requests, trusted hosts, loopback servers, bounded uploads/assignment, safe spreadsheet exports, ignored secret/runtime files and optional local token reduce risk in this demonstration. No public deployment or compliance claim is made. Reviewer labels are not authenticated identities. Raw webhook bodies are authenticated before parsing and are not persisted; only event identity/digest/outcome are recorded. API errors omit stack traces and secret values.

Gemini receives minimal evidence only on an explicit request. Its schema-validated explanation is advisory and cannot modify source values, assignment, score or status. Valid source citations still do not guarantee every generated sentence is correct; finance reviewers must verify advisory hypotheses. A configured request/session quota, timeout, disabled mode, error state and rule fallback preserve the core workflow.
