-- messages: one row per Gmail message.
-- Design notes:
--   * id is Gmail's message id -> natural PK -> idempotent upserts.
--   * body_text holds only the extracted text/plain; raw MIME is not stored
--     in Phase 1 (keeps the DB small; we can always re-fetch a message).
--   * internal_date is INTEGER epoch-ms for cheap ordering.
--   * labels are stored as a JSON string; SQLite JSON1 can query it later.

CREATE TABLE IF NOT EXISTS messages (
    id            TEXT PRIMARY KEY,
    thread_id     TEXT NOT NULL,
    from_addr     TEXT,
    to_addr       TEXT,
    subject       TEXT,
    snippet       TEXT,
    body_text     TEXT,
    internal_date INTEGER,
    labels        TEXT,          -- JSON array, e.g. ["INBOX","UNREAD"]
    fetched_at    TEXT NOT NULL  -- ISO8601 UTC
);

CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id);
CREATE INDEX IF NOT EXISTS idx_messages_date   ON messages(internal_date DESC);

-- Cache of LLM classifications, keyed by (message_id, prompt_version).
-- Bumping prompt_version invalidates the cache without losing history.
CREATE TABLE IF NOT EXISTS classifications (
    message_id     TEXT NOT NULL,
    prompt_version INTEGER NOT NULL,
    category       TEXT NOT NULL,
    urgency        TEXT NOT NULL,
    confidence     REAL NOT NULL,
    reason         TEXT,
    model          TEXT NOT NULL,
    classified_at  TEXT NOT NULL,
    raw_response   TEXT,
    PRIMARY KEY (message_id, prompt_version),
    FOREIGN KEY (message_id) REFERENCES messages(id)
);

-- Every Gemini call, successful or not. Drives the daily/RPM budget.
CREATE TABLE IF NOT EXISTS api_calls (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    called_at TEXT NOT NULL,   -- ISO8601 UTC 'YYYY-MM-DDTHH:MM:SSZ'
    model     TEXT NOT NULL,
    kind      TEXT NOT NULL,   -- 'classify' for now
    success   INTEGER NOT NULL,
    error     TEXT
);

CREATE INDEX IF NOT EXISTS idx_api_calls_time ON api_calls(called_at);