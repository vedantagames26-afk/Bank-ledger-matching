import json
import os
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, Depends
from fastapi.responses import Response, JSONResponse
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
from dotenv import load_dotenv
from .ingestion import SOURCES, REQUIRED, ingest, ValidationError
from .engine import reconcile, DEFAULT_CONFIG
from .repository import Repository
from .investigation import Investigator
from .integrations import razorpay_status, razorpay, verify_hmac, IntegrationError
from .reports import REPORTS, report_rows, csv_bytes

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
RUNTIME = Path(os.getenv("RECON_RUNTIME", ROOT / "runtime"))
repo = Repository(RUNTIME / "reconciliation.sqlite3")
investigator = Investigator(limit=int(os.getenv("GEMINI_REQUEST_LIMIT", "10")))
app = FastAPI(
    title="ClearLedger Reconciliation",
    version="1.0.0",
    description="INR/paise financial reconciliation. Local single-user demonstrator. Optional live integrations are explicit.",
)
app.add_middleware(
    TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"]
)


async def local_access(request: Request):
    # Same-origin mutations prevent drive-by requests to the local finance service.
    origin = request.headers.get("origin")
    if origin and origin not in (
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ):
        raise HTTPException(403, "Untrusted origin")
    token = os.getenv("RECON_ACCESS_TOKEN")
    if token:
        import hmac

        if not hmac.compare_digest(request.headers.get("x-recon-token", ""), token):
            raise HTTPException(401, "Local access token required")


@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Request does not meet the API schema",
            "errors": [
                {"location": list(e["loc"]), "message": e["msg"]} for e in exc.errors()
            ],
        },
    )


@app.exception_handler(Exception)
async def unexpected(request, exc):
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Operation failed. Inspect local server diagnostics; source data was preserved."
        },
    )


class HolidayEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verified: bool = False
    source: str = Field(default="", max_length=1000)
    verified_at: str | None = None

    @model_validator(mode="after")
    def verified_has_provenance(self):
        from datetime import date

        if self.verified:
            if not self.source or not self.verified_at:
                raise ValueError(
                    "Verified holiday requires source and verification date"
                )
            date.fromisoformat(self.verified_at[:10])
        return self


class RunConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    settlement_working_days: int = Field(default=2, ge=0, le=10)
    candidate_window_days: int = Field(default=7, ge=1, le=31)
    accept_score: float = Field(default=90, ge=80, le=100)
    ambiguity_margin: float = Field(default=4, ge=0, le=20)
    holidays: dict[str, HolidayEvidence] = Field(default_factory=dict, max_length=366)
    weekend_days: list[int] = Field(default_factory=lambda: [5, 6], max_length=6)
    method_settlement_days: dict[str, int] = Field(default_factory=dict)

    @field_validator("holidays")
    @classmethod
    def calendar_dates(cls, value):
        from datetime import date

        for key in value:
            date.fromisoformat(key)
        return value

    @field_validator("weekend_days")
    @classmethod
    def valid_weekdays(cls, value):
        if any(n < 0 or n > 6 for n in value) or len(value) != len(set(value)):
            raise ValueError(
                "Non-working weekdays must be unique values between 0 and 6"
            )
        return value

    @field_validator("method_settlement_days")
    @classmethod
    def valid_method_cycles(cls, value):
        if any(
            method not in ("upi", "card", "bank", "wallet", "netbanking", "emi")
            or n < 0
            or n > 10
            for method, n in value.items()
        ):
            raise ValueError("Unsupported method or settlement cycle")
        return value


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    import_ids: dict[str, str] = Field(default_factory=dict)
    config: RunConfig = Field(default_factory=RunConfig)
    acknowledge_rejected: bool = False


class Decision(BaseModel):
    action: Literal["confirm", "reject", "partial", "duplicate", "unresolved", "note"]
    actor: str = Field(min_length=1, max_length=80)
    note: str = Field(min_length=3, max_length=1000)

    @field_validator("actor", "note")
    @classmethod
    def meaningful_text(cls, value):
        if not value.strip():
            raise ValueError("Reviewer and reason must contain meaningful text")
        return value.strip()


def get_run(ident):
    try:
        return repo.reviewed(repo.get("runs", ident))
    except KeyError:
        raise HTTPException(404, "Run not found")


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "mode": "local single-user",
        "currency": "INR",
        "money_unit": "paise",
    }


