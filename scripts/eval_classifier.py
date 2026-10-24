"""Measure classifier accuracy against the hand-labelled eval set."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mail_pilot.classify.budget import RateBudget, RateLimitReached  # noqa: E402
from mail_pilot.classify.classifier import classify_message  # noqa: E402
from mail_pilot.classify.prompts import PROMPT_VERSION  # noqa: E402
from mail_pilot.config import PROJECT_ROOT  # noqa: E402
from mail_pilot.db.repository import connect, init_db  # noqa: E402

EVAL_PATH = PROJECT_ROOT / "data" / "eval_labels.jsonl"
CATEGORIES = ["informational", "actionable", "sensitive"]
URGENCIES = ["low", "medium", "high"]


def _print_confusion(expected: list[str], predicted: list[str],
                     labels: list[str], title: str) -> None:
    idx = {l: i for i, l in enumerate(labels)}
    m = [[0] * len(labels) for _ in labels]
    for e, p in zip(expected, predicted):
        if e in idx and p in idx:
            m[idx[e]][idx[p]] += 1
    print(f"\n{title}")
    header = "expected\\pred".ljust(14) + " | " + " | ".join(
        l.rjust(13) for l in labels)
    print(header)
    print("-" * len(header))
    for i, l in enumerate(labels):
        row = " | ".join(str(m[i][j]).rjust(13) for j in range(len(labels)))
        print(l.ljust(14) + " | " + row)

    # Per-class precision / recall
    print("\nPer-class:")
    for i, l in enumerate(labels):
        tp = m[i][i]
        fp = sum(m[j][i] for j in range(len(labels))) - tp
        fn = sum(m[i]) - tp
        precision = tp / (tp + fp) if (tp + fp) else float("nan")
        recall = tp / (tp + fn) if (tp + fn) else float("nan")
        f1 = (2 * precision * recall / (precision + recall)
              if precision + recall > 0 else float("nan"))
        print(f"  {l:<14} P={precision:.2f} R={recall:.2f} F1={f1:.2f} n={sum(m[i])}")


def main() -> None:
    if not EVAL_PATH.exists():
        print(f"{EVAL_PATH} missing. Run `python scripts/label_sample.py 20` first.")
        return
    rows = [json.loads(l) for l in EVAL_PATH.read_text().splitlines() if l.strip()]
    labelled = [r for r in rows if r.get("category") and r.get("urgency")]
    skipped = len(rows) - len(labelled)
    if skipped:
        print(f"Skipping {skipped} unlabelled row(s) — fill them in first.")
    if not labelled:
        print("No labelled rows to evaluate.")
        return

    init_db()
    conn = connect()
    budget = RateBudget(conn)

    expected_cat, pred_cat, expected_urg, pred_urg = [], [], [], []
    missing = 0

    for i, r in enumerate(labelled, start=1):
        msg_row = conn.execute(
            "SELECT * FROM messages WHERE id=?", (r["message_id"],)
        ).fetchone()
        if msg_row is None:
            missing += 1
            continue
        try:
            result = classify_message(conn, dict(msg_row), budget)
        except RateLimitReached as exc:
            print(f"Rate limit hit after {i - 1} classifications: {exc}")
            break
        expected_cat.append(r["category"])
        pred_cat.append(result.category.value)
        expected_urg.append(r["urgency"])
        pred_urg.append(result.urgency.value)

    if not expected_cat:
        print("No predictions produced.")
        return

    cat_correct = sum(e == p for e, p in zip(expected_cat, pred_cat))
    urg_correct = sum(e == p for e, p in zip(expected_urg, pred_urg))
    n = len(expected_cat)

    print(f"\nEvaluated {n} message(s). Missing from DB: {missing}")
    print(f"Category accuracy: {cat_correct}/{n} = {cat_correct / n:.1%}")
    print(f"Urgency  accuracy: {urg_correct}/{n} = {urg_correct / n:.1%}")

    _print_confusion(expected_cat, pred_cat, CATEGORIES, "Category confusion")
    _print_confusion(expected_urg, pred_urg, URGENCIES, "Urgency confusion")


if __name__ == "__main__":
    main()