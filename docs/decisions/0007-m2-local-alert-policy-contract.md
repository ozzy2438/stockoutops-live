# 0007. Local/CI M2 alert-policy contract and append-only evaluation state

- **Status:** Accepted for the bounded local/CI alert-policy foundation
- **Date:** 2026-08-14
- **Owner:** Ozzy / Osman Orka
- **Design and governance:** Honey / Orchestrator
- **Assurance:** Fizz
- **Decision state:** Accepted 2026-08-14. Fizz assurance `APPROVE` on reviewed
  source `c385657326d01dd9122bede7633fcba99ef6406f`; Ozzy owner merge decision
  executed as merge commit `720d7f1191103b21479f5c733f32082336570045`;
  post-merge `ci` run `31785973778` `SUCCESS` on that merge commit. Acceptance
  covers only the local/CI contract recorded here. M2-04 remains **PENDING**,
  and no external alert delivery, live SLO, M2 or G1 completion, or production
  readiness is accepted or proven.

## Context

Issue #21 and PR #22 introduce a provider-neutral alert-policy foundation over the
existing execute-false M2 shadow report. The foundation runs only in local and CI
controlled-synthetic rehearsal, persists deterministic policy evaluations, and has
no external alert-delivery implementation. It prepares a later alert-backend proof;
it does not complete M2-04 or demonstrate a live SLO.

Repository governance requires an ADR because this foundation defines both a
durable data/state contract and five frozen policy thresholds. The synthetic case
pack and all resulting alert evaluations are labelled `SIMULATED` and are
permanently ineligible as live-SLO evidence.

## Decision

### Frozen local/CI policies

All policies use policy version `m2-alert-policy-v1`, the strict `>` comparator,
and one tenant-scoped shadow-report batch as their evaluation window.

| Policy ID | Severity | Trigger | Classification |
|---|---|---|---|
| `shadow-external-action-safety` | SEV1 | `external_action_count > 0` | `TARGET` |
| `shadow-escalation-disagreement-rate` | SEV2 | escalation-disagreement rate `> 0.20` | `ENGINEERING TEST THRESHOLD` |
| `shadow-missing-required-evidence` | SEV3 | missing-required-evidence count `> 0` | `TARGET` |
| `shadow-unsupported-claim` | SEV3 | unsupported citation/claim proxy count `> 0` | `TARGET` |
| `shadow-processing-error-rate` | SEV3 | shadow-processing error rate `> 0.05` | `ENGINEERING TEST THRESHOLD` |

Values equal to a threshold do not breach it. These policy definitions are
deterministic local/CI controls, not evidence of production SLO attainment.

### Evaluation and persistence contract

- Persisted alert states are `OK`, `FIRING`, and `RESOLVED`.
- A missing metric records an `UNMEASURED` evaluation with no healthy state; it
  never silently becomes `OK`.
- An `UNMEASURED` evaluation after `FIRING` does not resolve the alert. Resolution
  requires a later measured, non-breaching evaluation and an explicit
  `FIRING` to `RESOLVED` transition.
- The stable alert fingerprint contains policy identity and version, tenant, and
  run/case correlation when present. It excludes the evaluation window so later
  measured windows can resolve the same alert identity.
- PostgreSQL stores append-only evaluation history. Application-role permissions
  and a mutation-blocking trigger reject update and delete operations.
- Tenant-scoped persistence, a transaction advisory lock, idempotency key, and
  payload hash make repeated evaluation deterministic. A repeated equivalent
  input replays its existing event; conflicting reuse fails closed.
- If `external_action_count > 0`, the foundation persists the SEV1 `FIRING`
  evaluation and then fails closed. It performs no external action or delivery.

`AlertSink` remains an interface only. There is no CloudWatch, SNS, email, Slack,
PagerDuty, webhook, or other alert-delivery implementation.

Production availability, RLS leakage, production identity/authorisation, cost per
investigation, live-model provider failures, and external delivery remain explicitly
`UNWIRED`, `UNMEASURED`, or `FUTURE`. They are not inferred from synthetic data.

## Consequences

### Positive

- Policy boundaries, threshold meaning, state transitions, and deduplication are
  reviewable without selecting a cloud alert backend.
- Synthetic inputs cannot be represented by this contract as live-SLO evidence.
- Append-only evaluation history supports deterministic replay and assurance.

### Negative / trade-offs

- All evidence is controlled synthetic; the engineering thresholds are not
  production SLOs.
- `unsupported_claim_count` is the current unsupported-citation proxy, not semantic
  unsupported-claim detection.
- Direct service construction can represent some missing metrics as `UNMEASURED`,
  while the canonical report loader requires `external_action_count`.
- Database/application mutation controls are not WORM storage or cryptographic
  tamper evidence.
- Local tenant enforcement is not production PostgreSQL RLS.

### Neutral

- There is no operational environment, live delivery, production dashboard, or
  real error-budget measurement.
- M2-04 remains **PENDING** until a separately authorised environment delivers and
  proves alerts.

## Alternatives considered

- **Record the decision only in Issue #21 and documentation** — rejected because
  repository governance requires an ADR for the data-contract and SLO decisions.
- **Hard-code CloudWatch delivery now** — rejected because provider selection and
  live delivery are separately gated and out of Issue #21 scope.
- **Treat missing metrics as healthy** — rejected because absence of evidence must
  remain `UNMEASURED`, never an implicit pass.
- **Keep only mutable current alert state** — rejected because it would discard the
  append-only transition evidence required for deterministic review.

## Recovery and rollback

Stop invoking the local alert CLI and revert merge commit
`720d7f1191103b21479f5c733f32082336570045` if this accepted contract must later be
withdrawn. Migration `0006` is additive and forward-only; retain any append-only
evaluation evidence rather than using a destructive rollback. No external
compensation is required because the foundation has no delivery or operational
write.

## Decision ownership and next gate

Ozzy / Osman Orka owns the decision. Honey and Orchestrator own design and
governance review; Fizz owns independent assurance. The required assurance and
owner decision have now occurred, in that order: Fizz `APPROVE` on
`c385657326d01dd9122bede7633fcba99ef6406f`, the Ozzy owner merge decision
recorded as `720d7f1191103b21479f5c733f32082336570045`, and post-merge `ci`
run `31785973778` `SUCCESS`. Acceptance is bounded to the contract recorded in
this ADR and must not be represented as consultation, assurance, or acceptance
of anything beyond it. The next gate is the separately authorised decision that
selects, wires, and proves an external alert backend.

## Follow-ups

- Driving issue: #21, closed 2026-08-14; parent M2 issue: #17, which remains open.
- M2-04 stays pending after this local/CI foundation.
- A later, separately authorised decision must select, wire, and prove an external
  alert backend before any live-delivery or SLO claim.
