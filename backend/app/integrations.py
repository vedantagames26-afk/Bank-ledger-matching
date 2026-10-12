"""Read-only Razorpay client verified against official documentation.
See docs/integrations.md for endpoint contracts and the verification date.
"""

import os
import hmac
import hashlib
import time
import httpx


class IntegrationError(ValueError):
    pass


class RazorpayClient:
    ENDPOINTS = {
        "payments": "/payments",
        "settlements": "/settlements",
        "recon": "/settlements/recon/combined",
    }

    def __init__(self, transport=None, sleeper=time.sleep):
        self.transport, self.sleeper = transport, sleeper
        self.tested, self.connected, self.last_outcome = False, False, "Not tested"

    def status(self):
        configured = bool(
            os.getenv("RAZORPAY_KEY_ID") and os.getenv("RAZORPAY_KEY_SECRET")
        )
        return {
            "configured": configured,
            "connection_tested": self.tested,
            "connected": self.connected,
            "state": "AVAILABLE_NOT_TESTED"
            if configured and not self.tested
            else "CONNECTED"
            if self.connected
            else "NOT_CONFIGURED"
            if not configured
            else "CONNECTION_ERROR",
            "message": "Read-only payments, settlements and reconciliation fetching. Account permissions apply. "
            + self.last_outcome,
            "webhooks_configured": bool(os.getenv("RAZORPAY_WEBHOOK_SECRET")),
        }

    def fetch(self, resource, params, max_pages=20):
        if resource not in self.ENDPOINTS:
            raise IntegrationError("Unsupported resource")
        key, secret = os.getenv("RAZORPAY_KEY_ID"), os.getenv("RAZORPAY_KEY_SECRET")
        if not key or not secret:
            raise IntegrationError("Optional Razorpay credentials are not configured")
        allowed = {"year", "month", "day"} if resource == "recon" else {"from", "to"}
        if set(params) - allowed:
            raise IntegrationError("Unsupported query parameter")
        if resource == "recon" and not {"year", "month"}.issubset(params):
            raise IntegrationError("Reconciliation fetching requires year and month")
        count = 1000 if resource == "recon" else 100
        output = []
        self.tested = True
        self.connected = False
        try:
            with httpx.Client(
                base_url="https://api.razorpay.com/v1",
                auth=(key, secret),
                timeout=15,
                transport=self.transport,
                follow_redirects=False,
            ) as client:
                for page in range(max_pages):
                    query = {**params, "count": count, "skip": page * count}
                    for attempt in range(3):
                        response = client.get(self.ENDPOINTS[resource], params=query)
                        if (
                            response.status_code not in (429, 500, 502, 503, 504)
                            or attempt == 2
                        ):
                            break
                        retry = response.headers.get("retry-after", "")
                        delay = (
                            min(float(retry), 5)
                            if retry.replace(".", "", 1).isdigit()
                            else 2**attempt
                        )
                        self.sleeper(delay)
                    if response.status_code != 200:
                        raise IntegrationError(
                            f"Razorpay request failed (HTTP {response.status_code}); check account permissions, credentials or rate limits"
                        )
                    body = response.json()
                    items = body.get("items")
                    if not isinstance(items, list):
                        raise IntegrationError(
                            "Razorpay returned an unsupported collection schema"
                        )
                    for item in items:
                        identity = "entity_id" if resource == "recon" else "id"
                        if (
                            not isinstance(item, dict)
                            or not isinstance(item.get(identity), str)
                            or not isinstance(item.get("amount"), int)
                            or isinstance(item.get("amount"), bool)
                        ):
                            raise IntegrationError(
                                "Required Razorpay response fields are missing or malformed"
                            )
                        if item.get("currency", "INR") != "INR":
                            raise IntegrationError(
                                "Only INR is supported; foreign currencies require a separate workflow"
                            )
                    output.extend(items)
                    if len(items) < count:
                        self.connected = True
                        self.last_outcome = "Last explicit fetch succeeded"
                        return output
            raise IntegrationError(
                "Pagination safety limit reached; narrow the requested date range. No partial data imported."
            )
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            self.last_outcome = "Last explicit fetch failed"
            if isinstance(exc, IntegrationError):
                raise
            raise IntegrationError(
                "Razorpay network or response error; no data imported"
            ) from exc


razorpay = RazorpayClient()


def razorpay_status():
    return razorpay.status()


def verify_hmac(payload: bytes, signature: str, secret: str) -> bool:
    return bool(secret) and hmac.compare_digest(
        hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest(), signature
    )
