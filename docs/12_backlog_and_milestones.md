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

Issue and PR state are the live gate record; this static file does not duplicate their changing checkboxes. M0 approval accepts the planning scaffold as the handoff baseline. It does **not** implement the architecture or silently accept OD-01 through OD-13. An open decision in `13_risks_and_open_decisions.md` gates only work that depends on its still-open scope; the narrow M1 subsets accepted below do not close the broader production decisions.

## Milestone 1 — Smallest human-supervised vertical slice

> **Authoritative owner scope.** M1 is one local/containerised engineering slice over one canonical simulated stockout case. It is not G0, staging, production operation, or evidence of model quality or business impact.

### Scope-locked path

1. Accept one investigation request and persist one durable `run_id`.
2. Resolve simulated identity, tenant, and role server-side; fail closed on invalid or cross-tenant access.
3. Retrieve only T1 inventory, T2 sales/demand, and T3 supplier evidence from governed versioned fixtures.
4. Validate 3/3 evidence freshness, contract, provenance, and citation IDs before reasoning.
5. Invoke the OpenAI Responses API at most once per normal run, using exact snapshot `gpt-4.1-mini-2025-04-14`, no tools, and strict structured output for only a cited root-cause hypothesis and recommendation draft. CI uses a deterministic stub only.
6. Present cited findings through the minimal review surface and persist Approve / Edit / Reject / Escalate.
7. Append every accepted transition and rejected control attempt to the audit trail.
8. Resume safely after restart and retry without duplicate internal actions.

### M1 subset decision mapping

The ADRs accept only the following local M1 subsets. `docs/13` remains the source of truth for the broader open decisions.

| Open decision | Accepted M1 subset | Scope that remains open after this PR |
|---|---|---|
| OD-01 | ADR-0002: OpenAI Responses API, exact `gpt-4.1-mini-2025-04-14` snapshot, strict output, no tools | Provider fallback, replacement-model choice, production provider strategy |
| OD-02 | ADR-0003: explicit Python state machine for one local single-writer slice | Distributed workflow engine, scheduling, leasing, and multi-writer recovery |
| OD-03 | ADR-0004: local PostgreSQL 16 state, audit, idempotency, and provenance subset | RLS, outbox, backup/PITR, restore drill, production schema and recovery |
| OD-05 | ADR-0005: local server-derived simulated identity and tenant fixtures | Real IdP, sessions, MFA, RBAC, provisioning, and production tenant model |
| OD-06 | ADR-0003: one same-origin server-rendered Jinja review page | Production UI technology, accessibility, browser security, and routing |
| OD-07 | ADR-0004: fixture-backed T1–T3 canonical-case contracts only | Real source systems, dbt-core boundary, T4–T6, and production freshness agreements |
| OD-13 | ADR-0004: T1–T3 `v1` fields, provenance, freshness, and citation rules only | Acceptance of the broader v2 tool catalogue and evidence rubric |

OD-04 and OD-08 through OD-12 remain fully open. They do not authorise additional M1 work; any future dependent work stays blocked until its own decision gate is satisfied.

### Work packages and dependencies

- [ ] M1-SL — Documentation scope lock: issue, ADR-0002–0005, this checklist, exact-head Fizz `APPROVE`, merge, and Ozzy implementation approval.
- [ ] M1-I1 — Bumble implementation PR: explicit control spine, local PostgreSQL, simulated identity, T1–T3 fixtures, bounded adapters, API and minimal review page. **Blocked by M1-SL.**
- [ ] M1-E1 — Scout evidence PR: clean-container run, exact-head CI, fixture hashes, structured result, UI smoke artefact, restart/retry result, audit export, limitations, measured live-call latency/tokens/cost where authorised. **Blocked by M1-I1.**
- [ ] M1-A1 — Fizz final milestone assurance on the exact evidence head. `APPROVE` is the only passing verdict.

### Definition of Done

- One accepted request retains one `run_id` across process restart.
- Missing/invalid identity and cross-tenant requests fail closed; measured fixture leakage is zero.
- T1–T3 retrieval is 3/3 and claim citation coverage is 100%; stale, missing, invalid, or provenance-incomplete evidence stops before the model.
- CI uses only the deterministic stub. Before the sole manual live smoke, Bumble verifies credential, billing/project, and exact-snapshot access without exposing or persisting the key.
- A normal run makes no more than one model call. Strict-schema, citation, refusal, timeout, and budget failures are rejected, audited, and escalated.
- Approve / Edit / Reject / Escalate are all persisted with reviewer, tenant, timestamps, reason where required, original/edited payload where applicable, and bound draft hash/expiry.
- The append-only audit reconstructs the current state; mutation attempts are rejected.
- Repeated intake/review requests create zero duplicate runs, decisions, or model invocations. This is an internal-action result; M1 performs no external write.
- Evidence includes reproducible local/container commands, exact commit, fixture manifest/hashes, structured output, audit export, UI smoke artefact, security/privacy and cost notes, recovery/rollback, and documented limitations.
- Fizz returns `APPROVE` on the exact evidence head. Tests alone do not complete M1.

### Explicitly out of scope

AWS deployment; T4–T7; external tasks or notifications; ≥34-case suite; full IdP, session, MFA, or RLS; distributed workflow execution; production operation; adoption, ROI, SLO, or reasoning-quality claims.

### Deferred from the former large M1

The former M1-01–M1-10 package is preserved but is not executable M1 authority. Framework hardening, T4–T6, registries beyond required version pins, ≥34 golden cases, regression gating, dashboards, AWS staging/auth/RBAC, baseline measurement, and G0 reporting require later owner sequencing after this slice. They must not be pulled into M1 without a written scope decision.

## Milestone 2 — Shadow Mode (G1)

> Issue #17 delivered the merged M2-01/M2-02 engineering foundation (PR #18).
> That issue remains open because M2/G1 is not complete.
>
> Issue #19 is authorised only for the UAT / real-shadow readiness bridge:
> canonical missing-evidence measurement, future genuine-case contract, intake,
> templates, and first-100 collection tooling. It does not recruit users, wire
> SLO alerts, collect 100 genuine cases, or complete G1.

- [x] M2-01 — Shadow processor engineering foundation merged (`execute=false`, PR #18). Not G1 exit.
- [x] M2-02 — Deterministic diff-report engineering foundation merged (PR #18). Not G1 exit.
- [ ] M2-03 — UAT user recruitment (≥ 3) + consent forms.
- [ ] M2-04 — SLO alerts wired.
- [ ] M2-05 — First 100 genuine shadow cases analysed; disagreement characterisation.
- [ ] M2-06 — G1 exit gate report + Fizz `APPROVE`.

## Milestone 3 — Assisted Operation (G2)

- [ ] M3-01 — Production hardening of the M1 review UI, identity, accessibility, and escalation routing.
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
