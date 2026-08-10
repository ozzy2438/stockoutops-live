# Observability

Dashboard definitions, alert rules, SLO configurations.

## Layout

```
observability/
├── dashboards/      # JSON/YAML dashboard exports (Grafana / vendor)
├── alerts/          # alert rule definitions
├── slo/             # SLO definitions + burn-rate policies
└── traces/          # trace schema, span naming conventions
```

See `docs/10_observability_slo_cost.md` for the full plan.
