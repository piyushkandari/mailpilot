"""Quick eyeball check on the SQLite contents."""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mail_pilot.db.repository import connect, count_messages  # noqa: E402


if __name__ == "__main__":
    conn = connect()
    print(f"Total messages in DB: {count_messages(conn)}\n")

    rows = conn.execute(
        """
        SELECT from_addr, subject, internal_date, length(body_text) AS body_len
        FROM messages
        ORDER BY internal_date DESC
        LIMIT 10
        """
    ).fetchall()

    for r in rows:
        ts = (
            datetime.fromtimestamp(r["internal_date"] / 1000, tz=timezone.utc)
            .strftime("%Y-%m-%d %H:%M")
            if r["internal_date"] else "?"
        )
        print(f"{ts}  from={r['from_addr'][:35]:<35}  "
              f"body_len={r['body_len']:>5}  subj={r['subject'][:60]}")