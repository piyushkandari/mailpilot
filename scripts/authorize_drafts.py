"""Re-authorize Gmail with the gmail.compose scope.

Run this once after changing GMAIL_SCOPES in config.py. It deletes the
existing token (forcing a fresh consent) and prints the authorized email.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mail_pilot.config import GMAIL_SCOPES, GMAIL_TOKEN_PATH  # noqa: E402
from mail_pilot.gmail.auth import get_profile_email  # noqa: E402


if __name__ == "__main__":
    print("Scopes requested:")
    for s in GMAIL_SCOPES:
        print(f"  - {s}")
    if GMAIL_TOKEN_PATH.exists():
        print(f"\nDeleting old token: {GMAIL_TOKEN_PATH}")
        GMAIL_TOKEN_PATH.unlink()
    print("\nOpening browser for consent. Approve BOTH scopes.\n")
    email = get_profile_email()
    print(f"\nAuthorized account: {email}")
    print("New token written. Phase 3 drafting can now create drafts.")