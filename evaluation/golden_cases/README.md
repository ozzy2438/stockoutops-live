# Golden cases

Each case is a directory with:

- `case.yaml` — inputs (tenant, sku_ids, store_ids, timestamps, feature flags).
- `expected.yaml` — expected root cause, required evidence citations, expected tool set (ordered), expected escalation flag, forbidden claims.
- `rubric.md` — scoring rubric with weights.
- `notes.md` — provenance: real / synthetic / anonymised; adjudicators; date.

Minimum coverage before G1→G2 promotion: see `docs/08_evaluation_plan.md`.
