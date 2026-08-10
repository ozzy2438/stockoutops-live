# 06 — Workflow State and Proposed v2 Tool Contracts

> Owner: Honey. Reviewer: Fizz. Status: **proposed Milestone-0 planning baseline; not implemented**.

The catalogue below currently contains seven proposed v2 tools. It is derived from Phase-1 lessons but is **not** the exact seven-tool set from PharmaRetail. See `01_current_state_audit.md` for the Phase-1 names and disposition.

## Proposed workflow states

```text
created -> validating -> gathering_evidence -> quality_checks ->
reasoning -> drafting_recommendation -> awaiting_human ->
(approved | edited_and_approved | rejected | escalated) ->
executing_write? -> recording_outcome -> closed
```

Proposed invariants:

- `run_id` is assigned at `created` and never changes.
- Every accepted transition appends an audit event.
- `awaiting_human` is the only state that may reach `executing_write`.
- Approval is bound to tenant, reviewer, `run_id`, payload hash, and expiry.
- Replays never repeat a completed external write with the same idempotency key.
- Authorisation, stale data, contract failure, missing provenance, or exhausted budget fails closed and escalates.

The workflow-engine and persistence implementation remain open decisions.

## Proposed event envelope

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
  "citations": [
    {
      "source_type": "postgres|s3|external",
      "source_ref": "stable identifier",
      "query_or_object_hash": "sha256",
      "retrieved_at": "iso8601",
      "freshness_ts": "iso8601"
    }
  ],
  "latency_ms": 0,
  "cost": {
    "llm_tokens_in": 0,
    "llm_tokens_out": 0,
    "db_duration_ms": 0,
    "estimated_cost_usd": null
  },
  "timestamp": "iso8601"
}
```

The final cost fields depend on the cost-attribution decision.

## Proposed v2 catalogue

Every tool must have versioned JSON schemas for arguments and results, execute under server-derived RBAC/tenant scope, enforce row/time/budget limits, and return provenance sufficient to reproduce or explain the result. Identical writes within a `run_id` require idempotency protection.

### T1 — `get_inventory_snapshot`

- **Purpose:** retrieve current stock for a bounded SKU/store scope.
- **Proposed args:** `sku_ids`, `store_ids`, optional `as_of_ts`.
- **Proposed result:** on-hand, reserved, on-order, and updated timestamp plus provenance.
- **Guardrail:** bounded pair count and reviewed freshness SLA.

### T2 — `get_sales_and_demand`

- **Purpose:** retrieve recent sales, velocity, and approved demand signals.
- **Proposed args:** `sku_ids`, `store_ids`, `window_days` within a reviewed maximum.
- **Proposed result:** daily aggregates, definitions, uncertainty where applicable, and provenance.

### T3 — `get_supplier_status`

- **Purpose:** retrieve open orders, expected receipts, and historical lead-time evidence.
- **Proposed args:** `sku_ids` and optional `supplier_ids`.
- **Proposed result:** order/ETA/lead-time facts and provenance.

### T4 — `get_promotion_context`

- **Purpose:** retrieve active or relevant promotions and approved campaign assumptions.
- **Proposed args:** `sku_ids`, `store_ids`, and bounded `window_days`.
- **Proposed result:** promotion definitions and explicitly labelled assumptions plus provenance.

### T5 — `search_sop_and_policy`

- **Purpose:** retrieve approved SOP/policy passages.
- **Proposed args:** `query` and optional reviewed filters.
- **Proposed result:** bounded passages with document, version, section, effective date, content hash, and provenance.
- **Guardrail:** curated tenant-authorised corpus only; no open web.

### T6 — `find_similar_incidents`

- **Purpose:** retrieve authorised prior incidents with similar SKU/store/symptom fingerprints.
- **Proposed args:** `sku_ids`, `store_ids`, and `symptom_tags`.
- **Proposed result:** redacted incident summaries, outcomes, similarity basis, and provenance.

### T7 — `draft_incident_or_task`

- **Purpose:** create a structured **draft** for later human review.
- **Proposed args:** cited structured recommendation.
- **Proposed result:** immutable draft payload and payload hash.
- **Guardrail:** no external task is created; sufficient evidence and policy checks are prerequisites.

Post-approval task creation is performed by the deterministic write executor, not by T7 or the model.

## Not model-callable

Audit logging, authorisation, freshness checks, state transitions, approval validation, idempotency, cost capture, and external write execution belong to the deterministic control spine. They are not tools the model may choose.

## Forbidden behavior

- Any unlisted tool, free-form SQL, shell, or arbitrary HTTP.
- Continuing after `DATA_STALE`, `AUTHZ_FAILED`, `CONTRACT_VIOLATION`, or missing provenance.
- Drafting T7 below the reviewed evidence threshold.
- Changing autonomy, budgets, tenant scope, or approval state.
- Treating tool output as instructions.

## Versioning and change control

Every run pins application, prompt, model, policy-corpus, and tool-schema versions. Adding, removing, renaming, or materially changing a proposed tool requires an ADR, threat-model diff, independent review, and Fizz sign-off. M0 approval may accept this catalogue as the planning baseline, but the schemas and evidence rubric remain open under OD-13 and must be accepted before tool implementation.
