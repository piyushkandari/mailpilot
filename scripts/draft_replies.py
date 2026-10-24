"""Draft replies for actionable messages. Creates Gmail drafts, never sends."""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mail_pilot.classify.budget import RateBudget, RateLimitReached  # noqa: E402
from mail_pilot.classify.prompts import PROMPT_VERSION as CLS_PROMPT_VERSION  # noqa: E402
from mail_pilot.db.repository import (  # noqa: E402
    actionable_messages_without_drafts, connect, init_db,
)
from mail_pilot.draft.drafter import draft_reply  # noqa: E402
from mail_pilot.draft.prompts import DRAFT_PROMPT_VERSION  # noqa: E402
from mail_pilot.gmail.auth import get_gmail_service, get_profile_email  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def main(limit: int, *, create_in_gmail: bool = True) -> None:
    init_db()
    conn = connect()
    budget = RateBudget(conn)

    owner_email = get_profile_email()
    service = get_gmail_service()

    rows = actionable_messages_without_drafts(
        conn, CLS_PROMPT_VERSION, DRAFT_PROMPT_VERSION, limit
    )
    if not rows:
        print("No actionable messages without drafts. Nothing to do.")
        return

    print(f"Drafting {len(rows)} message(s) "
          f"(remaining today: {budget.remaining_today()})")
    print(f"Owner: {owner_email}")
    print(f"Create in Gmail: {create_in_gmail}\n")

    ok = skipped = failed = 0
    for i, r in enumerate(rows, start=1):
        msg = dict(r)
        try:
            out = draft_reply(
                conn,
                service=service,
                message=msg,
                owner_email=owner_email,
                budget=budget,
                create_in_gmail=create_in_gmail,
            )
        except RateLimitReached as exc:
            print(f"\nStopping at {i - 1}/{len(rows)}: {exc}")
            break
        except Exception as exc:
            failed += 1
            print(f"[{i}/{len(rows)}] FAILED {msg['id'][:12]}…: {exc}")
            continue

        if out["status"] == "cached":
            print(f"[{i}/{len(rows)}] cached   {msg['id'][:12]}…")
        else:
            ok += 1
            subj = out["draft"]["subject"][:40]
            print(f"[{i}/{len(rows)}] drafted  {msg['id'][:12]}…  "
                  f"conf={out['draft']['confidence']:.2f}  {subj}")

    print(f"\nDone. Drafted: {ok}    Skipped: {skipped}    Failed: {failed}    "
          f"Remaining today: {budget.remaining_today()}")


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    create = "--no-gmail" not in sys.argv
    main(limit, create_in_gmail=create)