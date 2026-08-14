# 0007. Local/CI M2 alert-policy contract and append-only evaluation state

- **Status:** Proposed
- **Date:** 2026-08-14
- **Owner:** Ozzy / Osman Orka
- **Design and governance:** Honey / Orchestrator
- **Assurance:** Fizz
- **Decision state:** Pending assurance and owner decision; this record does not
  claim acceptance

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

Stop invoking the local alert CLI and revert PR #22 if the proposed contract is not
accepted. Migration `0006` is additive and forward-only; retain any append-only
evaluation evidence rather than using a destructive rollback. No external
compensation is required because the foundation has no delivery or operational
write.

## Decision ownership and next gate

Ozzy / Osman Orka owns the decision. Honey and Orchestrator own design and
governance review; Fizz owns independent assurance. This ADR remains `Proposed`
until the required assurance and owner decision occur. PR #22 must not represent
consultation, assurance, or acceptance that has not happened.

## Follow-ups

- Driving issue: #21; parent M2 issue: #17.
- M2-04 stays pending after this local/CI foundation.
- A later, separately authorised decision must select, wire, and prove an external
  alert backend before any live-delivery or SLO claim.
