"""Tools the agent can use."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from langchain_core.tools import tool
from mail_pilot.db.repository import connect

@tool
def search_thread_history(query: str) -> str:
    """Search past emails in the database for keywords. Use this to find past context."""
    conn = connect()
    rows = conn.execute(
        "SELECT subject, body_text FROM messages WHERE body_text LIKE ? OR subject LIKE ? LIMIT 3",
        (f"%{query}%", f"%{query}%")
    ).fetchall()
    conn.close()
    if not rows:
        return f"No past emails found for '{query}'."
    return "\n---\n".join(f"Subject: {r['subject']}\nBody: {r['body_text'][:200]}..." for r in rows)

@tool
def check_calendar(date_str: str) -> str:
    """Check availability for a given date (YYYY-MM-DD). Returns busy/free slots."""
    # Mock calendar for Phase 4. In Phase 7, this would hit the Google Calendar API.
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return "Error: date must be YYYY-MM-DD."
    
    # Hardcode a busy Friday
    if date_str.endswith("24"): # Assuming 24th is a Friday in test
        return "Busy from 10:00 to 11:30 and 14:00 to 15:00. Free otherwise."
    return "Completely free all day."

# THIS IS THE LINE THAT WAS MISSING:
TOOLS = [search_thread_history, check_calendar]