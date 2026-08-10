# 12 — Backlog & Milestones

> Owner: Orchestrator. This is the authoritative milestone checklist and gate process. Work normally starts from a GitHub Issue; an owner-authorised consolidation issue may cover a bounded close-out package.

## Verdict semantics

- `APPROVE` is the only Fizz verdict that satisfies a milestone gate and permits merge.
- `APPROVE WITH CONDITIONS` pauses merge and progression. Resolve every condition, rerun required checks, and obtain Fizz `APPROVE` on the new exact head.
- `BLOCK` stops the milestone until the blockers are resolved and the new exact head is reviewed.
- Passing tests or recording a non-approval verdict never completes a milestone.

## Milestone 0 — Planning (this milestone)

> **No production code.** Deliverables are documents and plans.

### Planning-package contents

These checks mean the scaffold artifact is populated and ready for the consolidated M0 gate. They do not claim that a proposed architecture choice is implemented or that an open decision is accepted.

- [x] M0-01 — Current-state audit populated (`docs/01_current_state_audit.md`).
- [x] M0-02 — Gap-to-deliverable matrix populated (`docs/02_gap_matrix.md`).
- [x] M0-03 — Owner scope and constraints recorded (`docs/03_scope.md`).
- [x] M0-04 — Baseline measurement plan recorded (`docs/04_baseline_plan.md`).
- [x] M0-05 — AWS-targeted Architecture v2 proposal recorded (`docs/05_architecture_v2.md`).
- [x] M0-06 — Workflow-state and proposed v2 tool-contract baseline recorded (`docs/06_workflow_and_tool_contracts.md`).
- [x] M0-07 — Threat-model and privacy proposal recorded (`docs/07_threat_model.md`).
- [x] M0-08 — Evaluation and golden-case plan recorded (`docs/08_evaluation_plan.md`).
- [x] M0-09 — Rollout plan G0→G4 recorded (`docs/09_rollout_plan.md`).
- [x] M0-10 — Observability, SLO, and cost plan recorded (`docs/10_observability_slo_cost.md`).
- [x] M0-11 — Six initial failure-injection designs recorded (`docs/11_failure_injection.md`); none is claimed as executed.
- [x] M0-12 — Prioritised backlog and milestone breakdown recorded in this document.
- [x] M0-13 — Risks, assumptions, and open decisions recorded (`docs/13_risks_and_open_decisions.md`).
- [x] M0-14 — ADR framework initialised with accepted ADR-0001 and a deliberately deferred ADR-0002 stub.

### Authoritative M0 acceptance gate

M0 is approved only when all of the following live evidence exists:

1. The owner-authorised consolidation issue defines the M0-only scope and acceptance criteria.
2. Its PR targets `main`, contains no application/test/service implementation, and includes the required threat-model diff.
3. Required CI and Markdown checks pass on the exact PR head.
4. Fizz records `APPROVE` for that exact head. A conditional verdict pauses merge; `BLOCK` stops the milestone.
5. The PR is squash-merged and the authoritative files are verified on GitHub `main`.
6. Osman explicitly records that M0 is approved and M1 may begin.

Issue and PR state are the live gate record; this static file does not duplicate their changing checkboxes. M0 approval accepts the planning scaffold as the handoff baseline. It does **not** implement the architecture or silently accept OD-01 through OD-13. Each deferred decision in `13_risks_and_open_decisions.md` gates its dependent M1 work.

## Milestone 1 — Historical Replay (G0)

- [ ] M1-01 — Skeleton repo layout for `src/` finalised (framework choice ADR merged).
- [ ] M1-02 — Deterministic outer loop (intake, guardrails, workflow engine, audit).
- [ ] M1-03 — Tool layer T1–T6 implemented under the accepted v2 contracts; T7 remains draft-only.
- [ ] M1-04 — Prompt / tool / model registry.
- [ ] M1-05 — Golden-case suite (≥ 34 cases) + replay harness.
- [ ] M1-06 — CI wires golden-case suite (block on regression).
- [ ] M1-07 — Observability wiring + operational dashboard v1.
- [ ] M1-08 — Cloud deployment (staging) with auth + RBAC.
- [ ] M1-09 — Baseline measurement run on manual investigations.
- [ ] M1-10 — G0 exit gate report + Fizz `APPROVE`.

## Milestone 2 — Shadow Mode (G1)

- [ ] M2-01 — Shadow processor implemented (`execute=false`).
- [ ] M2-02 — Diff-report tooling.
- [ ] M2-03 — UAT user recruitment (≥ 3) + consent forms.
- [ ] M2-04 — SLO alerts wired.
- [ ] M2-05 — First 100 shadow cases analysed; disagreement characterisation.
- [ ] M2-06 — G1 exit gate report + Fizz `APPROVE`.

## Milestone 3 — Assisted Operation (G2)

- [ ] M3-01 — Approve / edit / reject / escalate UI.
- [ ] M3-02 — Write executor (T7 realisation) with idempotency.
- [ ] M3-03 — Feature flags & fast rollback.
- [ ] M3-04 — First failure-injection round (FI-1, FI-2, FI-3).
- [ ] M3-05 — Operator study protocol pre-registered.
- [ ] M3-06 — 4-week assisted operation with weekly reports.
- [ ] M3-07 — G2 exit gate report + Fizz `APPROVE`.

## Milestone 4 — Low-Risk Canary (G3)

- [ ] M4-01 — Canary slice defined (workload / risk category).
- [ ] M4-02 — Automated approved-task creation for canary.
- [ ] M4-03 — Failure-injection round 2 (FI-4, FI-5, FI-6).
- [ ] M4-04 — At least one real incident post-mortem.
- [ ] M4-05 — Canary passes SLOs ≥ 2 weeks.
- [ ] M4-06 — G3 exit gate report + Fizz `APPROVE`.

## Milestone 5 — Controlled Operation (G4)

- [ ] M5-01 — 8–12 weeks continuous operation.
- [ ] M5-02 — Monthly cost report.
- [ ] M5-03 — Baseline vs assisted comparison report.
- [ ] M5-04 — Operator-study results published (as *controlled UAT experiment*).
- [ ] M5-05 — System card finalised.
- [ ] M5-06 — Fizz final `APPROVE` + honest live-status label committed.

## Cross-cutting continuous work

- ADR maintenance.
- Runbook maintenance.
- Weekly evaluation reports.
- Dependency updates via Dependabot.
- Threat-model diff on any relevant PR.
