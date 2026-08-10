# 08 — Evaluation & Golden-Case Plan

> Owner: Scout. Reviewer: Fizz. Status: **plan; no evaluation has been run for StockoutOps Live**.

## Evaluation layers

1. **Unit / contract tests** — tool schemas, workflow transitions, RLS invariants.
2. **Golden-case regression suite** — curated cases with expected root cause, expected tool set, expected escalation.
3. **Historical replay (G0)** — blind rerun of past resolved cases; correctness + evidence + tool-choice metrics.
4. **Shadow-mode diff (G1)** — live UAT cases analysed by agent without action; diffed against analyst decision.
5. **Assisted operation (G2)** — approve/edit/reject/escalate data.
6. **Failure-injection (M3–M5)** — see `11_failure_injection.md`.
7. **Operator study (G2–G3)** — controlled UAT experiment; see § below.

## Golden cases

Location: `evaluation/golden_cases/`.

Each case is a directory containing:

- `case.yaml` — inputs, tenant, timestamps, feature flags.
- `expected.yaml` — expected root cause, minimum evidence citations, expected tool set (ordered by required precedence), expected escalation flag, forbidden claims.
- `rubric.md` — scoring rubric with weights.
- `notes.md` — provenance (real / synthetic / anonymised).

Minimum coverage before G1 → G2 promotion:

| Category | # of cases |
|----------|-----------:|
| Supplier lead-time miss | ≥ 8 |
| Promotion demand spike | ≥ 8 |
| Data-freshness fault | ≥ 4 |
| Multi-store correlated stockout | ≥ 6 |
| SOP-mandated escalation | ≥ 4 |
| Ambiguous / insufficient evidence | ≥ 4 |
| **Total** | **≥ 34** |

## Metrics per case

- Correct root cause (binary + partial-credit rubric).
- Correct tool set (set match) and correct tool order (Kendall’s tau).
- Evidence completeness (0–1 against rubric).
- Unsupported claims (count; target 0).
- Unnecessary tool calls (count).
- Correct escalation flag (binary).
- Latency (ms).
- Cost (LLM tokens plus attributable AWS/RDS/ECS/S3 usage under the accepted method).

## Aggregate gates

| Gate | Requirement |
|------|-------------|
| G0 → G1 | ≥ 90% correct root cause on golden cases; 0 unsupported claims; 0 RLS leakage. |
| G1 → G2 | Shadow-diff agreement with analyst ≥ 80% on non-ambiguous cases; disagreements characterised. |
| G2 → G3 | Acceptance rate ≥ 70% and reject rate ≤ 10% on assisted runs over ≥ 4 weeks; no SEV1/SEV2 incidents. |
| G3 → G4 | Canary passes SLOs for ≥ 2 weeks; ≥ 3 failure-injection scenarios passed. |

## Operator study (controlled UAT experiment)

- Design: randomised at the case level (with optional crossover per operator) between `manual` and `assisted` arms.
- Cases stratified by severity / velocity band.
- Primary metric: **time to a correct and defensible recommendation**.
- Guardrails: wrong root cause, unsupported claim, excessive human edits, privacy/security failure.
- Pre-registration: metric, sample size, stopping rules signed before data collection begins.
- Reporting: results labelled as *controlled UAT experiment*. **Not** a commercial production A/B test.

## Shadow evaluation of model / prompt changes

Any change to model or prompt bundle triggers:

1. Golden-case rerun in CI (block on regression).
2. 100-case shadow run against the previous version.
3. Fizz review of the diff report before promotion.

## Reporting cadence

- Weekly `evaluation/reports/YYYY-Www-report.md` starting M1.
- Every gate transition produces a signed evaluation report referenced from the milestone PR.
