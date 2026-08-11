"""Tenant-scoped psycopg repository and transactional control primitives."""

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
from stockoutops.errors import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
)
from stockoutops.evidence.contracts import Evidence, parse_evidence
from stockoutops.identity import Principal
from stockoutops.schemas import IntakeRequest, ReviewAction
from stockoutops.state_machine import RunState, can_transition


@dataclass(frozen=True)
class RunRecord:
    run_id: UUID
    tenant_id: str
    requested_by: str
    assigned_reviewer_id: str
    sku_id: str
    store_id: str
    supplier_id: str
    as_of_ts: datetime
    window_start: datetime
    window_end: datetime
    request_hash: str
    state: RunState
    state_version: int
    draft_json: dict[str, object] | None
    draft_hash: str | None
    draft_created_at: datetime | None
    review_expires_at: datetime | None
    created_at: datetime
    updated_at: datetime


def _run(row: dict[str, Any]) -> RunRecord:
    return RunRecord(
        run_id=row["run_id"],
        tenant_id=row["tenant_id"],
        requested_by=row["requested_by"],
        assigned_reviewer_id=row["assigned_reviewer_id"],
        sku_id=row["sku_id"],
        store_id=row["store_id"],
        supplier_id=row["supplier_id"],
        as_of_ts=row["as_of_ts"],
        window_start=row["window_start"],
        window_end=row["window_end"],
        request_hash=row["request_hash"],
        state=RunState(row["state"]),
        state_version=row["state_version"],
        draft_json=row["draft_json"],
        draft_hash=row["draft_hash"],
        draft_created_at=row["draft_created_at"],
        review_expires_at=row["review_expires_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class _IdempotencyRaceLost(Exception):
    """Internal control-flow signal: another transaction committed this key first."""


def _tool_lock_key(run_id: UUID, tool_name: str) -> int:
    digest = hashlib.sha256(f"{run_id}:{tool_name}".encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


class ToolClaim:
    """Holds a session-level Postgres advisory lock across an external tool
    call on a dedicated connection.

    Session-scoped (not transaction-scoped): the lock is independent of any
    commit/rollback and is held for exactly as long as this connection
    stays open, however long the real call takes. Postgres releases it
    automatically if the connection dies (crash), so a genuinely abandoned
    attempt does not block observers forever — it just leaves the row
    'started', which is treated as a permanent stop pending manual
    recovery, not an automatic retry.
    """

    def __init__(self, connection: psycopg.Connection[dict[str, Any]], lock_key: int) -> None:
        self._connection = connection
        self._lock_key = lock_key
        self._released = False

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        try:
            self._connection.execute("SELECT pg_advisory_unlock(%s)", (self._lock_key,))
        finally:
            self._connection.close()

    def __enter__(self) -> ToolClaim:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.release()


class Repository:
    """All public tenant-scoped methods take Principal first and filter tenant_id."""

    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _insert_event(
        connection: Any,
        *,
        run_id: UUID,
        tenant_id: str,
        event_type: str,
        from_state: RunState | None,
        to_state: RunState | None,
        actor_id: str,
        payload: dict[str, object],
        occurred_at: datetime,
    ) -> None:
        connection.execute(
            """
            INSERT INTO workflow_event (
                run_id, tenant_id, event_type, from_state, to_state,
                actor_id, payload, occurred_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                run_id,
                tenant_id,
                event_type,
                from_state.value if from_state else None,
                to_state.value if to_state else None,
                actor_id,
                Jsonb(payload),
                occurred_at,
            ),
        )

    def begin_intake(
        self,
        principal: Principal,
        request: IntakeRequest,
        *,
        idempotency_key: str,
        payload_hash: str,
        assigned_reviewer_id: str,
        now: datetime,
    ) -> tuple[RunRecord, bool]:
        conflict: ConflictError | None = None
        result: RunRecord | None = None
        created = False
        with self.database.connect() as connection, connection.transaction():
            existing = connection.execute(
                """
                SELECT payload_hash, run_id
                FROM idempotency_key
                WHERE tenant_id = %s AND idempotency_key = %s
                FOR UPDATE
                """,
                (principal.tenant_id, idempotency_key),
            ).fetchone()
            if existing is None:
                run_id = uuid4()
                won_race = True
                try:
                    with connection.transaction():
                        row = connection.execute(
                            """
                            INSERT INTO investigation_run (
                                run_id, tenant_id, requested_by, assigned_reviewer_id,
                                sku_id, store_id, supplier_id, as_of_ts, window_start,
                                window_end, request_hash, state, state_version,
                                created_at, updated_at
                            ) VALUES (
                                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                'created', 0, %s, %s
                            )
                            RETURNING *
                            """,
                            (
                                run_id,
                                principal.tenant_id,
                                principal.actor_id,
                                assigned_reviewer_id,
                                request.sku_id,
                                request.store_id,
                                request.supplier_id,
                                request.as_of_ts,
                                request.window_start,
                                request.window_end,
                                payload_hash,
                                now,
                                now,
                            ),
                        ).fetchone()
                        # ON CONFLICT DO NOTHING makes concurrent inserts of the same
                        # (tenant_id, idempotency_key) resolve via Postgres's native
                        # unique-index wait: the loser blocks until the winner commits,
                        # then sees the conflict and returns no row instead of raising.
                        claimed = connection.execute(
                            """
                            INSERT INTO idempotency_key (
                                tenant_id, idempotency_key, payload_hash, run_id, created_at
                            ) VALUES (%s, %s, %s, %s, %s)
                            ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
                            RETURNING run_id
                            """,
                            (
                                principal.tenant_id,
                                idempotency_key,
                                payload_hash,
                                run_id,
                                now,
                            ),
                        ).fetchone()
                        if claimed is None:
                            won_race = False
                            raise _IdempotencyRaceLost()
                        self._insert_event(
                            connection,
                            run_id=run_id,
                            tenant_id=principal.tenant_id,
                            event_type="run_created",
                            from_state=None,
                            to_state=RunState.CREATED,
                            actor_id=principal.actor_id,
                            payload={"request_hash": payload_hash},
                            occurred_at=now,
                        )
                except _IdempotencyRaceLost:
                    pass
                if won_race:
                    result = _run(row)
                    created = True
                else:
                    # The savepoint rollback above discarded our unclaimed
                    # investigation_run insert; the winner's key row is now
                    # visible (its transaction committed before ours could
                    # proceed past the unique-index wait).
                    existing = connection.execute(
                        """
                        SELECT payload_hash, run_id
                        FROM idempotency_key
                        WHERE tenant_id = %s AND idempotency_key = %s
                        """,
                        (principal.tenant_id, idempotency_key),
                    ).fetchone()
                    if existing is None:
                        raise RuntimeError("Idempotency key conflict resolution failed")
            if existing is not None and result is None:
                row = connection.execute(
                    """
                    SELECT *
                    FROM investigation_run
                    WHERE run_id = %s AND tenant_id = %s
                    """,
                    (existing["run_id"], principal.tenant_id),
                ).fetchone()
                if row is None:
                    raise RuntimeError("Idempotency key references an inaccessible run")
                result = _run(row)
                if existing["payload_hash"] != payload_hash:
                    self._insert_event(
                        connection,
                        run_id=result.run_id,
                        tenant_id=principal.tenant_id,
                        event_type="intake_rejected",
                        from_state=result.state,
                        to_state=result.state,
                        actor_id=principal.actor_id,
                        payload={"code": "IDEMPOTENCY_KEY_CONFLICT"},
                        occurred_at=now,
                    )
                    conflict = ConflictError(
                        "IDEMPOTENCY_KEY_CONFLICT",
                        "Idempotency key was already used with a different payload",
                    )
        if conflict:
            raise conflict
        if result is None:
            raise RuntimeError("Intake transaction returned no run")
        return result, created

    def get_run(self, principal: Principal, run_id: UUID | str) -> RunRecord:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM investigation_run WHERE run_id = %s AND tenant_id = %s",
                (run_id, principal.tenant_id),
            ).fetchone()
        if row is None:
            raise NotFoundError()
        return _run(row)

    def append_rejected_control(
        self,
        principal: Principal,
        run_id: UUID | str,
        *,
        code: str,
        now: datetime,
    ) -> None:
        run = self.get_run(principal, run_id)
        with self.database.connect() as connection, connection.transaction():
            self._insert_event(
                connection,
                run_id=run.run_id,
                tenant_id=principal.tenant_id,
                event_type="control_rejected",
                from_state=run.state,
                to_state=run.state,
                actor_id=principal.actor_id,
                payload={"code": code},
                occurred_at=now,
            )

    def transition(
        self,
        principal: Principal,
        run: RunRecord,
        target: RunState,
        *,
        event_type: str,
        now: datetime,
        payload: dict[str, object] | None = None,
    ) -> RunRecord:
        if not can_transition(run.state, target):
            self.append_rejected_control(principal, run.run_id, code="INVALID_TRANSITION", now=now)
            raise ConflictError(
                "INVALID_TRANSITION",
                f"Transition {run.state.value} -> {target.value} is not allowed",
            )
        updated: dict[str, Any] | None
        with self.database.connect() as connection, connection.transaction():
            updated = connection.execute(
                """
                UPDATE investigation_run
                SET state = %s, state_version = state_version + 1, updated_at = %s
                WHERE run_id = %s AND tenant_id = %s
                  AND state = %s AND state_version = %s
                RETURNING *
                """,
                (
                    target.value,
                    now,
                    run.run_id,
                    principal.tenant_id,
                    run.state.value,
                    run.state_version,
                ),
            ).fetchone()
            if updated:
                self._insert_event(
                    connection,
                    run_id=run.run_id,
                    tenant_id=principal.tenant_id,
                    event_type=event_type,
                    from_state=run.state,
                    to_state=target,
                    actor_id=principal.actor_id,
                    payload=payload or {},
                    occurred_at=now,
                )
        if updated is None:
            self.append_rejected_control(
                principal, run.run_id, code="STATE_VERSION_CONFLICT", now=now
            )
            raise ConflictError("STATE_VERSION_CONFLICT", "Run state changed concurrently")
        return _run(updated)

    def set_draft_and_transition(
        self,
        principal: Principal,
        run: RunRecord,
        *,
        draft: dict[str, object],
        draft_hash: str,
        now: datetime,
        expires_at: datetime,
    ) -> RunRecord:
        target = RunState.AWAITING_HUMAN
        if not can_transition(run.state, target):
            self.append_rejected_control(principal, run.run_id, code="INVALID_TRANSITION", now=now)
            raise ConflictError("INVALID_TRANSITION", "Run cannot accept a draft")
        with self.database.connect() as connection, connection.transaction():
            updated = connection.execute(
                """
                UPDATE investigation_run
                SET state = %s,
                    state_version = state_version + 1,
                    draft_json = %s,
                    draft_hash = %s,
                    draft_created_at = %s,
                    review_expires_at = %s,
                    updated_at = %s
                WHERE run_id = %s AND tenant_id = %s
                  AND state = %s AND state_version = %s
                RETURNING *
                """,
                (
                    target.value,
                    Jsonb(draft),
                    draft_hash,
                    now,
                    expires_at,
                    now,
                    run.run_id,
                    principal.tenant_id,
                    run.state.value,
                    run.state_version,
                ),
            ).fetchone()
            if updated:
                self._insert_event(
                    connection,
                    run_id=run.run_id,
                    tenant_id=principal.tenant_id,
                    event_type="draft_ready",
                    from_state=run.state,
                    to_state=target,
                    actor_id=principal.actor_id,
                    payload={"draft_hash": draft_hash, "expires_at": expires_at.isoformat()},
                    occurred_at=now,
                )
        if updated is None:
            self.append_rejected_control(
                principal, run.run_id, code="STATE_VERSION_CONFLICT", now=now
            )
            raise ConflictError("STATE_VERSION_CONFLICT", "Run state changed concurrently")
        return _run(updated)

    def claim_or_observe_tool(
        self,
        principal: Principal,
        run_id: UUID,
        *,
        tool_name: str,
        request_hash: str,
        now: datetime,
    ) -> tuple[dict[str, Any], ToolClaim | None]:
        """Serialize every caller for this (run_id, tool_name) on a single
        Postgres session advisory lock instead of a fixed poll/timeout.

        A duplicate caller blocks for exactly as long as the true owner's
        call takes — matching the accepted up-to-30s reasoning bound with
        no hard-coded "should be fast" assumption — rather than racing a
        timer against it. Returns `(row, None)` if another attempt already
        exists: completed, genuinely failed, or abandoned (the lock is free
        again because that session ended without finishing, so the row is
        still 'started' — callers must treat this as a permanent stop, not
        retry it, preserving manual recovery/replay as the only way past a
        crashed attempt). Returns `(row, claim)` if this call is the
        exclusive owner: it must do the work, call `complete_tool`, then
        release the claim (release also happens automatically if the
        connection is dropped, e.g. on crash).
        """
        connection = psycopg.connect(self.database.dsn, row_factory=dict_row, autocommit=True)
        lock_key = _tool_lock_key(run_id, tool_name)
        connection.execute("SELECT pg_advisory_lock(%s)", (lock_key,))
        existing = connection.execute(
            """
            SELECT *
            FROM tool_invocation
            WHERE run_id = %s AND tenant_id = %s AND tool_name = %s
            """,
            (run_id, principal.tenant_id, tool_name),
        ).fetchone()
        if existing is not None:
            connection.execute("SELECT pg_advisory_unlock(%s)", (lock_key,))
            connection.close()
            return existing, None
        row = connection.execute(
            """
            INSERT INTO tool_invocation (
                run_id, tenant_id, tool_name, tool_schema_version,
                request_hash, status, created_at
            ) VALUES (%s, %s, %s, 'v1', %s, 'started', %s)
            RETURNING *
            """,
            (run_id, principal.tenant_id, tool_name, request_hash, now),
        ).fetchone()
        return row, ToolClaim(connection, lock_key)

    def complete_tool(
        self,
        principal: Principal,
        run_id: UUID,
        *,
        tool_name: str,
        result: dict[str, object] | None,
        metadata: dict[str, object],
        status: str,
        now: datetime,
    ) -> None:
        with self.database.connect() as connection, connection.transaction():
            updated = connection.execute(
                """
                UPDATE tool_invocation
                SET status = %s, result_json = %s, metadata_json = %s, completed_at = %s
                WHERE run_id = %s AND tenant_id = %s AND tool_name = %s
                RETURNING invocation_id
                """,
                (
                    status,
                    Jsonb(result) if result is not None else None,
                    Jsonb(metadata),
                    now,
                    run_id,
                    principal.tenant_id,
                    tool_name,
                ),
            ).fetchone()
        if updated is None:
            raise ConflictError("TOOL_INVOCATION_MISSING", "Tool invocation was not started")

    def get_tool(
        self, principal: Principal, run_id: UUID, tool_name: str
    ) -> dict[str, object] | None:
        with self.database.connect() as connection:
            return connection.execute(
                """
                SELECT *
                FROM tool_invocation
                WHERE run_id = %s AND tenant_id = %s AND tool_name = %s
                """,
                (run_id, principal.tenant_id, tool_name),
            ).fetchone()

    def list_evidence(self, principal: Principal, run_id: UUID) -> list[Evidence]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT result_json
                FROM tool_invocation
                WHERE run_id = %s AND tenant_id = %s
                  AND tool_name IN ('T1_inventory', 'T2_sales_demand', 'T3_supplier')
                  AND status = 'completed'
                ORDER BY tool_name
                """,
                (run_id, principal.tenant_id),
            ).fetchall()
        return [parse_evidence(row["result_json"]) for row in rows]

    def record_review(
        self,
        principal: Principal,
        run_id: UUID | str,
        *,
        idempotency_key: str,
        action: ReviewAction,
        submitted_draft_hash: str,
        edited_payload: dict[str, object] | None,
        edited_payload_hash: str | None,
        reason: str | None,
        now: datetime,
    ) -> RunRecord:
        target = {
            ReviewAction.APPROVE: RunState.APPROVED,
            ReviewAction.EDIT_APPROVE: RunState.EDITED_AND_APPROVED,
            ReviewAction.REJECT: RunState.REJECTED,
            ReviewAction.ESCALATE: RunState.ESCALATED,
        }[action]
        pending_error: ConflictError | AuthorizationError | None = None
        result: RunRecord | None = None
        with self.database.connect() as connection, connection.transaction():
            row = connection.execute(
                """
                SELECT *
                FROM investigation_run
                WHERE run_id = %s AND tenant_id = %s
                FOR UPDATE
                """,
                (run_id, principal.tenant_id),
            ).fetchone()
            if row is None:
                raise NotFoundError()
            run = _run(row)
            existing = connection.execute(
                """
                SELECT decision_id FROM review_decision
                WHERE run_id = %s AND tenant_id = %s
                """,
                (run.run_id, principal.tenant_id),
            ).fetchone()
            code: str | None = None
            if existing or run.state != RunState.AWAITING_HUMAN:
                code = "RUN_ALREADY_DECIDED"
                pending_error = ConflictError(code, "Run is not awaiting a review decision")
            elif principal.actor_id != run.assigned_reviewer_id:
                code = "WRONG_REVIEWER"
                pending_error = AuthorizationError("Reviewer is not assigned to this run")
            elif submitted_draft_hash != run.draft_hash:
                code = "STALE_APPROVAL_TARGET"
                pending_error = ConflictError(code, "Submitted draft hash is stale")
            elif run.review_expires_at is None or now > run.review_expires_at:
                code = "REVIEW_EXPIRED"
                pending_error = ConflictError(code, "Review fixture-policy window has expired")

            if pending_error:
                self._insert_event(
                    connection,
                    run_id=run.run_id,
                    tenant_id=principal.tenant_id,
                    event_type="review_rejected",
                    from_state=run.state,
                    to_state=run.state,
                    actor_id=principal.actor_id,
                    payload={"code": code or "REVIEW_REJECTED"},
                    occurred_at=now,
                )
            else:
                connection.execute(
                    """
                    INSERT INTO review_decision (
                        run_id, tenant_id, idempotency_key, action, reviewer_id,
                        original_draft, original_draft_hash, edited_payload,
                        edited_payload_hash, reason, decided_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        run.run_id,
                        principal.tenant_id,
                        idempotency_key,
                        action.value,
                        principal.actor_id,
                        Jsonb(run.draft_json),
                        run.draft_hash,
                        Jsonb(edited_payload) if edited_payload is not None else None,
                        edited_payload_hash,
                        reason,
                        now,
                    ),
                )
                decided = connection.execute(
                    """
                    UPDATE investigation_run
                    SET state = %s, state_version = state_version + 1, updated_at = %s
                    WHERE run_id = %s AND tenant_id = %s
                      AND state = 'awaiting_human' AND state_version = %s
                    RETURNING *
                    """,
                    (
                        target.value,
                        now,
                        run.run_id,
                        principal.tenant_id,
                        run.state_version,
                    ),
                ).fetchone()
                if decided is None:
                    raise RuntimeError("Locked review transition unexpectedly conflicted")
                self._insert_event(
                    connection,
                    run_id=run.run_id,
                    tenant_id=principal.tenant_id,
                    event_type="review_decided",
                    from_state=RunState.AWAITING_HUMAN,
                    to_state=target,
                    actor_id=principal.actor_id,
                    payload={"action": action.value, "draft_hash": submitted_draft_hash},
                    occurred_at=now,
                )
                closed = connection.execute(
                    """
                    UPDATE investigation_run
                    SET state = 'closed', state_version = state_version + 1, updated_at = %s
                    WHERE run_id = %s AND tenant_id = %s
                      AND state = %s AND state_version = %s
                    RETURNING *
                    """,
                    (
                        now,
                        run.run_id,
                        principal.tenant_id,
                        target.value,
                        decided["state_version"],
                    ),
                ).fetchone()
                if closed is None:
                    raise RuntimeError("Locked close transition unexpectedly conflicted")
                self._insert_event(
                    connection,
                    run_id=run.run_id,
                    tenant_id=principal.tenant_id,
                    event_type="run_closed",
                    from_state=target,
                    to_state=RunState.CLOSED,
                    actor_id=principal.actor_id,
                    payload={},
                    occurred_at=now,
                )
                result = _run(closed)
        if pending_error:
            raise pending_error
        if result is None:
            raise RuntimeError("Review transaction returned no run")
        return result

    def get_decision(self, principal: Principal, run_id: UUID | str) -> dict[str, object] | None:
        with self.database.connect() as connection:
            return connection.execute(
                """
                SELECT *
                FROM review_decision
                WHERE run_id = %s AND tenant_id = %s
                """,
                (run_id, principal.tenant_id),
            ).fetchone()

    def audit(self, principal: Principal, run_id: UUID | str) -> list[dict[str, object]]:
        self.get_run(principal, run_id)
        with self.database.connect() as connection:
            return connection.execute(
                """
                SELECT event_id, run_id, tenant_id, event_type, from_state,
                       to_state, actor_id, payload, occurred_at
                FROM workflow_event
                WHERE run_id = %s AND tenant_id = %s
                ORDER BY event_id
                """,
                (run_id, principal.tenant_id),
            ).fetchall()

    def fetch_inventory_fixture(
        self, principal: Principal, sku_id: str, store_id: str
    ) -> dict[str, object] | None:
        with self.database.connect() as connection:
            return connection.execute(
                """
                SELECT sku_id, store_id, on_hand, reserved, on_order, updated_at
                FROM inventory_fixture
                WHERE tenant_id = %s AND sku_id = %s AND store_id = %s
                """,
                (principal.tenant_id, sku_id, store_id),
            ).fetchone()

    def fetch_demand_fixture(
        self,
        principal: Principal,
        sku_id: str,
        store_id: str,
        window_start: datetime,
        window_end: datetime,
    ) -> dict[str, object] | None:
        with self.database.connect() as connection:
            return connection.execute(
                """
                SELECT sku_id, store_id, units_sold, average_daily_units,
                       demand_signal, updated_at
                FROM demand_fixture
                WHERE tenant_id = %s AND sku_id = %s AND store_id = %s
                  AND window_start = %s AND window_end = %s
                """,
                (
                    principal.tenant_id,
                    sku_id,
                    store_id,
                    window_start,
                    window_end,
                ),
            ).fetchone()

    def fetch_supplier_fixture(
        self, principal: Principal, sku_id: str, supplier_id: str
    ) -> dict[str, object] | None:
        with self.database.connect() as connection:
            return connection.execute(
                """
                SELECT sku_id, supplier_id, open_order_quantity,
                       expected_receipt_at, historical_lead_time_days,
                       status, updated_at
                FROM supplier_fixture
                WHERE tenant_id = %s AND sku_id = %s AND supplier_id = %s
                """,
                (principal.tenant_id, sku_id, supplier_id),
            ).fetchone()
