"""Phase 0 sanity check: complete Gmail OAuth and print the account email."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mail_pilot.gmail.auth import get_profile_email  # noqa: E402


if __name__ == "__main__":
    email = get_profile_email()
    print(f"Gmail OAuth OK. Authorized account: {email}")