"""Fetch the latest N inbox messages and store them in SQLite."""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mail_pilot.config import GMAIL_FETCH_LIMIT  # noqa: E402
from mail_pilot.gmail.fetch import fetch_and_store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else GMAIL_FETCH_LIMIT
    fetched, inserted = fetch_and_store(limit)
    print(f"Fetched: {fetched}    New in DB: {inserted}    (limit={limit})")