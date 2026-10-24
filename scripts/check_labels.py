"""Validate data/eval_labels.jsonl and count how many rows are labelled."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mail_pilot.config import PROJECT_ROOT  # noqa: E402

EVAL_PATH = PROJECT_ROOT / "data" / "eval_labels.jsonl"


def main() -> None:
    if not EVAL_PATH.exists():
        print(f"Missing {EVAL_PATH}. Run `python scripts/label_sample.py 20` first.")
        return

    labelled = 0
    malformed = 0
    total = 0
    for i, line in enumerate(EVAL_PATH.read_text().splitlines(), 1):
        s = line.strip()
        if not s:
            continue
        total += 1
        try:
            r = json.loads(s)
        except json.JSONDecodeError as e:
            print(f"BAD line {i}: {e.msg} at col {e.colno}")
            print(f"  {s}")
            malformed += 1
            continue
        ok = bool(r.get("category") and r.get("urgency"))
        mark = "*" if ok else " "
        print(f"{mark} {i:2d}  cat={str(r.get('category')):<15} "
              f"urg={str(r.get('urgency')):<8}  "
              f"{(r.get('subject_hint') or '')[:50]}")
        if ok:
            labelled += 1

    print(f"\nTotal rows: {total}    Labelled: {labelled}    "
          f"Malformed: {malformed}")


if __name__ == "__main__":
    main()