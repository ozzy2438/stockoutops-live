# Observability

> Milestone 0: documentation only. No dashboard, alert, SLO measurement, or telemetry pipeline exists.

CloudWatch is the target for logs, metrics, traces, dashboards, and alerts. The directory structure below is proposed for artifacts created after M0 approval.

## Layout

```text
observability/
├── dashboards/      # CloudWatch dashboard definitions
├── alerts/          # alert rule definitions
├── slo/             # SLO definitions + burn-rate policies
└── traces/          # trace schema, span naming conventions
```

See `docs/10_observability_slo_cost.md` for the full plan.
