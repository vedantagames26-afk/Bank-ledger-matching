from pathlib import Path
import pytest
from backend.app.ingestion import SOURCES
from backend.app.investigation import Investigator
from backend.app.integrations import razorpay_status, verify_hmac


@pytest.fixture
def run(client):
    response = client.post("/api/runs", json={})
    assert response.status_code == 200, response.text
    return response.json()


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_e2e_review_audit_report(client, run):
    selected = next(c for c in run["cases"] if c["left"]["id"] == "L004")
    response = client.post(
        f"/api/runs/{run['id']}/decisions/{selected['id']}",
        json={
            "action": "reject",
            "actor": "Finance reviewer",
            "note": "Amount discrepancy remains unexplained",
        },
    )
    assert (
        response.status_code == 200 and response.json()["previous_status"] == "REVIEW"
    )
    loaded = client.get("/api/runs/" + run["id"]).json()
    c = next(c for c in loaded["cases"] if c["id"] == selected["id"])
    assert c["status"] == "REVIEW" and c["effective_status"] == "UNMATCHED"
    audits = client.get("/api/audit").json()
    assert any(
        a["action"] == "manual_decision" and a["payload"]["case_id"] == selected["id"]
        for a in audits
    )
    exported = client.get(f"/api/runs/{run['id']}/reports/unmatched_ledger")
    assert (
        exported.status_code == 200
        and "L004" in exported.text
        and "source_amount_paise" in exported.text
    )


def test_upload_reconcile_all_four(client):
    ids = {}
    for s in SOURCES:
        response = client.post(
            "/api/imports/" + s,
            files={
                "file": (
                    s + ".csv",
                    (Path("data") / (s + ".csv")).read_bytes(),
                    "text/csv",
                )
            },
        )
        assert response.status_code == 200, response.text
        ids[s] = response.json()["id"]
        assert client.get("/api/imports/" + ids[s] + "/report").status_code == 200
    response = client.post("/api/runs", json={"import_ids": ids})
    assert (
        response.status_code == 200
        and response.json()["provenance"]["mode"] == "uploaded"
    )


def test_missing_source(client):
    assert (
        client.post(
            "/api/runs", json={"import_ids": {"internal_ledger": "missing"}}
        ).status_code
        == 422
    )


def test_rejected_acknowledgement(client):
    ids = {}
    for s in SOURCES:
        content = (Path("data") / (s + ".csv")).read_bytes()
        if s == "internal_ledger":
            content += b"bad,wrong,abc,direct,,,,,\n"
        r = client.post("/api/imports/" + s, files={"file": ("x.csv", content)})
        ids[s] = r.json()["id"]
    assert client.post("/api/runs", json={"import_ids": ids}).status_code == 422
    assert (
        client.post(
            "/api/runs", json={"import_ids": ids, "acknowledge_rejected": True}
        ).status_code
        == 200
    )


def test_reason_required(client, run):
    c = run["cases"][0]
    assert (
        client.post(
            f"/api/runs/{run['id']}/decisions/{c['id']}",
            json={"action": "confirm", "actor": "Test", "note": ""},
        ).status_code
        == 422
    )


def test_cannot_confirm_no_candidate(client, run):
    c = next(c for c in run["cases"] if not c["right"])
    assert (
        client.post(
            f"/api/runs/{run['id']}/decisions/{c['id']}",
            json={"action": "confirm", "actor": "Test", "note": "Checked"},
        ).status_code
        == 422
    )


def test_disabled_ai_fallback(client, run):
    response = client.post(f"/api/runs/{run['id']}/investigate/{run['cases'][0]['id']}")
    assert (
        response.status_code == 200
        and response.json()["provider"] == "rule-based"
        and response.json()["state"] == "AI_DISABLED"
    )


def test_quota_does_not_break_accounting(run):
    service = Investigator(limit=0)
    service.state = "AI_AVAILABLE"
    result = service.explain(run["cases"][0])
    assert (
        result["state"] == "AI_QUOTA_EXCEEDED"
        and run["cases"][0]["status"] == "MATCHED"
    )


