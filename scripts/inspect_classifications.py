"""Print recent classifications alongside the original messages."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mail_pilot.db.repository import connect  # noqa: E402


if __name__ == "__main__":
    conn = connect()
    rows = conn.execute(
        """
        SELECT c.message_id, c.category, c.urgency, c.confidence,
               m.subject, m.from_addr
        FROM classifications c
        JOIN messages m ON m.id = c.message_id
        ORDER BY c.classified_at DESC
        LIMIT 25
        """
    ).fetchall()
    if not rows:
        print("No classifications yet. Run scripts/classify_emails.py first.")
    for r in rows:
        print(f"{r['confidence']:.2f}  {r['category']:<13} {r['urgency']:<6}  "
              f"{(r['from_addr'] or '')[:25]:<25}  {(r['subject'] or '')[:50]}")