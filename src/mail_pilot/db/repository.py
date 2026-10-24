"""SQLite access layer for Mail Pilot.

Phase 1: messages table (upsert, count).
Phase 2: classifications table + api_calls table (cache + call budget).

Design choices worth knowing:
- Connection opened per call (cheap in SQLite) so scripts do not share state.
- WAL mode enabled on first connect -> concurrent readers later (FastAPI, Phase 6).
- INSERT ... ON CONFLICT DO NOTHING makes fetch idempotent.
- All timestamps stored as UTC ISO8601 'YYYY-MM-DDTHH:MM:SSZ' strings so
  SQLite's strftime/date functions compare correctly without parsing.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from mail_pilot.config import DB_PATH

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


# ---------- connection & schema -------------------------------------------

def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    # WAL = write-ahead logging: one writer, many readers, no "database is
    # locked" surprises once FastAPI is reading in Phase 6.
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db(db_path: Path | None = None) -> None:
    conn = connect(db_path)
    try:
        conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()


# ---------- Phase 1: messages ---------------------------------------------

def upsert_message(conn: sqlite3.Connection, msg: dict) -> bool:
    """Insert a message if its id is new. Returns True if inserted."""
    cur = conn.execute(
        """
        INSERT INTO messages
            (id, thread_id, from_addr, to_addr, subject, snippet,
             body_text, internal_date, labels, fetched_at)
        VALUES (:id, :thread_id, :from_addr, :to_addr, :subject, :snippet,
                :body_text, :internal_date, :labels, :fetched_at)
        ON CONFLICT(id) DO NOTHING
        """,
        {**msg, "labels": json.dumps(msg.get("labels") or [])},
    )
    return cur.rowcount == 1


def count_messages(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]


# ---------- Phase 2: classification + call budget -------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_classification(conn: sqlite3.Connection, message_id: str,
                       prompt_version: int) -> dict | None:
    """Return the cached classification for (message_id, prompt_version)."""
    row = conn.execute(
        "SELECT * FROM classifications WHERE message_id=? AND prompt_version=?",
        (message_id, prompt_version),
    ).fetchone()
    return dict(row) if row else None


def save_classification(conn: sqlite3.Connection, message_id: str,
                        prompt_version: int, *, category: str, urgency: str,
                        confidence: float, reason: str, model: str,
                        raw_response: str) -> None:
    """Insert or update a classification row."""
    conn.execute(
        """
        INSERT INTO classifications
            (message_id, prompt_version, category, urgency, confidence,
             reason, model, classified_at, raw_response)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(message_id, prompt_version) DO UPDATE SET
            category=excluded.category,
            urgency=excluded.urgency,
            confidence=excluded.confidence,
            reason=excluded.reason,
            model=excluded.model,
            classified_at=excluded.classified_at,
            raw_response=excluded.raw_response
        """,
        (message_id, prompt_version, category, urgency, confidence,
         reason, model, _now_iso(), raw_response),
    )
    conn.commit()


def record_api_call(conn: sqlite3.Connection, *, model: str, kind: str,
                    success: bool, error: str | None = None) -> None:
    """Log one Gemini (or other) API call for budget accounting."""
    conn.execute(
        "INSERT INTO api_calls (called_at, model, kind, success, error) "
        "VALUES (?, ?, ?, ?, ?)",
        (_now_iso(), model, kind, 1 if success else 0, error),
    )
    conn.commit()


def calls_last_minute(conn: sqlite3.Connection) -> int:
    """Number of API calls in the trailing 60 seconds."""
    row = conn.execute(
        "SELECT COUNT(*) FROM api_calls "
        "WHERE called_at > strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-60 seconds')"
    ).fetchone()
    return int(row[0])


def calls_today(conn: sqlite3.Connection) -> int:
    """Number of API calls since UTC midnight."""
    row = conn.execute(
        "SELECT COUNT(*) FROM api_calls "
        "WHERE substr(called_at, 1, 10) = date('now')"
    ).fetchone()
    return int(row[0])


def oldest_call_in_last_minute(conn: sqlite3.Connection) -> str | None:
    """Timestamp of the oldest call within the trailing 60s window."""
    row = conn.execute(
        "SELECT MIN(called_at) FROM api_calls "
        "WHERE called_at > strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-60 seconds')"
    ).fetchone()
    return row[0] if row and row[0] else None


def unclassified_messages(conn: sqlite3.Connection, prompt_version: int,
                          limit: int) -> list[sqlite3.Row]:
    """Messages that have no classification at this prompt_version, newest first."""
    return conn.execute(
        """
        SELECT m.*
        FROM messages m
        LEFT JOIN classifications c
            ON c.message_id = m.id AND c.prompt_version = ?
        WHERE c.message_id IS NULL
        ORDER BY m.internal_date DESC
        LIMIT ?
        """,
        (prompt_version, limit),
    ).fetchall()


# ---------- Phase 3: drafts ----------------------------------------------

def get_draft(conn: sqlite3.Connection, message_id: str,
              prompt_version: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM drafts WHERE message_id=? AND prompt_version=?",
        (message_id, prompt_version),
    ).fetchone()
    return dict(row) if row else None


def save_draft(conn: sqlite3.Connection, message_id: str, thread_id: str,
               prompt_version: int, *, subject: str, body: str,
               reasoning: str, confidence: float, model: str,
               gmail_draft_id: str | None, raw_response: str) -> None:
    conn.execute(
        """
        INSERT INTO drafts
            (message_id, thread_id, prompt_version, subject, body, reasoning,
             confidence, model, gmail_draft_id, created_at, raw_response)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(message_id, prompt_version) DO UPDATE SET
            subject=excluded.subject,
            body=excluded.body,
            reasoning=excluded.reasoning,
            confidence=excluded.confidence,
            model=excluded.model,
            gmail_draft_id=excluded.gmail_draft_id,
            created_at=excluded.created_at,
            raw_response=excluded.raw_response
        """,
        (message_id, thread_id, prompt_version, subject, body, reasoning,
         confidence, model, gmail_draft_id, _now_iso(), raw_response),
    )
    conn.commit()

def actionable_messages_without_drafts(
    conn: sqlite3.Connection,
    classification_prompt_version: int,
    draft_prompt_version: int,
    limit: int,
) -> list[sqlite3.Row]:
    """Actionable messages that have no draft at this draft_prompt_version.

    Excludes synthetic-* ids: those are Phase 2 fixtures that were inserted
    into `messages` only to satisfy the classifications FK. They have no
    Gmail thread behind them, so attempting threads.get on them returns
    HttpError 400 Invalid id value.
    """
    return conn.execute(
        """
        SELECT m.*, c.category, c.urgency
        FROM messages m
        JOIN classifications c
            ON c.message_id = m.id
           AND c.prompt_version = ?
        LEFT JOIN drafts d
            ON d.message_id = m.id
           AND d.prompt_version = ?
        WHERE c.category = 'actionable'
          AND d.message_id IS NULL
          AND m.id NOT LIKE 'synthetic-%'
        ORDER BY m.internal_date DESC
        LIMIT ?
        """,
        (classification_prompt_version, draft_prompt_version, limit),
    ).fetchall()