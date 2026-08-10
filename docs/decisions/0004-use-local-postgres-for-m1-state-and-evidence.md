# 0004. Use local PostgreSQL for M1 state, audit, idempotency, and T1–T3 evidence

- **Status:** Accepted for M1 (effective after this scope-lock PR merges)
- **Date:** 2026-08-10
- **Deciders:** Ozzy (owner), Honey (architecture), Orchestrator (scope)
- **Assurance:** Fizz review of the exact documentation PR head is required

## Context

M1 must survive process restart, reject duplicate internal actions, reconstruct state from an audit trail, and serve three governed simulated evidence classes. AWS, external source systems, and external writes are out of scope.

## Decision

- Run PostgreSQL 16 with Docker Compose for local/container execution.
- Use `psycopg` 3 and ordered plain SQL migrations with a small runner. Do not add an ORM or Alembic in M1.
- Minimum tables: `investigation_run`, append-only `workflow_event`, `tool_invocation`, `review_decision`, `idempotency_key`, and T1–T3 fixture tables.
- Apply each accepted state transition and its audit event in one database transaction. Use optimistic `state_version`; a zero-row compare-and-update is a conflict and fails closed.
- Deny application-role UPDATE/DELETE on `workflow_event` and add a trigger that raises on either operation. This rejects normal-path mutation; it is not a cryptographic hash chain or WORM guarantee.

### Idempotency

- Intake requires `Idempotency-Key`, unique on `(tenant_id, key)`, with SHA-256 of canonical request JSON.
  - same key and hash returns the existing `run_id` without a new action;
  - same key and different hash returns `409 IDEMPOTENCY_KEY_CONFLICT` and appends an audit event;
  - a different key may create a new run even for semantically similar input.
- Review keys are unique on `(run_id, key)` and a partial unique index permits at most one terminal `review_decision` per run.
- A repeated decided run returns `409 RUN_ALREADY_DECIDED`; a mismatched draft hash returns `409 STALE_APPROVAL_TARGET`.
- Duplicate internal action count is the number of additional runs for one intake key, additional decisions for one run, or additional model invocations for one run. M1 passes only at zero. This is not a claim about tickets or notifications because M1 performs no external write.

### Governed simulated evidence

- Implement only T1 inventory, T2 sales/demand, and T3 supplier as read-only functions over versioned local fixtures loaded from hash-manifested CSV/JSON.
- Pin `tool_schema_version: v1` and validate arguments/results deterministically.
- Provenance contains `evidence_id`, `source_type: postgres_fixture`, stable `source_ref`, query hash, content hash, retrieval timestamp, freshness timestamp, and fixture-manifest version.
- Derive a stable `evidence_id` from source reference and content hash. Every hypothesis and recommendation field cites at least one ID present in the pre-model bundle.
- All three evidence classes must be present, valid, fresh, and provenance-complete before reasoning.

The accepted M1 `v1` subset is singular and canonical-case bounded:

| Tool | Required arguments | Required result facts |
|---|---|---|
| T1 inventory | `sku_id`, `store_id`, `as_of_ts` | `on_hand`, `reserved`, `on_order`, `updated_at` |
| T2 sales/demand | `sku_id`, `store_id`, `window_start`, `window_end` | `units_sold`, `average_daily_units`, `demand_signal`, `updated_at` |
| T3 supplier | `sku_id`, `supplier_id`, `as_of_ts` | `open_order_quantity`, `expected_receipt_at`, `historical_lead_time_days`, `status`, `updated_at` |

Identifiers are non-empty strings; quantities and day measures are non-negative numbers; timestamps are ISO-8601 UTC strings. Each result also requires the common provenance object above. Unknown fields are rejected. No bulk scope, free-form filter, SQL, forecast generation, or external lookup is allowed.

Fixture freshness policy uses ISO-8601 durations:

| Evidence | Maximum fixture age | M1 justification |
|---|---:|---|
| T1 inventory | `PT24H` (24 hours) | Keeps the canonical daily snapshot deterministic. |
| T2 sales/demand | `PT48H` (48 hours) | Allows a simulated daily aggregate to lag one processing day. |
| T3 supplier | `PT72H` (72 hours) | Represents the slower canonical supplier-status refresh. |

These values are test policy, not data-owner-approved production SLAs. Compare them to an injected `as_of_ts`, never uncontrolled wall time.

Missing, stale, invalid, or provenance-incomplete evidence escalates before reasoning. Invalid model schema/citations or budget exhaustion also escalates and is audited.

## Consequences and limitations

- PostgreSQL matches the planned RDS engine while avoiding AWS deployment in M1.
- No RLS, backup/PITR, restore drill, partitioning, distributed lease, outbox, key TTL/garbage collection, semantic deduplication, or migration rollback tooling is claimed.
- T4–T7, S3, dbt-core, external HTTP, signed ingestion, PII pipeline, and real source-system freshness agreements remain deferred.
- State replay is measured on the simulated fixture; production durability and multi-writer safety are not proven.

## Security and privacy

Tenant filters remain mandatory at the repository boundary under ADR-0005. Fixtures contain no real client or personal data. Query and content hashes support attribution but are not proof against privileged database tampering.

## Recovery and rollback

Recovery is manual retry with the original idempotency key after restart. Evidence reads are side-effect free. Failed reasoning does not automatically call the model again. Database schema rollback is manual and must be documented in the implementation PR; no destructive migration is permitted in M1.

## Alternatives considered

- SQLite or in-memory state: rejected because it weakens the target-engine and restart evidence.
- ORM/Alembic: deferred; plain SQL is sufficient for the small schema.
- Outbox/external write design: deferred because M1 has no external side effect.

## Next gate

Bumble implements the accepted subset only after the scope-lock assurance gate. Backup, RLS, multi-writer, and external-write decisions require later evidence and ADRs.
