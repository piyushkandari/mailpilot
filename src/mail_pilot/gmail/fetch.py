"""Fetch recent Gmail messages, extract text, and store in SQLite.

Deliberately un-clever. If something is wrong, you can read this file
top-to-bottom in one sitting.
"""
from __future__ import annotations

import base64
import logging
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

from googleapiclient.errors import HttpError

from mail_pilot.db.repository import connect, init_db, upsert_message
from mail_pilot.gmail.auth import get_gmail_service

log = logging.getLogger(__name__)


# ---------- body extraction ------------------------------------------------

class _HTMLTextExtractor(HTMLParser):
    """Strip tags from text/html. Skips <script> and <style> contents."""
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self._chunks.append(data)

    def text(self) -> str:
        return " ".join(" ".join(self._chunks).split())


def _decode_body_data(part: dict) -> str:
    """base64url-decode a part's body. Handles missing padding & charset."""
    data = (part.get("body") or {}).get("data")
    if not data:
        return ""
    padded = data + "=" * (-len(data) % 4)
    raw = base64.urlsafe_b64decode(padded)

    charset = "utf-8"
    for h in part.get("headers") or []:
        if h.get("name", "").lower() == "content-type":
            for piece in h.get("value", "").split(";"):
                piece = piece.strip()
                if piece.lower().startswith("charset="):
                    charset = piece.split("=", 1)[1].strip().strip('"')
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def _extract_body(payload: dict) -> str:
    """Walk the MIME tree; prefer text/plain, fall back to stripped text/html."""
    parts = payload.get("parts") or []

    if payload.get("mimeType") == "text/plain":
        text = _decode_body_data(payload)
        if text.strip():
            return text

    # Prefer direct text/plain children (multipart/alternative usually pairs
    # plain + html at the same level).
    for part in parts:
        if part.get("mimeType") == "text/plain":
            text = _decode_body_data(part)
            if text.strip():
                return text

    # Recurse into nested multiparts (multipart/mixed, multipart/related).
    for part in parts:
        text = _extract_body(part)
        if text.strip():
            return text

    # Last resort: strip HTML.
    if payload.get("mimeType") == "text/html":
        return _strip_html(_decode_body_data(payload))
    for part in parts:
        if part.get("mimeType") == "text/html":
            return _strip_html(_decode_body_data(part))

    return ""


def _strip_html(html: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(html)
    return parser.text()


# ---------- parsing --------------------------------------------------------

def _get_header(headers: list[dict], name: str) -> str:
    name = name.lower()
    for h in headers or []:
        if h.get("name", "").lower() == name:
            return h.get("value", "")
    return ""


def parse_message(raw: dict) -> dict:
    """Turn one Gmail `users.messages.get` response into our DB dict."""
    payload = raw.get("payload") or {}
    headers = payload.get("headers") or []

    internal_ms_str = raw.get("internalDate")
    internal_ms = int(internal_ms_str) if internal_ms_str else None

    return {
        "id": raw["id"],
        "thread_id": raw["threadId"],
        "from_addr": _get_header(headers, "From"),
        "to_addr": _get_header(headers, "To"),
        "subject": _get_header(headers, "Subject"),
        "snippet": raw.get("snippet") or "",
        "body_text": _extract_body(payload),
        "internal_date": internal_ms,
        "labels": raw.get("labelIds") or [],
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------- fetching -------------------------------------------------------

def _retry(callable_, *, attempts: int = 3, base_delay: float = 1.0):
    """Retry on transient Gmail errors (5xx, 429) with exponential backoff."""
    for i in range(attempts):
        try:
            return callable_()
        except HttpError as exc:
            status = exc.resp.status if exc.resp else 0
            transient = status >= 500 or status == 429
            if not transient or i == attempts - 1:
                raise
            delay = base_delay * (2 ** i)
            log.warning("Gmail %s, retrying in %.1fs", status, delay)
            time.sleep(delay)


def list_message_ids(service, limit: int) -> list[str]:
    """Return up to `limit` message ids from the user's inbox, newest first."""
    resp = _retry(lambda: (
        service.users().messages().list(
            userId="me",
            maxResults=min(limit, 500),
            labelIds=["INBOX"],
        ).execute()
    ))
    return [m["id"] for m in (resp.get("messages") or [])][:limit]


def fetch_message(service, msg_id: str) -> dict:
    raw = _retry(lambda: (
        service.users().messages().get(
            userId="me",
            id=msg_id,
            format="full",
        ).execute()
    ))
    return parse_message(raw)


def fetch_and_store(limit: int) -> tuple[int, int]:
    """Return (fetched_ok, inserted_new)."""
    init_db()
    service = get_gmail_service()

    ids = list_message_ids(service, limit)
    log.info("Listed %d message ids", len(ids))

    conn = connect()
    fetched, inserted = 0, 0
    try:
        for i, msg_id in enumerate(ids, start=1):
            try:
                parsed = fetch_message(service, msg_id)
            except HttpError as exc:
                log.error("Failed to fetch %s: %s", msg_id, exc)
                continue
            fetched += 1
            if upsert_message(conn, parsed):
                inserted += 1
            if i % 10 == 0:
                conn.commit()  # flush incrementally for long runs
        conn.commit()
    finally:
        conn.close()
    return fetched, inserted