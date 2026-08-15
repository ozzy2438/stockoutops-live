# 10 — Observability, SLOs & Cost

> Owner: Bumble (build) + Honey (design) + Fizz (assurance). Status: **TARGET plan plus local/CI M2-04 policy-wiring and disabled-by-default webhook adapter candidates; no live SLO evidence, dashboard, or SLO attainment claim. M2-04 PENDING — no external/staging alert delivery has yet been proven.**

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

## Future production-target alerts — UNWIRED

- Any RLS leakage → SEV1, page on-call — **TARGET / UNWIRED**.
- Any unauthorised access → SEV1 — **TARGET / UNWIRED**.
- P95 latency SLO burn > 2x for 15 min → SEV2 — **TARGET / UNMEASURED**.
- Cost per investigation > 2× rolling median for 1h → SEV3 + email —
  **TARGET / UNMEASURED**.
- Tool error rate > 5% over 15 min → SEV3 — **TARGET / UNWIRED**.
- LLM provider error rate > 10% over 5 min → SEV3 + human-only fallback —
  **TARGET / FUTURE**.

These future policies are not implemented by the local M2-04 foundation. It has no
production RLS, IdP, availability, cost, live-model, page, email, or failover signal.

### M2 shadow foundation boundary

The controlled-synthetic pilot records only the fields needed for reproducible local
comparison: case outcome, agreement/disagreement counts, deterministic-provider
latency metadata, error category, and external-action count. Cost is labelled
`SIMULATED` or `UNMEASURED`; it is not a production cost measurement.

**M2-04 SLO alerts — PENDING.** The Issue #21 implementation candidate evaluates
only current controlled-synthetic shadow-report signals through a provider-neutral
local/CI policy layer. It persists append-only evaluations and generates local JSON
and Markdown. Issue #24 adds a disabled-by-default HTTPS webhook adapter over that
foundation. It does not create a CloudWatch alarm, measure an error budget, or
establish SLO attainment. **M2-04 PENDING — no external/staging alert delivery has
yet been proven.**

### Implemented local/CI policy candidate

| Policy | Severity | Trigger | Threshold classification | Current evidence limit |
|---|---|---:|---|---|
| Shadow external-action safety | SEV1 | `external_action_count > 0` | **TARGET** | Hard invariant; current rehearsal remains 0 |
| Escalation disagreement | SEV2 | rate `> 0.20` per tenant report batch | **ENGINEERING TEST THRESHOLD** | Synthetic diff behaviour only |
| Missing required evidence | SEV3 | count `> 0` | **TARGET** | Contract-derived T1–T3 metric only |
| Unsupported citation/claim | SEV3 | count `> 0` | **TARGET** | Deterministic citation validation only |
| Shadow processing errors | SEV3 | rate `> 0.05` per tenant report batch | **ENGINEERING TEST THRESHOLD** | Current successful report lacks an attempt/failure denominator, so it is `UNMEASURED` |

The comparator is strictly greater than: values below or equal to a threshold remain
`OK`; values above it become `FIRING`. A later non-breaching measured window appends
`RESOLVED`. A stable fingerprint excludes window values so repeated windows converge
on one derived active state. PostgreSQL advisory locking plus idempotency and payload
hashes prevent duplicate effective evaluations; history rejects update/delete through
application permissions and a database trigger. This is mutation control, not WORM or
cryptographic tamper evidence.

Synthetic inputs are permanently marked ineligible as live SLO evidence in this
foundation. Missing metrics produce `UNMEASURED`, never an implicit `OK`.

### Local HTTPS webhook adapter candidate

A generic HTTPS webhook `AlertSink` may be enabled only with explicit configuration.
The default is disabled and performs zero outbound requests. `make alert-pilot` and
CI keep that default. When enabled, the adapter:

- sends only `FIRED` and `RESOLVED` lifecycle notifications
- claims a tenant-scoped delivery-attempt row before HTTP so replay and concurrency
  cannot duplicate a notification
- uses a 2s timeout and at most two attempts (retry on timeout, connection error, or
  HTTP 5xx)
- requires HTTPS except for loopback HTTP used by the local proof receiver
- preserves original alert evaluation rows if delivery fails

Optional `STOCKOUTOPS_ALERT_WEBHOOK_TOKEN` is never committed, logged, or stored.
This adapter is not Slack, PagerDuty, email, CloudWatch, or SNS. It is not a
live/staging delivery proof.

**M2-04 PENDING — no external/staging alert delivery has yet been proven.**

Run after `make shadow-pilot`:

```bash
make alert-pilot
make alert-webhook-proof
```

Disable/rollback by leaving `STOCKOUTOPS_ALERT_WEBHOOK_ENABLED` unset or `false`
and reverting the implementation commit. Migrations `0006` and `0007` are additive
and forward-only; retain append-only evaluation history and any delivery-attempt
rows for inspection.

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