@app.get("/api/settings", dependencies=[Depends(local_access)])
def settings():
    return {
        "gemini": {
            "state": investigator.state,
            "model": os.getenv("GEMINI_MODEL", "Not configured"),
            "requests_used": investigator.calls,
            "request_limit": investigator.limit,
        },
        "razorpay": razorpay_status(),
        "config": DEFAULT_CONFIG,
        "calendar": {
            "source": "Configurable local evidence; demo uses weekends only",
            "verified_holidays": 0,
            "last_verified": None,
        },
        "sources": list(SOURCES),
        "required_columns": REQUIRED,
        "reports": REPORTS,
        "security": "Single-user loopback demonstration. Add authentication before deployment.",
    }


@app.get("/api/samples/{source}", dependencies=[Depends(local_access)])
def sample(source: str):
    if source not in SOURCES:
        raise HTTPException(404, "Unknown source")
    return Response(
        (ROOT / "data" / f"{source}.csv").read_bytes(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{source}.csv"'},
    )


@app.post("/api/imports/{source}", dependencies=[Depends(local_access)])
async def import_csv(
    source: str, file: UploadFile = File(...), mapping: str = Form("{}")
):
    content = await file.read(5 * 1024 * 1024 + 1)
    try:
        columns = json.loads(mapping)
        if not isinstance(columns, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in columns.items()
        ):
            raise ValidationError(
                "Column mapping must map original headers to canonical fields"
            )
        result = ingest(source, content, columns)
    except (ValidationError, json.JSONDecodeError) as exc:
        raise HTTPException(422, str(exc))
    saved = repo.save("imports", result)
    archive = RUNTIME / "imports" / saved["id"]
    archive.mkdir(parents=True, exist_ok=True)
    (archive / "source.csv").write_bytes(content)
    return saved


@app.get("/api/imports/{ident}/report", dependencies=[Depends(local_access)])
def ingestion_report(ident):
    try:
        result = repo.get("imports", ident)
    except KeyError:
        raise HTTPException(404, "Import not found")
    rows = [
        {
            "state": "accepted_duplicate" if r["duplicate"] else "accepted",
            "line": r["row_id"],
            "original": r["original"],
            "error": "",
        }
        for r in result["records"]
    ]
    rows += [{"state": "rejected", **r} for r in result["rejected"]]
    rows += [{"state": "warning", **r} for r in result["warnings"]]
    return Response(
        csv_bytes(rows, ["state", "line", "row_id", "original", "error"]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="ingestion_report.csv"'},
    )


@app.post("/api/runs", dependencies=[Depends(local_access)])
def create_run(body: RunRequest):
    datasets, hashes, imports = {}, {}, {}
    if body.import_ids and set(body.import_ids) != set(SOURCES):
        raise HTTPException(
            422, "Upload all four sources; demo and user files are not mixed implicitly"
        )
    for source in SOURCES:
        if body.import_ids:
            try:
                imported = repo.get("imports", body.import_ids[source])
            except KeyError:
                raise HTTPException(404, "Import not found")
            if imported["source"] != source:
                raise HTTPException(422, "Import source does not match")
            if imported["rejected"] and not body.acknowledge_rejected:
                raise HTTPException(
                    422,
                    "Rejected rows require explicit acknowledgement before reconciliation",
                )
        else:
            imported = ingest(source, (ROOT / "data" / f"{source}.csv").read_bytes())
        if not imported["records"]:
            raise HTTPException(422, "Each source must contain accepted rows")
        datasets[source] = imported["records"]
        hashes[source] = imported["sha256"]
        imports[source] = imported
    # Large all-pairs assignment is bounded; do not allow accidental memory exhaustion.
    if (
        len(datasets["internal_ledger"]) > 1500
        or len(datasets["razorpay_settlements"]) > 1500
        or len(datasets["bank_statement"]) > 3000
        or len(datasets["razorpay_recon"]) > 3000
    ):
        raise HTTPException(
            422,
            "Local assignment supports up to 1,500 ledger/settlement and 3,000 bank/event rows per run",
        )
    result = reconcile(datasets, body.config.model_dump())
    result["provenance"] = {
        "mode": "uploaded" if body.import_ids else "synthetic demo",
        "hashes": hashes,
        "import_ids": body.import_ids,
        "acknowledged_rejected": body.acknowledge_rejected,
    }
    result["input_snapshots"] = imports
    return repo.reviewed(repo.save("runs", result))


@app.get("/api/runs", dependencies=[Depends(local_access)])
def list_runs():
    return repo.runs()


@app.get("/api/runs/{ident}", dependencies=[Depends(local_access)])
def run(ident):
    return get_run(ident)


@app.post("/api/runs/{ident}/decisions/{case_id}", dependencies=[Depends(local_access)])
def review(ident, case_id, body: Decision):
    try:
        return repo.decide(ident, case_id, body.actor, body.action, body.note)
    except KeyError:
        raise HTTPException(404, "Run or case not found")
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.post(
    "/api/runs/{ident}/investigate/{case_id}", dependencies=[Depends(local_access)]
)
def investigate(ident, case_id):
    run = get_run(ident)
    selected = next((c for c in run["cases"] if c["id"] == case_id), None)
    if not selected:
        raise HTTPException(404, "Case not found")
    explanation = investigator.explain(selected)
    repo.audit(
        "investigation",
        "local",
        {"run_id": ident, "case_id": case_id, "result": explanation},
    )
    return explanation


@app.get("/api/runs/{ident}/reports/{kind}", dependencies=[Depends(local_access)])
def download(ident, kind):
    run = get_run(ident)
    if kind not in REPORTS:
        raise HTTPException(404, "Unknown report")
    repo.audit("report_export", "local", {"run_id": ident, "kind": kind})
    rows = repo.audits() if kind == "audit" else report_rows(run, kind)
    fields = (
        [
            "case_id",
            "profile",
            "source_id",
            "source_row",
            "candidate_id",
            "status",
            "automated_status",
            "source_amount_paise",
            "candidate_amount_paise",
            "difference_paise",
            "evidence_score",
            "residual_paise",
            "reason",
            "review",
        ]
        if kind not in ("audit", "unmatched_events", "unmatched_bank")
        else None
    )
    return Response(
        csv_bytes(rows, fields),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{kind}.csv"'},
    )


@app.get("/api/audit", dependencies=[Depends(local_access)])
def audit():
    return repo.audits()


class FetchRequest(BaseModel):
    resource: Literal["payments", "settlements", "recon"]
    from_timestamp: int | None = Field(default=None, ge=0)
    to_timestamp: int | None = Field(default=None, ge=0)
    year: int | None = Field(default=None, ge=2000, le=2100)
    month: int | None = Field(default=None, ge=1, le=12)
    day: int | None = Field(default=None, ge=1, le=31)


@app.post("/api/integrations/razorpay/sync", dependencies=[Depends(local_access)])
def sync(body: FetchRequest):
    if body.resource == "recon":
        params = {
            k: getattr(body, k)
            for k in ("year", "month", "day")
            if getattr(body, k) is not None
        }
    else:
        params = {
            k: v
            for k, v in [("from", body.from_timestamp), ("to", body.to_timestamp)]
            if v is not None
        }
        if (
            body.from_timestamp is not None
            and body.to_timestamp is not None
            and body.from_timestamp > body.to_timestamp
        ):
            raise HTTPException(422, "Start must precede end")
    try:
        items = razorpay.fetch(body.resource, params)
    except IntegrationError as exc:
        raise HTTPException(503, str(exc))
    saved = repo.save(
        "fetches",
        {
            "source": "razorpay_live",
            "resource": body.resource,
            "params": params,
            "items": items,
        },
    )
    return {
        "id": saved["id"],
        "created": saved["created"],
        "count": len(items),
        "resource": body.resource,
        "message": "Read-only raw records saved. They are not automatically treated as reconciliation inputs.",
    }


@app.get(
    "/api/integrations/razorpay/fetches/{ident}", dependencies=[Depends(local_access)]
)
def fetch_report(ident):
    try:
        result = repo.get("fetches", ident)
    except KeyError:
        raise HTTPException(404, "Fetch not found")
    repo.audit("live_report_export", "local", {"fetch_id": ident})
    fields = sorted({k for r in result["items"] for k in r}) or ["id"]
    return Response(
        csv_bytes(result["items"], fields),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="razorpay_raw.csv"'},
    )


@app.post("/api/webhooks/razorpay")
async def webhook(request: Request):
    secret = os.getenv("RAZORPAY_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(503, "Optional webhook secret is not configured")
    payload = await request.body()
    if len(payload) > 1024 * 1024:
        raise HTTPException(413, "Webhook exceeds size limit")
    signature = request.headers.get("x-razorpay-signature", "")
    previous = os.getenv("RAZORPAY_WEBHOOK_PREVIOUS_SECRET", "")
    if not (
        verify_hmac(payload, signature, secret)
        or previous
        and verify_hmac(payload, signature, previous)
    ):
        raise HTTPException(401, "Invalid webhook signature")
    event_id = request.headers.get("x-razorpay-event-id", "")
    if not event_id or len(event_id) > 200:
        raise HTTPException(422, "Webhook event identifier is required")
    try:
        data = json.loads(payload)
        event = data.get("event")
        if not isinstance(event, str) or len(event) > 100:
            raise ValueError()
    except (ValueError, AttributeError):
        raise HTTPException(422, "Invalid webhook event")
    import hashlib

    try:
        return repo.receive_webhook(
            event_id, hashlib.sha256(payload).hexdigest(), event
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc))
