"""Central place for paths and environment loading.

Why a module instead of reading os.environ everywhere:
- One import point for dotenv.
- Paths are resolved relative to the project root, so scripts work
  regardless of the current working directory.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Project root is the parent of src/mail_pilot/
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY")

GMAIL_CREDENTIALS_PATH = PROJECT_ROOT / os.getenv(
    "GMAIL_CREDENTIALS_PATH", "credentials/credentials.json"
)
GMAIL_TOKEN_PATH = PROJECT_ROOT / os.getenv(
    "GMAIL_TOKEN_PATH", "credentials/token.json"
)

# Phase 0 scope: read-only. Draft/send scopes are added only in Phase 3/6.
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Free-tier primary model: most generous observed limits (~15 RPM / 500 RPD).
# Keep the model name here so later phases can swap it without hunting.
GEMINI_MODEL = "gemini-3.5-flash-lite"

DB_PATH = PROJECT_ROOT / os.getenv("DB_PATH", "mail_pilot.db")

# How many recent messages to fetch per run. Kept configurable so Phase 2
# can experiment with 10 (cheap, fast) vs 100 (better accuracy eval set).
GMAIL_FETCH_LIMIT = int(os.getenv("GMAIL_FETCH_LIMIT", "20"))