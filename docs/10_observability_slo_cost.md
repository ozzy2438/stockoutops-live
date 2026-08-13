# 10 — Observability, SLOs & Cost

> Owner: Bumble (build) + Honey (design) + Fizz (assurance). Status: **TARGET plan; M2 adds local report metadata only, with no live SLO evidence, dashboards, or alerts**.

## Signals

### Structured logs

Every log line includes: `timestamp`, `run_id`, `tenant_id`, `actor`, `step`, `level`, `message`, `latency_ms`, `outcome`.

### Traces

A single trace is proposed to span UI click → workflow step → tool call → LLM call → write. Trace id is recorded in the audit event and shown in the UI as “Run trace”. OpenTelemetry-compatible instrumentation should export to CloudWatch; the exact tracing configuration is reviewed before implementation.

### Metrics

- `investigation_started_total{tenant}`
- `investigation_completed_total{tenant,outcome}` (outcome ∈ approved/edited/rejected/escalated/failed)
- `investigation_latency_seconds` (histogram; p50/p95)
- `tool_call_total{tool,result}`
- `tool_call_latency_seconds{tool}`
- `llm_tokens_total{direction,model}`
- `rls_leakage_total` (must be 0)
- `unauthorised_access_total` (must be 0)
- `unsupported_claim_total`
- `cost_per_investigation_usd`
- `feature_flag_state{flag}`

### Audit

Append-only log with per-tenant partitioning; integrity-hashed periodically.

## SLOs (initial, subject to M1 measurement)

| SLI | SLO | Window | Error budget |
|-----|-----|--------|--------------|
| Investigation success rate | ≥ 99% | 30 days rolling | 1% |
| P95 latency intake→recommendation | ≤ 180 s | 30 days | ≤ 5% of runs above target |
| Availability (UI + API) | ≥ 99.5% business hours | 30 days | 0.5% |
| RLS leakage | 0 | any | 0 (release-blocker) |
| Unauthorised access | 0 | any | 0 (release-blocker) |
| Unsupported claim rate | ≤ 2% | 30 days | 2% |

## Alerts

- Any RLS leakage → SEV1, page on-call.
- Any unauthorised access → SEV1.
- P95 latency SLO burn > 2x for 15 min → SEV2.
- Cost per investigation > 2× rolling median for 1h → SEV3 + email.
- Tool error rate > 5% over 15 min → SEV3.
- LLM provider error rate > 10% over 5 min → SEV3 + auto-failover to human-only mode.

### M2 shadow foundation boundary

The controlled-synthetic pilot records only the fields needed for reproducible local
comparison: case outcome, agreement/disagreement counts, deterministic-provider
latency metadata, error category, and external-action count. Cost is labelled
`SIMULATED` or `UNMEASURED`; it is not a production cost measurement.

**M2-04 SLO alerts — PENDING.** No alarm, dashboard, error-budget, SLO attainment,
or production observability claim is created by the M2-01/M2-02 foundation.

## Dashboards

- **Operational**: live SLO status, latency, tool health, active runs, error budget burn.
- **Business**: acceptance/edit/reject rates, TTD vs baseline, top root causes, weekly volume.
- **Cost**: cost per investigation, LLM tokens, attributable RDS/ECS/S3 usage, and per-tenant breakdown.
- **Evaluation**: golden-case pass rate, shadow-diff agreement, drift charts.

## Cost model

- **Proposed cost per investigation** = attributable LLM usage + attributable AWS usage + an accepted allocation of shared fixed cost.
- Every run writes a `cost` object into its audit event.
- Monthly cost report: total cost, cost per outcome type, cost per tenant, cost drivers (top tools).
- The allocation method remains open under OD-09; no numeric cost claim is MEASURED until that decision and telemetry are in place.

## Retention

- Metrics: 90 days at full resolution; 13 months downsampled.
- Logs: 30 days hot; 12 months cold.
- Audit log: ≥ 12 months.
- LLM prompt/response bodies: not decided (OD-10); raw-body persistence defaults off until approved.

## On-call

- Rotation defined in `docs/runbooks/on_call.md` (created in M1).
- Every SEV1/2 has a post-mortem within 5 business days.
