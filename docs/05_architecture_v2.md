# 05 — Architecture v2

> Owner: Honey. Reviewer: Fizz. Status: **proposal, subject to M0 review**.

## Design principles

1. **Deterministic outer loop, bounded agent inner loop.** Identity, authorization, freshness, approval, write, and audit are deterministic code paths. Agentic reasoning is used only where genuine uncertainty exists (root-cause hypothesis, evidence framing, recommendation drafting).
2. **Every run has a durable `run_id`.** State survives process restarts; each step is idempotent and replayable.
3. **Tools are contracts, not calls.** The agent may only invoke allow-listed tools with schema-validated arguments. No free-form SQL, no shell.
4. **Human is a first-class step**, not an afterthought. Approve/edit/reject/escalate is modelled as an explicit workflow state.
5. **Everything is observable.** Structured logs, traces spanning tool calls, metrics, cost telemetry, and lineage.
6. **Fail closed.** On any authorization, freshness, or contract violation, the workflow halts and escalates.

## High-level components

```
           +----------------------+
           |  Alert / Request     |
           |  (webhook, UI, cron) |
           +----------+-----------+
                      |
                      v
           +----------------------+       +-----------------------+
           |  Intake & Guardrails |------>|  Identity / Tenant /  |
           |  (deterministic)     |       |  Eligibility / Fresh  |
           +----------+-----------+       +-----------------------+
                      |
                      v
           +----------------------+       +-----------------------+
           |  Workflow Engine     |<----->|  Durable State Store  |
           |  (run_id, steps)     |       |  (append-only + KV)   |
           +----------+-----------+       +-----------------------+
                      |
                      v
           +----------------------+       +-----------------------+
           |  Tool Layer          |<----->|  Governed Data Marts  |
           |  (allow-listed 7)    |       |  (Snowflake + RLS)    |
           +----------+-----------+       +-----------------------+
                      |
                      v
           +----------------------+       +-----------------------+
           |  Agent (LLM)         |------>|  Prompt/Tool Registry |
           |  bounded reasoning   |       |  (versioned)          |
           +----------+-----------+       +-----------------------+
                      |
                      v
           +----------------------+       +-----------------------+
           |  Recommendation Pack |------>|  Human Review UI      |
           |  (cited)             |       |  (approve/edit/rej.)  |
           +----------+-----------+       +-----------------------+
                      |
                      v
           +----------------------+       +-----------------------+
           |  Write Executor      |------>|  Incident / Task /    |
           |  (post-approval)     |       |  Notification systems |
           +----------+-----------+       +-----------------------+
                      |
                      v
           +----------------------+       +-----------------------+
           |  Audit + Outcome     |------>|  Observability stack  |
           |  logging             |       |  (logs/traces/metrics)|
           +----------------------+       +-----------------------+
```

## Component notes

### Intake & Guardrails
- Rejects requests missing tenant, identity, or required fields.
- Verifies data freshness against per-mart SLAs; halts with `DATA_STALE` on violation.
- Emits `intake.accepted` / `intake.rejected` events.

### Workflow Engine
- Durable, resumable, idempotent steps.
- Each step writes to append-only event log with `run_id`, `tenant_id`, `actor`, `timestamp`, `step`, `input_hash`, `output_hash`.
- Supported step states: `pending`, `running`, `succeeded`, `failed`, `awaiting_human`, `escalated`, `cancelled`.

### Tool Layer
- Exactly the 7 allow-listed tools from PharmaRetail (see `docs/06_workflow_and_tool_contracts.md`).
- All arguments are JSON-schema validated **before** execution.
- All results carry a citation object (source mart, filter, row-count, freshness).
- Tools run under the caller’s RBAC + RLS scope; no service-account escalation.

### Agent
- LLM behind a stable adapter interface (provider swap is one-line).
- Prompts, tool schemas, and stopping criteria are versioned in a registry; each run records the exact versions used.
- Enforced maximum tool calls per run, maximum tokens per call, maximum wall-clock.
- Structured outputs only; unstructured text is treated as untrusted commentary.

### Human Review UI
- Presents: root-cause hypothesis, evidence citations, affected scope, proposed action, risk flags.
- Actions: **Approve**, **Edit-then-approve**, **Reject with reason**, **Escalate**.
- No action can be taken until required citations are present and freshness is green.

### Write Executor
- Only path that mutates external systems (incident / task / notification).
- Runs strictly after human approval; carries the approval token and reviewer id.
- Emits `write.attempted`, `write.succeeded`, `write.failed` events.

### Audit + Observability
- Append-only audit log is the source of truth.
- OpenTelemetry traces link user click → workflow step → tool call → LLM call → write.
- Cost telemetry attached to each `run_id` (LLM tokens, warehouse credits, minutes).

## Non-functional targets (initial)

| Dimension | Target (M2 canary) |
|-----------|--------------------|
| Availability | 99.5% during business hours |
| P50 investigation latency | ≤ 60s from intake to recommendation |
| P95 investigation latency | ≤ 180s |
| RLS leakage | 0 (release-blocker if > 0) |
| Unsupported claim rate | ≤ 2% in golden-case suite |
| Cost per investigation | tracked; no target until baseline is measured |

## Trust boundaries

See `docs/07_threat_model.md` for the STRIDE analysis and the trust-boundary diagram diff process.

## Change control

Any change to this document requires an ADR under `docs/decisions/` and Fizz sign-off.
