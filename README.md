## Known limitations (Phase 2)

- Classifier was evaluated against a 12-case hand-authored fixture set
  (data/synthetic_fixtures.jsonl), not against the real inbox.
  Real-inbox labelling is deferred to Phase 5's prompt-iteration loop,
  when the eval will be re-run against hand-labelled live mail.
- Sample size is small (n=12). Confidence intervals on 91.7% accuracy
  are wide: roughly [62%, 99%] at 95% confidence. Treat as a smoke
  signal, not a benchmark.
- Calibration is poor: the model returns confidence ≥ 0.95 on
  almost every prediction, including the one it got wrong. Phase 5
  will add few-shot examples with mid-range confidences.
- Urgency='high' recall is 50% (2/4). Acceptable for Phase 3
  (drafting is category-driven); needs tightening before Phase 6's
  priority ordering is built on it.
- The one confusion in the eval was actionable → sensitive, which
  is the safe direction: the email is still escalated to the human,
  not silently dropped.