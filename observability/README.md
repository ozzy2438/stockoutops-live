# Observability

> Current status: target planning plus Issue #21 local/CI alert-policy and
> Issue #24 disabled-by-default HTTPS webhook adapter candidates. No dashboard,
> cloud alarm, live SLO measurement, error budget, or telemetry pipeline exists.
> **M2-04 PENDING — no external/staging alert delivery has yet been proven.**

CloudWatch is the target for logs, metrics, traces, dashboards, and alerts. The directory structure below is proposed for artifacts created after M0 approval.

The implemented policy candidate lives under `src/stockoutops/alerting/` because it is a
provider-neutral domain policy and PostgreSQL audit boundary, not a CloudWatch
configuration. The optional webhook adapter is the same package; it is disabled by
default and is not a vendor notification integration. Generated simulated reports are
ignored under `evaluation/reports/`. Every current output is labelled as a local/CI
engineering rehearsal.

## Layout

```text
observability/
├── dashboards/      # CloudWatch dashboard definitions
├── alerts/          # alert rule definitions
├── slo/             # SLO definitions + burn-rate policies
└── traces/          # trace schema, span naming conventions
```

See `docs/10_observability_slo_cost.md` for the full plan.
