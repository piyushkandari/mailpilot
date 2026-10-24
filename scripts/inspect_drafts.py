"""Show recent drafts alongside the source message."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mail_pilot.db.repository import connect  # noqa: E402


if __name__ == "__main__":
    conn = connect()
    rows = conn.execute(
        """
        SELECT d.subject, d.confidence, d.gmail_draft_id,
               m.subject AS orig_subject, m.from_addr
        FROM drafts d
        JOIN messages m ON m.id = d.message_id
        ORDER BY d.created_at DESC
        LIMIT 25
        """
    ).fetchall()
    if not rows:
        print("No drafts yet. Run scripts/draft_replies.py first.")
    for r in rows:
        gid = r["gmail_draft_id"][:10] + "…" if r["gmail_draft_id"] else "(none)"
        print(f"{r['confidence']:.2f}  draft={gid:<14}  "
              f"from={ (r['from_addr'] or '')[:22]:<22}  "
              f"re: {(r['orig_subject'] or '')[:55]}")