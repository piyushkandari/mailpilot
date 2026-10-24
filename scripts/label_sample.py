"""Generate a template eval set: pick N random messages for you to hand-label.

Fills data/eval_labels.jsonl with:
  {"message_id": "...", "subject_hint": "...", "category": null, "urgency": null}

Open the file in your editor and replace null with real labels.
Do NOT let the classifier see this file at labeling time — label first.
"""
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mail_pilot.config import PROJECT_ROOT  # noqa: E402
from mail_pilot.db.repository import connect  # noqa: E402

OUT_PATH = PROJECT_ROOT / "data" / "eval_labels.jsonl"


def main(n: int) -> None:
    conn = connect()
    rows = conn.execute(
        "SELECT id, subject FROM messages ORDER BY RANDOM() LIMIT ?", (n,)
    ).fetchall()
    if not rows:
        print("No messages in DB. Run `python scripts/fetch_emails.py 100` first.")
        return

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, dict] = {}
    if OUT_PATH.exists():
        for line in OUT_PATH.read_text().splitlines():
            if line.strip():
                rec = json.loads(line)
                existing[rec["message_id"]] = rec

    added = 0
    with OUT_PATH.open("a", encoding="utf-8") as f:
        for r in rows:
            if r["id"] in existing:
                continue
            f.write(json.dumps({
                "message_id": r["id"],
                "subject_hint": (r["subject"] or "")[:80],
                "category": None,
                "urgency": None,
            }) + "\n")
            added += 1

    print(f"Wrote {added} new template rows to {OUT_PATH}")
    print(f"Total in file: {len(existing) + added}")
    print("Now open the file and fill in category/urgency for each row.")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 20)