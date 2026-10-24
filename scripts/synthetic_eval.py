"""Evaluate the classifier on hand-authored fixtures.

Why the FK error happened last time and what's different now:
- classifications.message_id has a FOREIGN KEY to messages.id.
- Synthetic messages were not in the messages table, so save_classification
  raised sqlite3.IntegrityError.
- Fix: upsert each synthetic message into `messages` before classifying.
  Synthetic ids are prefixed with "synthetic-" so they never collide with
  real Gmail ids, and can be cleaned up with:
      DELETE FROM messages WHERE id LIKE 'synthetic-%';
      DELETE FROM classifications WHERE message_id LIKE 'synthetic-%';
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mail_pilot.classify.budget import RateBudget, RateLimitReached  # noqa: E402
from mail_pilot.classify.classifier import classify_message  # noqa: E402
from mail_pilot.config import PROJECT_ROOT  # noqa: E402
from mail_pilot.db.repository import (  # noqa: E402
    connect, init_db, upsert_message,
)

FIXTURES_PATH = PROJECT_ROOT / "data" / "synthetic_fixtures.jsonl"
CATEGORIES = ["informational", "actionable", "sensitive"]
URGENCIES = ["low", "medium", "high"]


def _write_default_fixtures() -> None:
    if FIXTURES_PATH.exists():
        return
    FIXTURES_PATH.parent.mkdir(parents=True, exist_ok=True)
    fixtures = [
        {"subject": "Your AWS bill for October",
         "body": "Your monthly invoice is ready. No action is required.",
         "category": "informational", "urgency": "low"},
        {"subject": "Weekly newsletter — tech roundup",
         "body": "Here are this week's top articles. Unsubscribe at any time.",
         "category": "informational", "urgency": "low"},
        {"subject": "Your order has shipped",
         "body": "Tracking number: XYZ. Estimated delivery: 3 days.",
         "category": "informational", "urgency": "low"},
        {"subject": "Re: Can you review the PR by Friday?",
         "body": "Hi, just checking in — I need your sign-off before we merge.",
         "category": "actionable", "urgency": "medium"},
        {"subject": "Coffee next week?",
         "body": "Free Tuesday or Thursday afternoon? Let me know what works.",
         "category": "actionable", "urgency": "low"},
        {"subject": "Project kickoff — confirm attendance",
         "body": "Please confirm whether you can attend the kickoff on Monday at 10am.",
         "category": "actionable", "urgency": "medium"},
        {"subject": "Action required: update your payment method",
         "body": "Your card ending in 4242 expires soon. Update it to avoid interruption.",
         "category": "actionable", "urgency": "high"},
        {"subject": "Security alert: new sign-in",
         "body": "We detected a sign-in from a new device in another country. If this wasn't you, secure your account immediately.",
         "category": "sensitive", "urgency": "high"},
        {"subject": "Tax documents ready for download",
         "body": "Your 1099 form is available. Handle it securely.",
         "category": "sensitive", "urgency": "medium"},
        {"subject": "Unusual account activity — verify now",
         "body": "We noticed unusual activity. Verify your identity within 24 hours to avoid suspension.",
         "category": "sensitive", "urgency": "high"},
        {"subject": "Medical appointment reminder",
         "body": "Your appointment is on 15 Nov at 09:30 with Dr. Patel. Reply to reschedule.",
         "category": "sensitive", "urgency": "medium"},
        {"subject": "Invoice #1042 due in 7 days",
         "body": "Amount due: $1,240. Pay by 30 Oct to avoid late fees.",
         "category": "sensitive", "urgency": "high"},
    ]
    with FIXTURES_PATH.open("w", encoding="utf-8") as f:
        for fixture in fixtures:
            f.write(json.dumps(fixture) + "\n")
    print(f"Wrote {len(fixtures)} default fixtures to {FIXTURES_PATH}")


def _print_confusion(expected, predicted, labels, title) -> None:
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

    print("\nPer-class:")
    for i, l in enumerate(labels):
        tp = m[i][i]
        fp = sum(m[j][i] for j in range(len(labels))) - tp
        fn = sum(m[i]) - tp
        precision = tp / (tp + fp) if (tp + fp) else float("nan")
        recall = tp / (tp + fn) if (tp + fn) else float("nan")
        f1 = (2 * precision * recall / (precision + recall)
              if precision + recall > 0 else float("nan"))
        print(f"  {l:<14} P={precision:.2f} R={recall:.2f} F1={f1:.2f} "
              f"n={sum(m[i])}")


def main() -> None:
    _write_default_fixtures()
    init_db()
    conn = connect()
    budget = RateBudget(conn)

    fixtures = [json.loads(l) for l in FIXTURES_PATH.read_text().splitlines() if l.strip()]
    print(f"Running {len(fixtures)} synthetic fixtures\n")

    expected_cat, pred_cat, expected_urg, pred_urg = [], [], [], []
    for i, fx in enumerate(fixtures, start=1):
        msg = {
            "id": f"synthetic-{i}",
            "thread_id": f"synthetic-thread-{i}",
            "from_addr": "sender@example.com",
            "to_addr": None,
            "subject": fx["subject"],
            "body_text": fx["body"],
            "snippet": fx["body"][:100],
            "internal_date": None,
            "labels": [],
            "fetched_at": "1970-01-01T00:00:00Z",
        }
        # Persist into messages so the FK from classifications passes.
        upsert_message(conn, msg)

        try:
            result = classify_message(conn, msg, budget)
        except RateLimitReached as exc:
            print(f"Rate limit at fixture {i}: {exc}")
            break

        expected_cat.append(fx["category"])
        pred_cat.append(result.category.value)
        expected_urg.append(fx["urgency"])
        pred_urg.append(result.urgency.value)

        mark = "OK " if result.category.value == fx["category"] else "XX "
        print(f"{mark}[{i:2d}] {fx['subject'][:45]:<45} "
              f"exp={fx['category']:<13} got={result.category.value:<13} "
              f"conf={result.confidence:.2f}")

    if not expected_cat:
        print("No predictions produced.")
        return

    cat_correct = sum(e == p for e, p in zip(expected_cat, pred_cat))
    urg_correct = sum(e == p for e, p in zip(expected_urg, pred_urg))
    n = len(expected_cat)

    print(f"\nEvaluated {n} fixtures")
    print(f"Category accuracy: {cat_correct}/{n} = {cat_correct / n:.1%}")
    print(f"Urgency  accuracy: {urg_correct}/{n} = {urg_correct / n:.1%}")

    _print_confusion(expected_cat, pred_cat, CATEGORIES, "Category confusion")
    _print_confusion(expected_urg, pred_urg, URGENCIES, "Urgency confusion")


if __name__ == "__main__":
    main()