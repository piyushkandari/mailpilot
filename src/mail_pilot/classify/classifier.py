"""The classifier: prompt → Gemini → Pydantic → cache → DB.

Retries only on transient errors (429, 5xx, JSON parse failure). On a
validation failure we retry once with temperature=0 and a stricter system
instruction, then give up loudly.

Phase 7 addition: tracks latency (ms) and token usage for telemetry.
"""
from __future__ import annotations

import logging
import sqlite3
import time

from google import genai
from google.genai import types
from pydantic import ValidationError

from mail_pilot.classify.budget import RateBudget
from mail_pilot.classify.prompts import SYSTEM_PROMPT, PROMPT_VERSION, build_prompt
from mail_pilot.classify.schema import IntentResult
from mail_pilot.config import GEMINI_MODEL
from mail_pilot.db.repository import (
    get_classification,
    record_api_call,
    save_classification,
)
from mail_pilot.gemini.client import get_client

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (5, 30, 60)  # 429 free-tier usually needs ~30s


def _is_transient(exc: BaseException) -> bool:
    msg = str(exc)
    return any(t in msg for t in (
        "429", "500", "502", "503", "504",
        "RESOURCE_EXHAUSTED", "UNAVAILABLE", "DEADLINE_EXCEEDED",
    ))


def _parse_response(text: str) -> IntentResult:
    """Model sometimes wraps JSON in ```json fences. Strip then validate."""
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:].lstrip()
    return IntentResult.model_validate_json(t)


def _call_gemini(client: genai.Client, prompt: str, *, strict: bool = False) -> tuple[IntentResult, str, int]:
    """Call Gemini and return (parsed_result, raw_text, token_count)."""
    system = SYSTEM_PROMPT
    if strict:
        system += ("\nIMPORTANT: Return ONLY the raw JSON object. "
                   "No prose, no code fences, no explanation outside JSON.")
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=IntentResult,
            temperature=0.0,
        ),
    )
    raw = response.text or ""
    
    # Extract token usage for Phase 7 telemetry
    tokens = 0
    if hasattr(response, "usage_metadata") and response.usage_metadata:
        tokens = response.usage_metadata.total_token_count or 0

    # Prefer response.parsed when the SDK provides it; fall back to parsing.
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, IntentResult):
        return parsed, raw, tokens
    return _parse_response(raw), raw, tokens


def classify_message(conn: sqlite3.Connection, msg: dict, budget: RateBudget, *,
                     force: bool = False) -> IntentResult:
    """Classify one message. Uses cache unless force=True."""
    if not force:
        cached = get_classification(conn, msg["id"], PROMPT_VERSION)
        if cached:
            return IntentResult(
                category=cached["category"],
                urgency=cached["urgency"],
                confidence=cached["confidence"],
                reason=cached["reason"],
            )

    prompt = build_prompt(msg)
    client = get_client()

    last_exc: BaseException | None = None
    for attempt in range(MAX_ATTEMPTS):
        budget.check()
        budget.wait_if_needed()

        strict = attempt >= 1  # tighten the instruction after first failure
        start_time = time.time()
        
        try:
            result, raw, tokens = _call_gemini(client, prompt, strict=strict)
        except (ValidationError, ValueError) as exc:
            last_exc = exc
            latency_ms = int((time.time() - start_time) * 1000)
            log.warning("Validation failed (attempt %d): %s", attempt + 1, exc)
            record_api_call(conn, model=GEMINI_MODEL, kind="classify",
                            success=False, error=f"validation: {exc}", 
                            latency_ms=latency_ms, total_tokens=0)
            continue
        except Exception as exc:
            last_exc = exc
            latency_ms = int((time.time() - start_time) * 1000)
            record_api_call(conn, model=GEMINI_MODEL, kind="classify",
                            success=False, error=str(exc)[:500], 
                            latency_ms=latency_ms, total_tokens=0)
            if _is_transient(exc) and attempt < MAX_ATTEMPTS - 1:
                delay = BACKOFF_SECONDS[attempt]
                log.warning("Transient error, sleeping %ds: %s", delay, exc)
                time.sleep(delay)
                continue
            raise

        # Success
        latency_ms = int((time.time() - start_time) * 1000)
        record_api_call(conn, model=GEMINI_MODEL, kind="classify", 
                        success=True, latency_ms=latency_ms, total_tokens=tokens)
        save_classification(
            conn, msg["id"], PROMPT_VERSION,
            category=result.category.value,
            urgency=result.urgency.value,
            confidence=result.confidence,
            reason=result.reason,
            model=GEMINI_MODEL,
            raw_response=raw[:4000],
        )
        return result

    raise RuntimeError(
        f"Classification failed after {MAX_ATTEMPTS} attempts: {last_exc}"
    )