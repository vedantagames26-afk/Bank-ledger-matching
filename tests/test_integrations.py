import json
import hmac
import hashlib
import httpx
import pytest
from backend.app.integrations import RazorpayClient, IntegrationError


@pytest.fixture
def credentials(monkeypatch):
    monkeypatch.setenv("RAZORPAY_KEY_ID", "test-id")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "test-secret")


@pytest.mark.parametrize(
    "resource,path",
    [
        ("payments", "/v1/payments"),
        ("settlements", "/v1/settlements"),
        ("recon", "/v1/settlements/recon/combined"),
    ],
)
def test_verified_endpoints(credentials, resource, path):
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "entity_id" if resource == "recon" else "id": "source1",
                        "amount": 100,
                        "currency": "INR",
                    }
                ]
            },
        )

    client = RazorpayClient(transport=httpx.MockTransport(handle))
    result = client.fetch(
        resource,
        {"year": 2026, "month": 1} if resource == "recon" else {"from": 1, "to": 2},
    )
    assert (
        result[0]["amount"] == 100
        and seen[0].url.path == path
        and seen[0].headers["authorization"].startswith("Basic ")
    )
    assert client.status()["connected"] and client.status()["connection_tested"]


def test_pagination(credentials):
    seen = []

    def handle(request):
        seen.append(int(request.url.params["skip"]))
        return httpx.Response(
            200,
            json={
                "items": [{"id": str(i), "amount": 100} for i in range(100)]
                if len(seen) == 1
                else []
            },
        )

    assert (
        len(RazorpayClient(transport=httpx.MockTransport(handle)).fetch("payments", {}))
        == 100
    )
    assert seen == [0, 100]


def test_transient_retry(credentials):
    seen = []
    delays = []

    def handle(request):
        seen.append(request)
        return (
            httpx.Response(429, headers={"Retry-After": "1"})
            if len(seen) < 2
            else httpx.Response(200, json={"items": []})
        )

    assert (
        RazorpayClient(
            transport=httpx.MockTransport(handle), sleeper=delays.append
        ).fetch("payments", {})
        == []
    )
    assert delays == [1]


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_errors_are_safe(credentials, status):
    c = RazorpayClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(status, json={"secret": "never expose"})
        ),
        sleeper=lambda n: None,
    )
    with pytest.raises(IntegrationError) as error:
        c.fetch("payments", {})
    assert "never expose" not in str(error.value) and not c.status()["connected"]


def test_schema_error(credentials):
    c = RazorpayClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"items": [{"id": "x"}]})
        )
    )
    with pytest.raises(IntegrationError):
        c.fetch("payments", {})


def test_webhook_signature_deduplication_out_of_order(client, monkeypatch):
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "test-hook-secret")

    def send(event, event_id):
        body = json.dumps(
            {"event": event, "payload": {"sensitive": "not persisted"}}
        ).encode()
        signature = hmac.new(b"test-hook-secret", body, hashlib.sha256).hexdigest()
        return client.post(
            "/api/webhooks/razorpay",
            content=body,
            headers={
                "X-Razorpay-Signature": signature,
                "X-Razorpay-Event-Id": event_id,
            },
        )

    assert send("payment.captured", "hook1").json()["outcome"] == "recorded_not_applied"
    assert send("payment.captured", "hook1").json()["outcome"] == "duplicate_ignored"
    assert send("payment.authorized", "hook2").status_code == 200
    assert send("payment.failed", "hook1").status_code == 409
    assert (
        client.post(
            "/api/webhooks/razorpay",
            content=b"{}",
            headers={"X-Razorpay-Signature": "wrong", "X-Razorpay-Event-Id": "invalid"},
        ).status_code
        == 401
    )
    assert "sensitive" not in json.dumps(client.get("/api/audit").json())


def test_webhook_unconfigured(client, monkeypatch):
    monkeypatch.delenv("RAZORPAY_WEBHOOK_SECRET", raising=False)
    assert client.post("/api/webhooks/razorpay", content=b"{}").status_code == 503
