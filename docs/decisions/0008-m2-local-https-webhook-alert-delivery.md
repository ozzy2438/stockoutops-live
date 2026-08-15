# 0008. Local HTTPS webhook alert delivery adapter

- **Status:** Proposed
- **Date:** 2026-08-14
- **Deciders:** TBD pending Buzz/Fizz assurance and owner merge
- **Consulted:** Honey (design), Fizz (egress/SLO labelling)
- **Informed:** Orchestrator, Scout
- **Driving issue:** #24; parent M2 issue: #17, which remains open

## Context

ADR-0007 accepted the local/CI alert-policy contract and left `AlertSink` as an
interface only. Issue #21 / PR #22 persist append-only `FIRING` / `RESOLVED`
evaluations without outbound delivery. M2-04 still requires a separately
authorised real/staging delivery proof.

This decision records the smallest provider-neutral outbound path toward that
later proof: a generic HTTPS webhook over the existing `AlertSink` boundary.
It does not select Slack, PagerDuty, email, CloudWatch, or SNS. It does not
close OD-08. It does not complete M2-04.

## Decision

- Implement one HTTPS webhook `AlertSink`. Delivery is disabled by default and
  requires explicit configuration to enable.
- Keep frozen ADR-0007 policy thresholds, severities, comparator, evaluation
  states, `SIMULATED` labelling, `execute=false`, and
  `live_slo_evidence_eligible=false`. Evaluation rows continue to constrain
  `external_alert_delivery_count = 0`.
- Persist evaluation events first. Webhook failure must not roll back alert
  evidence.
- Notify only `FIRED` and `RESOLVED` transitions. Replay and `STILL_FIRING`
  must not send.
- Claim a tenant-scoped delivery-attempt row before HTTP so concurrent callers
  and idempotent replay cannot duplicate a lifecycle notification.
- Bound transport: HTTPS except loopback HTTP for local proof; reject URL
  credentials; timeout 2s; at most two attempts; retry only timeout,
  connection error, or HTTP 5xx.
- Use existing `httpx`. No AWS and no OpenAI. Optional webhook token is read
  from the environment and is never committed, logged, or stored.
- Local/CI proof uses a loopback HTTP receiver. No public internet contact is
  authorised by this decision.

**M2-04 PENDING — no external/staging alert delivery has yet been proven.**

## Consequences

### Positive

- Outbound delivery can be reviewed without choosing a vendor backend.
- Evaluation history remains the source of alert evidence when delivery fails.
- Duplicate lifecycle notifications are constrained by a durable claim.

### Negative / trade-offs

- Claim-before-send is at-most-once. A crash after claim and before a successful
  POST can drop a notification; that is accepted for this engineering candidate.
- Loopback HTTP is allowed only so local tests can prove the adapter without TLS.
- The adapter is not a production notifier, live SLO, or G1-exit mechanism.

### Neutral

- CloudWatch, SNS, email, Slack, and PagerDuty remain absent.
- OD-08 remains open.
- Issue #17 remains open.

## Alternatives considered

- **Hard-code CloudWatch or Slack now** — rejected; provider selection and live
  delivery remain separately gated.
- **Deliver inside the evaluation transaction** — rejected; delivery failure
  would discard required alert evidence.
- **Skip durable delivery claims** — rejected; the evaluation advisory lock is
  released at commit, so replay/concurrency needs a claim-before-HTTP row.

## Recovery and rollback

Leave `STOCKOUTOPS_ALERT_WEBHOOK_ENABLED` unset or `false`. Revert the
implementation commit if the adapter must be withdrawn. Migration `0007` is
additive; retain any delivery-attempt rows rather than using a destructive
rollback. No live external compensation is required because this candidate does
not prove staging or production delivery.

## Follow-ups

- Driving issue: #24.
- Parent M2 issue: #17, remains open.
- M2-04 stays pending until a separately authorised environment delivers and
  proves alerts.
- A later accepted decision must still select, wire, and prove a real/staging
  alert backend before any live-delivery or SLO claim.
