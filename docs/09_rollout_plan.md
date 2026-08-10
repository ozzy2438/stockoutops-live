# 09 — Rollout Plan (Historical replay → Shadow → Assisted UAT → Canary → Controlled)

> Owner: Bumble (execution) + Scout (evidence) + Fizz (verdict). Status: **plan; no gate has started**.

## Gate 0 — Historical replay

- Environment: staging.
- Input: known-outcome real + controlled-synthetic stockout cases (blind to agent).
- Purpose: verify correctness, tool choice/order, evidence completeness, escalation logic, no unsupported claims, no unnecessary tool calls, policy compliance.
- Exit criteria: aggregate gate G0→G1 in `docs/08_evaluation_plan.md`.
- Rollback: N/A (no external effect).

## Gate 1 — Shadow mode

- Environment: staging with production-shaped data OR prod with `execute=false` flag.
- Behaviour: agent analyses live UAT cases; **produces no external actions**.
- Measurement: side-by-side diff against analyst decision; agreement, missed evidence, hypothetical impact.
- Exit criteria: G1→G2 gate met.
- Rollback: disable shadow processor via feature flag.

## Gate 2 — Assisted operation

- Environment: prod, feature-flagged for named UAT users.
- Behaviour: agent prepares investigation pack; human clicks Approve / Edit / Reject / Escalate; only approved low-risk tasks are created.
- Measurement: acceptance rate, edit rate, rejection rate, escalation rate, TTD vs baseline, cost per investigation.
- Duration: ≥ 4 weeks of steady usage.
- Exit criteria: G2→G3 gate met + Fizz APPROVE.
- Rollback: flip feature flag off; workflow reverts to manual.

## Gate 3 — Low-risk canary

- Environment: prod; small workload slice (≤ 10% of eligible cases OR a specific low-risk category).
- Behaviour: only the *approved-task-creation* step is automated after approval; higher-risk categories remain assisted only.
- Rollback: automated canary flag off; per-run kill switch.
- Failure-injection: ≥ 3 scenarios executed here (see `11_failure_injection.md`).
- Exit criteria: G3→G4 gate met + Fizz APPROVE.

## Gate 4 — Controlled operation

- Duration: 8–12 weeks.
- Requirements: scheduled runs, release history, weekly evaluation reports, incident post-mortems for any SEV1/2, cost report monthly.
- Exit criteria: Definition of Done in `README.md` §6 satisfied; Fizz final `APPROVE`.

## Feature-flag policy

- Every gate transition is governed by named feature flags.
- Flags live under `infra/flags/` and are versioned.
- Flag flips are logged with actor, run_id scope, and effective time.

## Rollback SLAs

- Assisted (G2) rollback: ≤ 5 min.
- Canary (G3) rollback: ≤ 2 min for the automated step; ≤ 5 min for the whole gate.
- Any SEV1 auto-triggers rollback to previous gate.

## Communication

- Every gate transition is announced in the Production-Ready-Real-World channel with the Fizz verdict attached.
- Users on the gate get 24h heads-up for any behaviour change.