def test_gemini_429(monkeypatch, run):
    from google import genai

    class Quota(Exception):
        code = 429

    def fail(**kwargs):
        raise Quota()

    monkeypatch.setattr(genai, "Client", fail)
    monkeypatch.setenv("GEMINI_API_KEY", "unit-test-only")
    monkeypatch.setenv("GEMINI_MODEL", "unit-test-only")
    service = Investigator()
    assert service.explain(run["cases"][0])["state"] == "AI_QUOTA_EXCEEDED"
    assert service.calls == 1
    service.explain(run["cases"][1])
    assert service.calls == 1


def test_gemini_malformed(monkeypatch, run):
    from google import genai
    from types import SimpleNamespace

    monkeypatch.setenv("GEMINI_API_KEY", "unit-test-only")
    monkeypatch.setenv("GEMINI_MODEL", "test")
    monkeypatch.setattr(
        genai,
        "Client",
        lambda **kw: SimpleNamespace(
            models=SimpleNamespace(
                generate_content=lambda **kw: SimpleNamespace(text="not json")
            )
        ),
    )
    assert Investigator().explain(run["cases"][0])["state"] == "AI_ERROR"


def test_optional_razorpay_unavailable(client):
    assert not razorpay_status()["connected"]
    assert (
        client.post(
            "/api/integrations/razorpay/sync", json={"resource": "payments"}
        ).status_code
        == 503
    )


def test_generic_hmac():
    import hmac, hashlib

    payload = b"body"
    signature = hmac.new(b"secret", payload, hashlib.sha256).hexdigest()
    assert verify_hmac(payload, signature, "secret") and not verify_hmac(
        payload, "wrong", "secret"
    )


def test_untrusted_origin(client):
    assert (
        client.post(
            "/api/runs", json={}, headers={"Origin": "https://malicious.invalid"}
        ).status_code
        == 403
    )


def test_token_access(client, monkeypatch):
    monkeypatch.setenv("RECON_ACCESS_TOKEN", "test-only")
    assert client.get("/api/settings").status_code == 401
    assert (
        client.get("/api/settings", headers={"X-Recon-Token": "test-only"}).status_code
        == 200
    )


@pytest.mark.parametrize(
    "kind",
    [
        "matched",
        "review",
        "unmatched_ledger",
        "unmatched_events",
        "unmatched_settlements",
        "unmatched_bank",
        "partial",
        "duplicates",
        "variances",
        "audit",
    ],
)
def test_reports(client, run, kind):
    response = client.get(f"/api/runs/{run['id']}/reports/{kind}")
    assert response.status_code == 200 and response.headers["content-type"].startswith(
        "text/csv"
    )


def test_upload_size(client):
    response = client.post(
        "/api/imports/internal_ledger",
        files={"file": ("x.csv", b"x" * (5 * 1024 * 1024 + 1))},
    )
    assert response.status_code == 422


def test_unknown_run(client):
    assert client.get("/api/runs/unknown").status_code == 404


def test_negative_cycle_rejected(client):
    assert (
        client.post(
            "/api/runs", json={"config": {"settlement_working_days": -1}}
        ).status_code
        == 422
    )


def test_invalid_calendar_evidence(client):
    assert (
        client.post(
            "/api/runs", json={"config": {"holidays": {"wrong": {"verified": True}}}}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/runs", json={"config": {"weekend_days": [0, 1, 2, 3, 4, 5, 6]}}
        ).status_code
        == 422
    )


def test_investigation_persists(client, run):
    c = run["cases"][0]
    client.post(f"/api/runs/{run['id']}/investigate/{c['id']}")
    loaded = client.get("/api/runs/" + run["id"]).json()
    found = next(r for r in loaded["cases"] if r["id"] == c["id"])
    assert found["investigation"]["provider"] == "rule-based"
    assert all(
        not row.startswith("allocation:")
        for row in found["investigation"]["explanation"]["data_sources_used"]
    )
