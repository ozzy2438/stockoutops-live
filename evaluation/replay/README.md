# Historical replay (Gate 0)

Blind rerun of known-outcome cases in staging.

## Inputs

- Golden cases from `evaluation/golden_cases/`.
- Real anonymised historical incidents (added as data-contract permits).

## Outputs

- Per-case scorecard.
- Aggregate G0 report under `evaluation/reports/gates/G0-<date>.md`.

## CI hook

See `.github/workflows/evaluation.yml`.
