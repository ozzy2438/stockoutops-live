# Milestone 0 — Planning

> No production code in this milestone. Deliverables are documents, plans, and the ADR framework.

## Deliverables

See the full checklist in `docs/12_backlog_and_milestones.md` under “Milestone 0”.

## How to run M0

1. Orchestrator opens one GitHub Issue per M0 line item using the `milestone_task` template.
2. Assign owner and independent reviewer per RACI in `docs/team/roles.md`.
3. Each deliverable ships as a PR that updates the matching doc under `docs/`.
4. When all M0 items are checked, Orchestrator opens the M0 review PR referencing every merged PR.
5. **Fizz** performs independent review and posts a verdict (APPROVE / APPROVE WITH CONDITIONS / BLOCK) as a PR comment.
6. Osman gives final approval to start M1.

## Exit checklist

- [ ] All 15 M0 items closed.
- [ ] Fizz verdict recorded on the M0 review PR.
- [ ] Osman approval recorded.
- [ ] GitHub Milestones for M1–M5 created with the target dates.
- [ ] Branch protection on `main` verified: required reviews, required status checks, no force-push, no direct commits.

## Artifacts produced in M0 (checklist)

- [ ] `docs/01_current_state_audit.md` populated.
- [ ] `docs/02_gap_matrix.md` populated.
- [ ] `docs/03_scope.md` confirmed with Osman.
- [ ] `docs/04_baseline_plan.md` populated & pre-registered.
- [ ] `docs/05_architecture_v2.md` accepted.
- [ ] `docs/06_workflow_and_tool_contracts.md` accepted.
- [ ] `docs/07_threat_model.md` accepted.
- [ ] `docs/08_evaluation_plan.md` accepted.
- [ ] `docs/09_rollout_plan.md` accepted.
- [ ] `docs/10_observability_slo_cost.md` accepted.
- [ ] `docs/11_failure_injection.md` accepted; ≥ 6 scenarios.
- [ ] ADR-0001 accepted; ADR-0002 (LLM provider) accepted.
- [ ] `docs/13_risks_and_open_decisions.md` current.
- [ ] `docs/artifacts/pii-inventory.md` created.
