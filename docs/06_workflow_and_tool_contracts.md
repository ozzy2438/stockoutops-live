# 06 — Workflow State & Tool Contracts

> Owner: Honey. Reviewer: Fizz. Status: **proposal**.

## Workflow states

Each investigation is a durable workflow with a strict state machine:

```
 created -> validating -> gathering_evidence -> quality_checks ->
 reasoning -> drafting_recommendation -> awaiting_human ->
 (approved | edited_and_approved | rejected | escalated) ->
 executing_write? -> recording_outcome -> closed
```

Invariants:

- `run_id` is assigned at `created` and never changes.
- Every transition writes an append-only audit event.
- `awaiting_human` is the **only** state that can transition into `executing_write`.
- Any exception routes to `escalated` and pauses the run.

## Standard event envelope

```json
{
  "event_id": "uuid",
  "run_id": "uuid",
  "tenant_id": "string",
  "actor": { "type": "user|agent|system", "id": "string" },
  "step": "string",
  "state_from": "string",
  "state_to": "string",
  "input_hash": "sha256",
  "output_hash": "sha256",
  "citations": [ { "source": "mart", "filter": {}, "row_count": 0, "freshness_ts": "iso8601" } ],
  "latency_ms": 0,
  "cost": { "llm_tokens_in": 0, "llm_tokens_out": 0, "warehouse_credits": 0.0 },
  "timestamp": "iso8601"
}
```

## Tool contracts (7 allow-listed tools)

All tools must:

- Have a JSON schema for arguments and results.
- Execute under the caller’s RBAC + RLS scope.
- Return a citation object.
- Be idempotent for identical arguments within the same `run_id`.
- Enforce per-call token / row / time budgets.

### T1 — `get_inventory_snapshot`
- **Purpose:** current stock for a SKU / store list.
- **Args:** `sku_ids: string[]`, `store_ids: string[]`, `as_of_ts?: iso8601`.
- **Returns:** rows of `(sku_id, store_id, on_hand, reserved, on_order, updated_at)` + citation.
- **Guardrails:** max 500 (sku × store) pairs per call; freshness ≤ 15 min or halts.

### T2 — `get_sales_and_demand`
- **Purpose:** recent sales, velocity, demand signals.
- **Args:** `sku_ids`, `store_ids`, `window_days` (≤ 90).
- **Returns:** daily aggregates with confidence intervals + citation.

### T3 — `get_supplier_status`
- **Purpose:** open POs, expected receipt dates, historical lead-time.
- **Args:** `sku_ids`, `supplier_ids?`.
- **Returns:** open POs, expected ETA, lead-time percentiles + citation.

### T4 — `get_promotion_context`
- **Purpose:** active / upcoming promotions and campaign flags.
- **Args:** `sku_ids`, `store_ids`, `window_days` (≤ 30).
- **Returns:** promo definitions, uplift assumptions (labelled as ASSUMED) + citation.

### T5 — `search_sop_and_policy`
- **Purpose:** retrieve approved SOP / policy passages.
- **Args:** `query`, `topic_filter?`.
- **Returns:** top-k passages with document id, section, effective-from date, hash + citation.
- **Guardrails:** only from a curated policy corpus; no open web.

### T6 — `find_similar_incidents`
- **Purpose:** prior incidents with similar SKU / store / cause fingerprint.
- **Args:** `sku_ids`, `store_ids`, `symptom_tags`.
- **Returns:** incident summaries with outcomes + citation.

### T7 — `draft_incident_or_task`
- **Purpose:** produce a *draft* incident/task payload (Jira-compatible schema) for later human approval.
- **Args:** structured recommendation object.
- **Returns:** draft payload; **does not create anything externally.**
- **Guardrails:** cannot be called unless prior tools produced sufficient citations for a defined evidence rubric.

## What the agent may NOT do

- Call any tool not in T1–T7.
- Emit free-form SQL, shell commands, or arbitrary HTTP.
- Call `T7` without evidence rubric ≥ threshold.
- Escalate its own autonomy level.
- Continue after a `DATA_STALE`, `AUTHZ_FAILED`, or `CONTRACT_VIOLATION` event.

## Versioning

Every tool schema and prompt is versioned. Each run records `{tool: version}` for all invoked tools and the prompt-bundle version. Rollback = pin to a previous set.

## Change control

Adding, removing or changing a tool requires an ADR + threat-model diff + Fizz sign-off.
