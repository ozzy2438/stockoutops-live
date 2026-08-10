# Context Handoff — for the next expert

> Read this first if you are the specialist Osman brought in to execute the plan.

This repository is a **Milestone 0 scaffold**. No production code has been written yet by design. Your job is to work **through** this scaffold, not around it.

## What has been decided (do not re-open without an ADR)

- Project name, purpose, and phase (see `README.md`, `docs/00_project_charter.md`).
- Initial autonomy = **A2 approve-to-act** (see `README.md` §3).
- Scope in / out (see `docs/03_scope.md`).
- Rollout gates G0→G4 with exit criteria (see `docs/09_rollout_plan.md`).
- 7 allow-listed tools with contract-first design (see `docs/06_workflow_and_tool_contracts.md`).
- STRIDE-based threat model with AI-specific threats (see `docs/07_threat_model.md`).
- Evaluation methodology: golden cases + historical replay + shadow diff + controlled UAT experiment (see `docs/08_evaluation_plan.md`).
- Observability signals, SLOs and cost model (see `docs/10_observability_slo_cost.md`).
- 6 failure-injection scenarios (see `docs/11_failure_injection.md`).
- Honest labelling rule: never write *production-proven* without real users + sustained operation.

## What is still open (needs your ADRs)

- **ADR-0002** LLM provider & model family.
- **ADR-0003** Workflow engine (adopt vs build).
- **ADR-0004** Hosting target & region.
- **ADR-0005** Cost-attribution method.
- **ADR-0006** Retention policy for LLM prompt/response bodies.
- **OD-06** UAT consent form.
- **OD-07** Operator-study primary-metric operational definition.

See `docs/13_risks_and_open_decisions.md`.

## Recommended order of work (M0 close-out → M1 kickoff)

1. Read `README.md`, then `docs/00_project_charter.md` → `docs/13_risks_and_open_decisions.md` in order.
2. Perform the current-state audit against the PharmaRetail codebase and fill in `docs/01_current_state_audit.md`.
3. Populate `docs/02_gap_matrix.md` from that audit.
4. Draft the four pending ADRs (0002–0005) and get Honey + Fizz sign-off.
5. Open one GitHub Issue per M0 line item in `docs/12_backlog_and_milestones.md` (use the `milestone_task` template).
6. Request the Fizz M0 review PR; capture the verdict.
7. Only after Osman’s approval, create the `src/` skeleton per the target layout in `src/README.md`.

## Rules you must follow

- No direct push to `main`. Issue → Branch → PR → independent review → merge.
- No new external dependency without an ADR.
- No claim about users, incidents, latency, cost or business impact without a MEASURED / SIMULATED / ASSUMED / TARGET label.
- Passing tests ≠ milestone completion.
- Fizz has authority to block a release.
- Zero RLS leakage is a release-blocker; treat any regression as SEV1.

## How to ask for changes to the plan

Open a `feature` issue that:

1. States which line of the plan you want to change.
2. Explains why (evidence, not preference).
3. References the ADR you’ll create.
4. Names the required reviewers per `.github/CODEOWNERS` and `docs/team/roles.md`.

If in doubt, escalate to Osman — do not silently deviate.
