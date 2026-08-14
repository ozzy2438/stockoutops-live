# Observability

> Current status: target planning plus an Issue #21 local/CI alert-policy
> implementation candidate. No dashboard, cloud alarm, notification delivery, live
> SLO measurement, error budget, or telemetry pipeline exists.

CloudWatch is the target for logs, metrics, traces, dashboards, and alerts. The directory structure below is proposed for artifacts created after M0 approval.

The implemented candidate lives under `src/stockoutops/alerting/` because it is a
provider-neutral domain policy and PostgreSQL audit boundary, not a CloudWatch
configuration. Generated simulated reports are ignored under `evaluation/reports/`.
Every current output is labelled as a local/CI engineering rehearsal; M2-04 remains
pending until a separately authorised environment delivers and proves alerts.

## Layout

```text
observability/
├── dashboards/      # CloudWatch dashboard definitions
├── alerts/          # alert rule definitions
├── slo/             # SLO definitions + burn-rate policies
└── traces/          # trace schema, span naming conventions
```

See `docs/10_observability_slo_cost.md` for the full plan.
