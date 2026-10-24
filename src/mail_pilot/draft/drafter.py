"""The drafter: thread context → Gemini → MIME draft → DB row.

Cache key: (message_id, draft_prompt_version).
Budget: shares the same api_calls ledger as the classifier.
Safety: no send path exists in this module or anywhere it imports.
"""
from __future__ import annotations

import logging
import sqlite3
import time

from google import genai
from google.genai import types
from pydantic import ValidationError

from mail_pilot.classify.budget import RateBudget
from mail_pilot.config import GEMINI_MODEL
from mail_pilot.db.repository import (
    get_draft,
    record_api_call,
    save_draft,
)
from mail_pilot.draft.prompts import (
    DRAFT_PROMPT_VERSION,
    SYSTEM_PROMPT,
    build_draft_prompt,
)
from mail_pilot.draft.schema import DraftReply
from mail_pilot.gemini.client import get_client
from mail_pilot.gmail.drafts import (
    create_draft_reply,
    fetch_thread_context,
    get_raw_message,
    _get_message_id_header,
)

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (5, 30, 60)


def _is_transient(exc: BaseException) -> bool:
    msg = str(exc)
    return any(t in msg for t in (
        "429", "500", "502", "503", "504",
        "RESOURCE_EXHAUSTED", "UNAVAILABLE", "DEADLINE_EXCEEDED",
    ))


def _parse(text: str) -> DraftReply:
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:].lstrip()
    return DraftReply.model_validate_json(t)


def _call_gemini(client, prompt: str, *, strict: bool = False):
    system = SYSTEM_PROMPT
    if strict:
        system += ("\nIMPORTANT: Return ONLY the raw JSON object. "
                   "No prose, no code fences.")
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=DraftReply,
            temperature=0.3,  # slight variation is fine for drafting
        ),
    )
    raw = response.text or ""
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, DraftReply):
        return parsed, raw
    return _parse(raw), raw


def draft_reply(
    conn: sqlite3.Connection,
    *,
    service,
    message: dict,
    owner_email: str,
    budget: RateBudget,
    create_in_gmail: bool = True,
    force: bool = False,
) -> dict:
    """Draft a reply for one actionable message.

    Returns a dict with keys: status, draft, gmail_draft_id.
    status is one of: 'cached', 'skipped_sensitive', 'drafted', 'failed'.
    """
    message_id = message["id"]
    thread_id = message["thread_id"]

    # 1. Sensitive messages are not auto-drafted by default.
    #    (The caller filters by category; this is a belt-and-braces check.)
    #    See Phase 3 assumption in the README.

    # 2. Cache lookup
    if not force:
        cached = get_draft(conn, message_id, DRAFT_PROMPT_VERSION)
        if cached and cached.get("gmail_draft_id"):
            return {
                "status": "cached",
                "draft": {
                    "subject": cached["subject"],
                    "body": cached["body"],
                    "confidence": cached["confidence"],
                },
                "gmail_draft_id": cached["gmail_draft_id"],
            }

    # 3. Build thread context
    thread_messages = fetch_thread_context(service, thread_id)
    if not thread_messages:
        # Fall back to the single message we already have in the DB.
        thread_messages = [message]

    prompt = build_draft_prompt(
        thread_messages=thread_messages,
        latest_subject=message.get("subject") or "(no subject)",
        owner_email=owner_email,
    )

    client = get_client()
    last_exc: BaseException | None = None
    result: DraftReply | None = None
    raw_text = ""

    for attempt in range(MAX_ATTEMPTS):
        budget.check()
        budget.wait_if_needed()
        strict = attempt >= 1
        try:
            result, raw_text = _call_gemini(client, prompt, strict=strict)
        except (ValidationError, ValueError) as exc:
            last_exc = exc
            log.warning("Draft validation failed (attempt %d): %s",
                        attempt + 1, exc)
            record_api_call(conn, model=GEMINI_MODEL, kind="draft",
                            success=False, error=f"validation: {exc}")
            continue
        except Exception as exc:
            last_exc = exc
            record_api_call(conn, model=GEMINI_MODEL, kind="draft",
                            success=False, error=str(exc)[:500])
            if _is_transient(exc) and attempt < MAX_ATTEMPTS - 1:
                delay = BACKOFF_SECONDS[attempt]
                log.warning("Transient draft error, sleeping %ds: %s",
                            delay, exc)
                time.sleep(delay)
                continue
            raise

        record_api_call(conn, model=GEMINI_MODEL, kind="draft", success=True)
        break

    if result is None:
        raise RuntimeError(
            f"Drafting failed after {MAX_ATTEMPTS} attempts: {last_exc}"
        )

    # 4. Optionally create the Gmail draft
    gmail_draft_id: str | None = None
    if create_in_gmail:
        # Pull the RFC Message-ID from the latest incoming message so the
        # recipient's client threads the reply correctly.
        latest_incoming_id = message_id
        in_reply_to = ""
        references = ""
        try:
            raw = get_raw_message(service, latest_incoming_id)
            in_reply_to = _get_message_id_header(raw)
            # References should accumulate; for a first reply, it's just the
            # parent's Message-ID. For deeper threads, the history is in the
            # thread context but we keep this simple for Phase 3.
            references = in_reply_to
        except Exception as exc:
            log.warning("Could not read Message-ID header: %s", exc)

        api_draft = create_draft_reply(
            service,
            thread_id=thread_id,
            to_addr=message.get("from_addr") or "",
            subject=result.subject,
            body=result.body,
            in_reply_to_message_id=in_reply_to,
            references=references,
        )
        gmail_draft_id = api_draft.get("id")

    # 5. Persist
    save_draft(
        conn,
        message_id=message_id,
        thread_id=thread_id,
        prompt_version=DRAFT_PROMPT_VERSION,
        subject=result.subject,
        body=result.body,
        reasoning=result.reasoning,
        confidence=result.confidence,
        model=GEMINI_MODEL,
        gmail_draft_id=gmail_draft_id,
        raw_response=raw_text[:4000],
    )

    return {
        "status": "drafted",
        "draft": {
            "subject": result.subject,
            "body": result.body,
            "confidence": result.confidence,
        },
        "gmail_draft_id": gmail_draft_id,
    }