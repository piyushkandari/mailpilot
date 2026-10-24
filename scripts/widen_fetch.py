"""One-off script: fetch messages from every Gmail label to grow the corpus.

Why this exists: the inbox alone often has very few messages on a new account.
Gmail keeps mail across multiple system labels (SENT, CATEGORY_*, etc.), and
pulling them all gives a much larger pool for the Phase 2 eval set.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mail_pilot.gmail.auth import get_gmail_service  # noqa: E402
from mail_pilot.gmail.fetch import _retry, parse_message  # noqa: E402
from mail_pilot.db.repository import connect, init_db, upsert_message  # noqa: E402


def main() -> None:
    init_db()
    svc = get_gmail_service()

    labels = (
        "INBOX",
        "SENT",
        "CATEGORY_PROMOTIONS",
        "CATEGORY_UPDATES",
        "CATEGORY_SOCIAL",
        "CATEGORY_PERSONAL",
    )

    ids: list[str] = []
    for label in labels:
        try:
            resp = _retry(lambda: svc.users().messages().list(
                userId="me",
                maxResults=200,
                labelIds=[label],
            ).execute())
            got = [m["id"] for m in (resp.get("messages") or [])]
            print(f"{label:<22} {len(got)}")
            ids += got
        except Exception as e:
            print(f"{label:<22} ERROR {e}")

    # Dedup while preserving order — Gmail sometimes lists a message under
    # multiple labels (e.g. INBOX + CATEGORY_PERSONAL).
    ids = list(dict.fromkeys(ids))

    conn = connect()
    inserted = 0
    for i, mid in enumerate(ids, 1):
        raw = _retry(lambda: svc.users().messages().get(
            userId="me",
            id=mid,
            format="full",
        ).execute())
        if upsert_message(conn, parse_message(raw)):
            inserted += 1
        if i % 10 == 0:
            conn.commit()

    conn.commit()
    conn.close()
    print(f"\nTotal unique ids: {len(ids)}    Inserted new: {inserted}")


if __name__ == "__main__":
    main()