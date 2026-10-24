"""Phase 0 sanity check: prove the Gemini API key works."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mail_pilot.gemini.client import quick_check  # noqa: E402


if __name__ == "__main__":
    text = quick_check()
    print("Gemini response:", text)