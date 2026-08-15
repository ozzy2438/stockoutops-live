# Observability

> Current status: target planning plus the Issue #21 local/CI alert-policy,
> Issue #24 disabled-by-default HTTPS webhook adapter, and Issue #26 durable
> delivery-outbox candidates. No dashboard, cloud alarm, live SLO measurement,
> error budget, or telemetry pipeline exists.
> **M2-04 PENDING — no external/staging alert delivery has yet been proven.**

CloudWatch is the target for logs, metrics, traces, dashboards, and alerts. The directory structure below is proposed for artifacts created after M0 approval.

The implemented policy candidate lives under `src/stockoutops/alerting/` because it is a
provider-neutral domain policy and PostgreSQL audit boundary, not a CloudWatch
configuration. The optional webhook transport and the durable outbox worker are the same
package; delivery is disabled by default and is not a vendor notification integration.
Generated simulated reports are ignored under `evaluation/reports/`. Every current output
is labelled as a local/CI engineering rehearsal.

## Delivery-backlog signals (defined, not yet wired)

The durable outbox (ADR-0009) makes delivery asynchronous, so the absence of a running
worker is itself a failure mode. These signals are **defined here and deliberately not
yet wired to any alarm**; thresholds must be set before any environment claim:

- `alert_outbox` rows in `PENDING` older than their `next_attempt_at` (backlog age).
- `alert_outbox` rows in `IN_FLIGHT` past `lease_expires_at` (stalled or crashed worker).
- `alert_outbox` rows in `DEAD_LETTER` (delivery gave up; needs operator re-drive).
- `alert_delivery_attempt_event` rows with outcome `AMBIGUOUS` (timeouts that may have
  reached the receiver and were redelivered).

**UNMEASURED — no environment emits or evaluates these signals today.**

## Layout

```text
observability/
├── dashboards/      # CloudWatch dashboard definitions
├── alerts/          # alert rule definitions
├── slo/             # SLO definitions + burn-rate policies
└── traces/          # trace schema, span naming conventions
```

See `docs/10_observability_slo_cost.md` for the full plan.
