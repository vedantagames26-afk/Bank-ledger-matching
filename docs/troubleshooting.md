# Troubleshooting

**Install fails writing a home cache:** use `scripts/install.sh`; it directs pip/npm caches into writable `/workspace` paths. Do not disable TLS, signature or checksum verification.

**Missing module:** run the install script from the project root, and use `.venv/bin/python`, not system Python. All Python dependencies are pinned in `backend/requirements.lock`; frontend dependencies resolve through `npm ci` and the committed lockfile.

**Port already used:** inspect `runtime/backend.log` and `runtime/frontend.log`. `scripts/stop.sh` only targets recorded managed commands belonging to this checkout. Stop your own interactive server separately, or use another port with a corresponding Vite proxy update in a coding task. Don't terminate unrelated processes.

**New server configuration isn't reflected:** stop/start the managed servers. Python credentials and integration status initialize at process startup. Existing run snapshots retain their original configuration; start a new run after changing the settlement profile.

**Dashboard says service unavailable:** confirm backend health on port 8000 and the frontend `/api/health` proxy on 5173 with local HTTP requests. Browser error messages are sanitized. Network API requests are optional for demo mode.

**HTTP 401:** if `RECON_ACCESS_TOKEN` is configured, enter that same value in the browser's session access settings. The value is session-local and not included in source code. Don't paste credentials into chat.

**Import rejects rows:** review the ingestion report. Check required headers/mapping, YYYY-MM-DD dates, finite two-decimal money and transaction direction. Invalid money is never replaced by zero. Correct source files and upload again; old bytes/results are retained. Duplicate IDs are quarantined rather than automatically deleted.

**Balance warnings:** preserve statement order. Confirm whether the provided balance column is post-transaction balance and whether the extract omits intermediate rows. The first row needs an opening balance from an independent source for a full opening-balance check.

**High score still needs review:** check amount difference, contradictory references, competing candidates, duplicate/missing settlement components and timing. A score is not an accounting authorization. Missing UTRs aren't automatic failures.

**Gemini disabled/quota/error:** confirm only the **presence** of key/model configuration; never dump your environment. Select an account-available model and review quotas. Correct the cause, then restart. Deterministic functions, import, review, audit and reports remain available.

**Razorpay unavailable:** credentials, account permission, report access and date range can each cause failure. Check the sanitized HTTP status and official account settings. Use CSV/demo mode; never invent missing events or display an untested connection as connected.

**Holiday explanation unavailable:** obtain the appropriate local bank/product calendar and provenance, then enter explicit verified calendar evidence. No nationwide/current banking holiday feed was verified during this task. Saturday/Sunday demo settings are not a universal bank calendar.

**Browser tests fail to launch:** install Chromium through your OS's trusted package manager or set `CHROMIUM_PATH`. Current cloud machine has `/usr/bin/chromium`. Playwright browser downloads initially met domain restrictions; system Chromium was used and tested instead.

**Sensitive data:** `runtime/` is local/ignored, not encrypted. No destructive reset endpoint is exposed. Archive needed records and stop the application before any manual removal. Never delete user data just to reset tests; backend tests isolate their SQLite files in `/tmp`.
