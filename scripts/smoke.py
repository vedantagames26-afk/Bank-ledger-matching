"""Exercise the running demo through HTTP without external credentials."""

import json
import os
from pathlib import Path
import urllib.request
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
BASE = "http://127.0.0.1:8000/api"


def request(path, body=None):
    headers = {"Content-Type": "application/json"}
    if os.getenv("RECON_ACCESS_TOKEN"):
        headers["X-Recon-Token"] = os.environ["RECON_ACCESS_TOKEN"]
    req = urllib.request.Request(
        BASE + path,
        headers=headers,
        data=json.dumps(body).encode() if body is not None else None,
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read()


assert json.loads(request("/health"))["status"] == "ok"
run = json.loads(request("/runs", {}))
expected = json.loads((ROOT / "data/expected_results.json").read_text())
by_id = {c["left"]["id"]: c for c in run["cases"]}
for group in ("ledger", "settlements"):
    for ident, status in expected[group].items():
        assert by_id[ident]["status"] == status, (ident, by_id[ident]["status"], status)
assert run["metrics"]["bank_count"] >= 100
assert len(
    {
        c["right"]["row_id"]
        for c in run["cases"]
        if c["right"] and c["profile"] != "ledger_razorpay"
    }
) == sum(bool(c["right"]) for c in run["cases"] if c["profile"] != "ledger_razorpay")
assert b"source_amount_paise" in request("/runs/" + run["id"] + "/reports/matched")
case = by_id["L004"]
from urllib.parse import quote

settings = json.loads(request("/settings"))
if settings["gemini"]["state"] == "AI_DISABLED":
    explanation = json.loads(
        request("/runs/" + run["id"] + "/investigate/" + quote(case["id"], safe=""), {})
    )
    assert explanation["provider"] == "rule-based"
else:
    explanation = {"provider": "Live AI not requested by this smoke check"}

print(
    json.dumps(
        {
            "run_id": run["id"],
            "metrics": run["metrics"],
            "investigation_provider": explanation["provider"],
        },
        indent=2,
    )
)
