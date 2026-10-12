"""On-demand, bounded Gemini explanation; deterministic results are never modified."""

import hashlib
import json
import os
import threading
import time
from pydantic import BaseModel, Field, ConfigDict


class Explanation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    summary: str = Field(max_length=2000)
    evidence_considered: list[str] = Field(max_length=30)
    supporting_evidence: list[str] = Field(max_length=30)
    contradicting_evidence: list[str] = Field(max_length=30)
    missing_evidence: list[str] = Field(max_length=30)
    plausible_explanations: list[str] = Field(max_length=10)
    recommended_action: str = Field(max_length=2000)
    reasoning_confidence: float = Field(ge=0, le=1)
    requires_human_review: bool
    data_sources_used: list[str] = Field(max_length=30)


class Investigator:
    def __init__(self, limit=10):
        self.limit, self.calls = limit, 0
        self.cache, self.lock = {}, threading.Lock()
        self.state = (
            "AI_AVAILABLE"
            if os.getenv("GEMINI_API_KEY") and os.getenv("GEMINI_MODEL")
            else "AI_DISABLED"
        )

    def explain(self, case):
        fallback = {
            "provider": "rule-based",
            "state": self.state,
            "explanation": {
                "case_id": case["id"],
                "summary": case["reason"],
                "evidence_considered": list(
                    (case.get("evidence") or {}).get("breakdown", {})
                ),
                "supporting_evidence": ["Genuine shared reference"]
                if (case.get("evidence") or {}).get("shared_references")
                else [],
                "contradicting_evidence": (case.get("evidence") or {}).get(
                    "contradictions", []
                ),
                "missing_evidence": (case.get("evidence") or {}).get(
                    "missing_evidence", []
                ),
                "plausible_explanations": [],
                "recommended_action": case["recommended_action"],
                "reasoning_confidence": 0.0,
                "requires_human_review": case["status"] != "MATCHED",
                "data_sources_used": [case["left"]["row_id"]]
                + (
                    [r["row_id"] for r in case["right"].get("members", [case["right"]])]
                    if case["right"]
                    else []
                ),
            },
        }
        # Send minimal evidence, not customer names or raw financial source payloads.
        payload = {
            "case_id": case["id"],
            "status": case["status"],
            "reason": case["reason"],
            "evidence": case["evidence"],
            "source_ids": fallback["explanation"]["data_sources_used"],
        }
        key = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        with self.lock:
            if key in self.cache:
                return self.cache[key]
            if self.state != "AI_AVAILABLE":
                return fallback
            if self.calls >= self.limit:
                self.state = "AI_QUOTA_EXCEEDED"
                fallback["state"] = self.state
                return fallback
            self.calls += 1
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(
                api_key=os.environ["GEMINI_API_KEY"],
                http_options=types.HttpOptions(
                    timeout=15000, retry_options=types.HttpRetryOptions(attempts=1)
                ),
            )
            for attempt in range(2):
                try:
                    response = client.models.generate_content(
                        model=os.environ["GEMINI_MODEL"],
                        contents="Explain this financial case using only supplied evidence. Cite source IDs. Never invent facts, change accounting status, or assert unverified holidays. All plausible explanations are hypotheses.\n"
                        + json.dumps(payload),
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=Explanation,
                            temperature=0,
                        ),
                    )
                    break
                except Exception as transient:
                    if (
                        getattr(transient, "code", None) not in (500, 502, 503, 504)
                        or attempt == 1
                    ):
                        raise
                    with self.lock:
                        if self.calls >= self.limit:
                            raise
                        self.calls += 1
                    retry = getattr(transient, "response", None)
                    header = (
                        retry.headers.get("retry-after", "")
                        if retry is not None
                        else ""
                    )
                    time.sleep(
                        min(float(header), 3)
                        if header.replace(".", "", 1).isdigit()
                        else 1
                    )
            explanation = Explanation.model_validate_json(response.text)
            if (
                explanation.case_id != case["id"]
                or not explanation.data_sources_used
                or not set(explanation.data_sources_used).issubset(
                    set(payload["source_ids"])
                )
            ):
                raise ValueError("Unsupported source citation")
            result = {
                "provider": "Gemini (advisory)",
                "state": "AI_AVAILABLE",
                "explanation": explanation.model_dump(),
            }
            with self.lock:
                self.cache[key] = result
            return result
        except Exception as exc:
            code = getattr(exc, "code", None)
            self.state = "AI_QUOTA_EXCEEDED" if code == 429 else "AI_ERROR"
            fallback["state"] = self.state
            return fallback
