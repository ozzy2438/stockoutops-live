"""Tenant-scoped PostgreSQL persistence and locking for shadow results."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from stockoutops.database import Database
from stockoutops.errors import ConflictError, NotFoundError
from stockoutops.identity import Principal
from stockoutops.shadow.contracts import (
    BaselineSource,
    ProvenanceLabel,
    ShadowActualOutcome,
    ShadowComparison,
)


def _lock_key(value: str) -> int:
    digest = hashlib.sha256(value.encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


@dataclass(frozen=True)
class ShadowRunRecord:
    shadow_run_id: UUID
    tenant_id: str
    idempotency_key: str
    payload_hash: str
    case_id: str
    case_version: str
    case_pack_version: str
    processor_version: str
    prompt_version: str
    tool_schema_version: str
    provenance_label: ProvenanceLabel
    baseline_source: BaselineSource
    execute: bool
    status: str
    investigation_run_id: UUID | None
    provider_label: str | None
    output_json: dict[str, object] | None
    diff_json: dict[str, object] | None
    output_hash: str | None
    diff_hash: str | None
    latency_ms: float | None
    estimated_cost_usd: float | None
    cost_evidence_label: str | None
    external_action_count: int
    created_by: str
    created_at: datetime
    completed_at: datetime | None


def _record(row: dict[str, Any]) -> ShadowRunRecord:
    return ShadowRunRecord(
        shadow_run_id=row["shadow_run_id"],
        tenant_id=row["tenant_id"],
        idempotency_key=row["idempotency_key"],
        payload_hash=row["payload_hash"],
        case_id=row["case_id"],
        case_version=row["case_version"],
        case_pack_version=row["case_pack_version"],
        processor_version=row["processor_version"],
        prompt_version=row["prompt_version"],
        tool_schema_version=row["tool_schema_version"],
        provenance_label=row["provenance_label"],
        baseline_source=row["baseline_source"],
        execute=row["execute"],
        status=row["status"],
        investigation_run_id=row["investigation_run_id"],
        provider_label=row["provider_label"],
        output_json=row["output_json"],
        diff_json=row["diff_json"],
        output_hash=row["output_hash"],
        diff_hash=row["diff_hash"],
        latency_ms=float(row["latency_ms"]) if row["latency_ms"] is not None else None,
        estimated_cost_usd=(
            float(row["estimated_cost_usd"]) if row["estimated_cost_usd"] is not None else None
        ),
        cost_evidence_label=row["cost_evidence_label"],
        external_action_count=row["external_action_count"],
        created_by=row["created_by"],
        created_at=row["created_at"],
        completed_at=row["completed_at"],
    )


class ShadowClaim:
    def __init__(self, connection: psycopg.Connection[dict[str, Any]], keys: list[int]) -> None:
        self._connection = connection
        self._keys = keys
        self._released = False

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        try:
            for key in reversed(self._keys):
                self._connection.execute("SELECT pg_advisory_unlock(%s)", (key,))
        finally:
            self._connection.close()

    def __enter__(self) -> ShadowClaim:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.release()


class ShadowRepository:
    """Every tenant-scoped public method receives Principal first."""

    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _insert_event(
        connection: Any,
        *,
        run: ShadowRunRecord,
        actor_id: str,
        event_type: str,
        payload: dict[str, object],
        occurred_at: datetime,
    ) -> None:
        connection.execute(
            """
            INSERT INTO shadow_control_event (
                shadow_run_id, tenant_id, event_type, actor_id, payload, occurred_at
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                run.shadow_run_id,
                run.tenant_id,
                event_type,
                actor_id,
                Jsonb(payload),
                occurred_at,
            ),
        )

    def begin_or_observe(
        self,
        principal: Principal,
        *,
        idempotency_key: str,
        payload_hash: str,
        case_id: str,
        case_version: str,
        case_pack_version: str,
        processor_version: str,
        prompt_version: str,
        provenance_label: ProvenanceLabel,
        baseline_source: BaselineSource,
        now: datetime,
    ) -> tuple[ShadowRunRecord, ShadowClaim | None, bool]:
        keys = sorted(
            {
                _lock_key(f"shadow:idempotency:{principal.tenant_id}:{idempotency_key}"),
                _lock_key(
                    "shadow:case:"
                    f"{principal.tenant_id}:{case_id}:{case_version}:{processor_version}"
                ),
            }
        )
        connection = psycopg.connect(self.database.dsn, row_factory=dict_row, autocommit=True)
        try:
            for key in keys:
                connection.execute("SELECT pg_advisory_lock(%s)", (key,))
            rows = connection.execute(
                """
                SELECT * FROM shadow_run
                WHERE tenant_id = %s
                  AND (
                    idempotency_key = %s
                    OR (case_id = %s AND case_version = %s AND processor_version = %s)
                  )
                ORDER BY shadow_run_id
                """,
                (
                    principal.tenant_id,
                    idempotency_key,
                    case_id,
                    case_version,
                    processor_version,
                ),
            ).fetchall()
            if len(rows) > 1:
                raise ConflictError(
                    "SHADOW_IDENTITY_CONFLICT",
                    "Idempotency key and case identity resolve to different shadow runs",
                )
            if rows:
                run = _record(rows[0])
                if run.payload_hash != payload_hash:
                    self._insert_event(
                        connection,
                        run=run,
                        actor_id=principal.actor_id,
                        event_type="shadow_request_rejected",
                        payload={"code": "SHADOW_IDEMPOTENCY_CONFLICT"},
                        occurred_at=now,
                    )
                    raise ConflictError(
                        "SHADOW_IDEMPOTENCY_CONFLICT",
                        "Shadow identity was already used with a different payload",
                    )
                if run.status != "started":
                    for key in reversed(keys):
                        connection.execute("SELECT pg_advisory_unlock(%s)", (key,))
                    connection.close()
                    return run, None, False
                return run, ShadowClaim(connection, keys), False

            row = connection.execute(
                """
                INSERT INTO shadow_run (
                    shadow_run_id, tenant_id, idempotency_key, payload_hash,
                    case_id, case_version, case_pack_version, processor_version,
                    prompt_version, tool_schema_version, provenance_label, baseline_source,
                    execute, status, external_action_count, created_by, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, 'v1', %s, %s, false,
                    'started', 0, %s, %s
                ) RETURNING *
                """,
                (
                    uuid4(),
                    principal.tenant_id,
                    idempotency_key,
                    payload_hash,
                    case_id,
                    case_version,
                    case_pack_version,
                    processor_version,
                    prompt_version,
                    provenance_label,
                    baseline_source,
                    principal.actor_id,
                    now,
                ),
            ).fetchone()
            run = _record(row)
            self._insert_event(
                connection,
                run=run,
                actor_id=principal.actor_id,
                event_type="shadow_run_started",
                payload={"execute": False, "external_action_count": 0},
                occurred_at=now,
            )
            return run, ShadowClaim(connection, keys), True
        except Exception:
            if not connection.closed:
                for key in reversed(keys):
                    connection.execute("SELECT pg_advisory_unlock(%s)", (key,))
                connection.close()
            raise

    def complete(
        self,
        principal: Principal,
        run: ShadowRunRecord,
        *,
        investigation_run_id: UUID,
        actual: ShadowActualOutcome,
        comparison: ShadowComparison,
        output_hash: str,
        diff_hash: str,
        completed_at: datetime,
    ) -> ShadowRunRecord:
        terminal_status = "escalated" if actual.escalated else "completed"
        with self.database.connect() as connection, connection.transaction():
            row = connection.execute(
                """
                UPDATE shadow_run
                SET status = %s, investigation_run_id = %s, provider_label = %s,
                    output_json = %s, diff_json = %s, output_hash = %s,
                    diff_hash = %s, latency_ms = %s, estimated_cost_usd = %s,
                    cost_evidence_label = %s, completed_at = %s
                WHERE shadow_run_id = %s AND tenant_id = %s AND status = 'started'
                RETURNING *
                """,
                (
                    terminal_status,
                    investigation_run_id,
                    actual.provider_label,
                    Jsonb(actual.model_dump(mode="json")),
                    Jsonb(comparison.model_dump(mode="json")),
                    output_hash,
                    diff_hash,
                    actual.latency_ms,
                    actual.estimated_cost_usd,
                    actual.cost_evidence_label,
                    completed_at,
                    run.shadow_run_id,
                    principal.tenant_id,
                ),
            ).fetchone()
            if row is None:
                raise ConflictError(
                    "SHADOW_COMPLETION_CONFLICT", "Shadow run is no longer startable"
                )
            completed = _record(row)
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO shadow_diff (
                        shadow_run_id, tenant_id, field_name, agreement,
                        expected_json, actual_json, category, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    [
                        (
                            run.shadow_run_id,
                            principal.tenant_id,
                            entry.field_name,
                            entry.agreement,
                            Jsonb(entry.expected),
                            Jsonb(entry.actual),
                            entry.category,
                            completed_at,
                        )
                        for entry in comparison.entries
                    ],
                )
            self._insert_event(
                connection,
                run=completed,
                actor_id=principal.actor_id,
                event_type="shadow_run_completed",
                payload={
                    "status": terminal_status,
                    "execute": False,
                    "external_action_count": 0,
                    "output_hash": output_hash,
                    "diff_hash": diff_hash,
                },
                occurred_at=completed_at,
            )
        return completed

    def get(self, principal: Principal, shadow_run_id: UUID | str) -> ShadowRunRecord:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM shadow_run WHERE shadow_run_id = %s AND tenant_id = %s",
                (shadow_run_id, principal.tenant_id),
            ).fetchone()
        if row is None:
            raise NotFoundError()
        return _record(row)

    def events(self, principal: Principal, shadow_run_id: UUID | str) -> list[dict[str, object]]:
        self.get(principal, shadow_run_id)
        with self.database.connect() as connection:
            return connection.execute(
                """
                SELECT shadow_event_id, shadow_run_id, tenant_id, event_type,
                       actor_id, payload, occurred_at
                FROM shadow_control_event
                WHERE shadow_run_id = %s AND tenant_id = %s
                ORDER BY shadow_event_id
                """,
                (shadow_run_id, principal.tenant_id),
            ).fetchall()
