"""Classify up to N unclassified messages. Caches, respects budget."""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mail_pilot.classify.budget import RateBudget, RateLimitReached  # noqa: E402
from mail_pilot.classify.classifier import classify_message  # noqa: E402
from mail_pilot.classify.prompts import PROMPT_VERSION  # noqa: E402
from mail_pilot.db.repository import (  # noqa: E402
    connect, init_db, unclassified_messages,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def main(limit: int) -> None:
    init_db()
    conn = connect()
    budget = RateBudget(conn)

    remaining = budget.remaining_today()
    if remaining == 0:
        print("Daily free-tier budget exhausted. Try again tomorrow (UTC).")
        return

    batch = min(limit, remaining)
    rows = unclassified_messages(conn, PROMPT_VERSION, batch)
    if not rows:
        print(f"No unclassified messages at prompt_version={PROMPT_VERSION}.")
        return

    print(f"Classifying {len(rows)} message(s) "
          f"(remaining today: {remaining}, prompt_version={PROMPT_VERSION})")

    ok = 0
    for i, r in enumerate(rows, start=1):
        msg = dict(r)
        try:
            result = classify_message(conn, msg, budget)
        except RateLimitReached as exc:
            print(f"Stopping at {i - 1}/{len(rows)}: {exc}")
            break
        except Exception as exc:
            print(f"[{i}/{len(rows)}] ERROR on {msg['id']}: {exc}")
            continue
        ok += 1
        print(f"[{i}/{len(rows)}] {msg['id'][:12]}… "
              f"cat={result.category.value:<12} urg={result.urgency.value:<6} "
              f"conf={result.confidence:.2f}")

    print(f"\nDone. Classified: {ok}    Remaining today: {budget.remaining_today()}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 10)