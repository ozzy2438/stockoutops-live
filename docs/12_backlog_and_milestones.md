# 12 — Backlog & Milestones

> Owner: Orchestrator. This is the ordered spine of the project. Every item becomes a GitHub Issue using the `milestone_task` template.

## Milestone 0 — Planning (this milestone)

> **No production code.** Deliverables are documents and plans.

- [ ] M0-01 — Current-state audit filled in (`docs/01_current_state_audit.md`) — owner: Orchestrator.
- [ ] M0-02 — Gap-to-deliverable matrix populated (`docs/02_gap_matrix.md`) — owner: Orchestrator + Scout.
- [ ] M0-03 — Scope definition confirmed with Osman (`docs/03_scope.md`) — owner: Orchestrator.
- [ ] M0-04 — Baseline measurement plan (`docs/04_baseline_plan.md`) — owner: Scout.
- [ ] M0-05 — Architecture v2 proposal (`docs/05_architecture_v2.md`) — owner: Honey.
- [ ] M0-06 — Workflow state & tool contracts (`docs/06_workflow_and_tool_contracts.md`) — owner: Honey.
- [ ] M0-07 — Threat model & privacy (`docs/07_threat_model.md`) — owner: Honey.
- [ ] M0-08 — Evaluation & golden-case plan (`docs/08_evaluation_plan.md`) — owner: Scout.
- [ ] M0-09 — Rollout plan G0→G4 (`docs/09_rollout_plan.md`) — owner: Bumble + Scout.
- [ ] M0-10 — Observability, SLO & cost plan (`docs/10_observability_slo_cost.md`) — owner: Bumble.
- [ ] M0-11 — Failure-injection scenarios v1 (`docs/11_failure_injection.md`) — owner: Fizz + Bumble.
- [ ] M0-12 — Prioritised issue & milestone breakdown (this doc, plus GitHub Milestones created).
- [ ] M0-13 — Risks, assumptions & open decisions (`docs/13_risks_and_open_decisions.md`) — owner: Orchestrator.
- [ ] M0-14 — ADR framework initialised (`docs/decisions/`) with ADR-0001 and ADR-0002 stub.
- [ ] M0-15 — Fizz independent review of M0 with verdict APPROVE / APPROVE WITH CONDITIONS / BLOCK.

**Exit criteria M0:** all above checked and Osman approves start of M1.

## Milestone 1 — Historical Replay (G0)

- [ ] M1-01 — Skeleton repo layout for `src/` finalised (framework choice ADR merged).
- [ ] M1-02 — Deterministic outer loop (intake, guardrails, workflow engine, audit).
- [ ] M1-03 — Tool layer T1–T6 implemented under contracts; T7 as draft-only.
- [ ] M1-04 — Prompt / tool / model registry.
- [ ] M1-05 — Golden-case suite (≥ 34 cases) + replay harness.
- [ ] M1-06 — CI wires golden-case suite (block on regression).
- [ ] M1-07 — Observability wiring + operational dashboard v1.
- [ ] M1-08 — Cloud deployment (staging) with auth + RBAC.
- [ ] M1-09 — Baseline measurement run on manual investigations.
- [ ] M1-10 — G0 exit gate report + Fizz verdict.

## Milestone 2 — Shadow Mode (G1)

- [ ] M2-01 — Shadow processor implemented (`execute=false`).
- [ ] M2-02 — Diff-report tooling.
- [ ] M2-03 — UAT user recruitment (≥ 3) + consent forms.
- [ ] M2-04 — SLO alerts wired.
- [ ] M2-05 — First 100 shadow cases analysed; disagreement characterisation.
- [ ] M2-06 — G1 exit gate report + Fizz verdict.

## Milestone 3 — Assisted Operation (G2)

- [ ] M3-01 — Approve / edit / reject / escalate UI.
- [ ] M3-02 — Write executor (T7 realisation) with idempotency.
- [ ] M3-03 — Feature flags & fast rollback.
- [ ] M3-04 — First failure-injection round (FI-1, FI-2, FI-3).
- [ ] M3-05 — Operator study protocol pre-registered.
- [ ] M3-06 — 4-week assisted operation with weekly reports.
- [ ] M3-07 — G2 exit gate report + Fizz verdict.

## Milestone 4 — Low-Risk Canary (G3)

- [ ] M4-01 — Canary slice defined (workload / risk category).
- [ ] M4-02 — Automated approved-task creation for canary.
- [ ] M4-03 — Failure-injection round 2 (FI-4, FI-5, FI-6).
- [ ] M4-04 — At least one real incident post-mortem.
- [ ] M4-05 — Canary passes SLOs ≥ 2 weeks.
- [ ] M4-06 — G3 exit gate report + Fizz verdict.

## Milestone 5 — Controlled Operation (G4)

- [ ] M5-01 — 8–12 weeks continuous operation.
- [ ] M5-02 — Monthly cost report.
- [ ] M5-03 — Baseline vs assisted comparison report.
- [ ] M5-04 — Operator-study results published (as *controlled UAT experiment*).
- [ ] M5-05 — System card finalised.
- [ ] M5-06 — Fizz final verdict + honest live-status label committed.

## Cross-cutting continuous work

- ADR maintenance.
- Runbook maintenance.
- Weekly evaluation reports.
- Dependency updates via Dependabot.
- Threat-model diff on any relevant PR.
