# Evaluation

All evaluation artifacts live here.

## Layout

```text
evaluation/
├── golden_cases/     # curated cases with expected outcomes (G0 + regression)
├── replay/           # G0 historical-replay harness
├── shadow/           # G1 shadow-mode diffs (agent vs analyst)
├── uat/              # G2 assisted-operation & operator-study records
└── reports/          # weekly & gate-transition evaluation reports
```

See `docs/08_evaluation_plan.md` for methodology and gate criteria.

## Rules

- Every case is labelled MEASURED / SIMULATED / ASSUMED / TARGET.
- Golden-case updates require Scout + Fizz review.
- Any change to metric definitions requires an ADR.
