"""Gmail draft creation and thread-context fetching.

This module is the ONLY place in the codebase that touches drafts.create.
It does not expose a send function. If you find `drafts.send` or
`messages.send` anywhere in this repo, it is a bug.
"""
from __future__ import annotations

import base64
import logging
from email.message import EmailMessage

from googleapiclient.errors import HttpError

from mail_pilot.gmail.fetch import _retry, parse_message

log = logging.getLogger(__name__)


def fetch_thread_context(service, thread_id: str) -> list[dict]:
    """Return every message in the thread, oldest first, parsed to our shape."""
    raw_thread = _retry(lambda: (
        service.users().threads().get(
            userId="me",
            id=thread_id,
            format="full",
        ).execute()
    ))
    messages = raw_thread.get("messages") or []
    parsed = [parse_message(m) for m in messages]
    parsed.sort(key=lambda m: m.get("internal_date") or 0)
    return parsed


def _get_message_id_header(raw_message: dict) -> str:
    """Extract the RFC Message-ID header from a Gmail message payload."""
    headers = (raw_message.get("payload") or {}).get("headers") or []
    for h in headers:
        if h.get("name", "").lower() == "message-id":
            return h.get("value", "")
    return ""


def create_draft_reply(
    service,
    *,
    thread_id: str,
    to_addr: str,
    subject: str,
    body: str,
    in_reply_to_message_id: str = "",
    references: str = "",
) -> dict:
    """Create a Gmail draft attached to `thread_id`. NEVER sends.

    Returns the API Draft object: {"id": ..., "message": {"id": ..., ...}}
    """
    msg = EmailMessage()
    # Gmail fills "From" from the authenticated account automatically; setting
    # it explicitly here avoids some clients showing "From: me".
    msg["To"] = to_addr
    msg["Subject"] = subject
    if in_reply_to_message_id:
        msg["In-Reply-To"] = in_reply_to_message_id
        msg["References"] = references or in_reply_to_message_id
    msg.set_content(body)

    raw_bytes = msg.as_bytes()
    encoded = base64.urlsafe_b64encode(raw_bytes).decode("ascii")

    draft_body = {
        "message": {
            "raw": encoded,
            "threadId": thread_id,
        }
    }

    try:
        draft = service.users().drafts().create(
            userId="me", body=draft_body
        ).execute()
    except HttpError as exc:
        log.error("drafts.create failed: %s", exc)
        raise

    return draft


def get_raw_message(service, message_id: str) -> dict:
    """Fetch a full message (used to read the Message-ID header for threading)."""
    return _retry(lambda: (
        service.users().messages().get(
            userId="me", id=message_id, format="full"
        ).execute()
    ))