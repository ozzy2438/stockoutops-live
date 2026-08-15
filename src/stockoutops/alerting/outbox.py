"""Durable PostgreSQL alert-delivery outbox.

Delivery intent is committed inside the alert-evaluation transaction. A leased
worker performs HTTP strictly outside any transaction and records bounded,
append-only attempt evidence.

This is durable at-least-once *processing*. It is not exactly-once network
delivery; see ADR-0009.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from psycopg import Connection
from psycopg.types.json import Jsonb

from stockoutops.database import Database
from stockoutops.errors import ConflictError, NotFoundError
from stockoutops.identity import Principal

OutboxState = Literal["PENDING", "IN_FLIGHT", "DELIVERED", "DEAD_LETTER"]
AttemptOutcome = Literal["DELIVERED", "RETRYABLE_FAILURE", "PERMANENT_FAILURE", "AMBIGUOUS"]

DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_LEASE_SECONDS = 30.0
DEFAULT_BACKOFF_BASE_SECONDS = 2.0
DEFAULT_BACKOFF_CAP_SECONDS = 300.0
MAX_ATTEMPT_CEILING = 100


def delivery_idempotency_key(tenant_id: str, evaluation_id: int, transition: str) -> str:
    """Deterministic and stable across replay, retry, lease takeover, and re-drive."""

    return f"{tenant_id}:{evaluation_id}:{transition}"


def backoff_delay_seconds(
    attempt_count: int,
    *,
    base_seconds: float = DEFAULT_BACKOFF_BASE_SECONDS,
    cap_seconds: float = DEFAULT_BACKOFF_CAP_SECONDS,
) -> float:
    """Deterministic bounded exponential backoff. attempt_count is 1-based."""

    if attempt_count < 1:
        raise ValueError("attempt_count must be >= 1")
    exponent = min(attempt_count - 1, 16)
    return min(base_seconds * (2**exponent), cap_seconds)


@dataclass(frozen=True)
class LeasedDelivery:
    """One leased delivery intent. Carries its own tenant context."""

    outbox_id: int
    tenant_id: str
    evaluation_id: int
    alert_fingerprint: str
    transition: str
    destination_host: str
    payload: dict[str, Any]
    payload_hash: str
    idempotency_key: str
    attempt_number: int
    max_attempts: int
    lease_owner: str
    lease_expires_at: datetime

    @property
    def is_final_attempt(self) -> bool:
        return self.attempt_number >= self.max_attempts


class AlertOutboxRepository:
    """Tenant-scoped public methods receive Principal first.

    `lease` is the one deliberate exception: it is the background worker's
    cross-tenant scan. Every row it returns carries its own `tenant_id`, and all
    subsequent writes are constrained to that value both here and by the
    database triggers in migration 0008.
    """

    def __init__(self, database: Database) -> None:
        self.database = database

    # -- enqueue -----------------------------------------------------------

    @staticmethod
    def enqueue_in_transaction(
        connection: Connection[dict[str, Any]],
        *,
        tenant_id: str,
        evaluation_id: int,
        alert_fingerprint: str,
        transition: str,
        destination_host: str,
        payload: dict[str, Any],
        payload_hash: str,
        enqueued_at: datetime,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> int | None:
        """Insert delivery intent using the caller's open transaction.

        The caller owns the transaction so the intent commits atomically with
        the alert evaluation append. Returns the new outbox id, or None when an
        intent already exists for this tenant/evaluation.
        """

        if max_attempts < 1 or max_attempts > MAX_ATTEMPT_CEILING:
            raise ValueError("max_attempts is outside the allowed bound")
        row = connection.execute(
            """
            INSERT INTO alert_outbox (
                tenant_id, evaluation_id, alert_fingerprint, transition,
                destination_host, payload_json, payload_hash, idempotency_key,
                state, attempt_count, max_attempts, redrive_count,
                next_attempt_at, enqueued_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, 'PENDING', 0, %s, 0, %s, %s, %s
            )
            ON CONFLICT (tenant_id, evaluation_id) DO NOTHING
            RETURNING outbox_id
            """,
            (
                tenant_id,
                evaluation_id,
                alert_fingerprint,
                transition,
                destination_host,
                Jsonb(payload),
                payload_hash,
                delivery_idempotency_key(tenant_id, evaluation_id, transition),
                max_attempts,
                enqueued_at,
                enqueued_at,
                enqueued_at,
            ),
        ).fetchone()
        return None if row is None else int(row["outbox_id"])

    # -- worker lease ------------------------------------------------------

    def lease(
        self,
        *,
        worker_id: str,
        now: datetime,
        lease_seconds: float = DEFAULT_LEASE_SECONDS,
        batch_size: int = 10,
    ) -> list[LeasedDelivery]:
        """Atomically claim due work. Takes over leases that have expired.

        `FOR UPDATE SKIP LOCKED` keeps competing workers from claiming the same
        row. No network call happens here; the transaction closes before the
        worker sends anything.
        """

        if not worker_id:
            raise ValueError("worker_id is required")
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        lease_expires_at = now + timedelta(seconds=lease_seconds)
        with self.database.connect() as connection, connection.transaction():
            candidates = connection.execute(
                """
                SELECT outbox_id
                FROM alert_outbox
                WHERE next_attempt_at <= %s
                  AND (
                        state = 'PENDING'
                        OR (state = 'IN_FLIGHT' AND lease_expires_at <= %s)
                  )
                  AND attempt_count < max_attempts
                ORDER BY next_attempt_at, outbox_id
                LIMIT %s
                FOR UPDATE SKIP LOCKED
                """,
                (now, now, batch_size),
            ).fetchall()
            if not candidates:
                return []
            ids = [int(row["outbox_id"]) for row in candidates]
            rows = connection.execute(
                """
                UPDATE alert_outbox
                SET state = 'IN_FLIGHT',
                    attempt_count = attempt_count + 1,
                    lease_owner = %s,
                    lease_expires_at = %s,
                    updated_at = %s
                WHERE outbox_id = ANY(%s)
                RETURNING *
                """,
                (worker_id, lease_expires_at, now, ids),
            ).fetchall()
        return [
            LeasedDelivery(
                outbox_id=int(row["outbox_id"]),
                tenant_id=row["tenant_id"],
                evaluation_id=int(row["evaluation_id"]),
                alert_fingerprint=row["alert_fingerprint"],
                transition=row["transition"],
                destination_host=row["destination_host"],
                payload=dict(row["payload_json"]),
                payload_hash=row["payload_hash"],
                idempotency_key=row["idempotency_key"],
                attempt_number=int(row["attempt_count"]),
                max_attempts=int(row["max_attempts"]),
                lease_owner=worker_id,
                lease_expires_at=lease_expires_at,
            )
            for row in sorted(rows, key=lambda item: int(item["outbox_id"]))
        ]

    # -- attempt outcomes --------------------------------------------------

    def record_delivered(
        self,
        leased: LeasedDelivery,
        *,
        http_status: int,
        started_at: datetime,
        completed_at: datetime,
    ) -> None:
        if not 200 <= http_status < 300:
            raise ValueError("record_delivered requires a 2xx status")
        with self.database.connect() as connection, connection.transaction():
            self._append_attempt_event(
                connection,
                leased,
                outcome="DELIVERED",
                http_status=http_status,
                error_class=None,
                started_at=started_at,
                completed_at=completed_at,
            )
            self._write_terminal_ledger(
                connection,
                leased,
                status="DELIVERED",
                http_status=http_status,
                error_class=None,
                completed_at=completed_at,
            )
            self._transition(
                connection,
                leased,
                state="DELIVERED",
                next_attempt_at=None,
                last_http_status=http_status,
                last_error_class=None,
                completed_at=completed_at,
                now=completed_at,
            )

    def record_retry(
        self,
        leased: LeasedDelivery,
        *,
        outcome: AttemptOutcome,
        http_status: int | None,
        error_class: str,
        started_at: datetime,
        completed_at: datetime,
        backoff_base_seconds: float = DEFAULT_BACKOFF_BASE_SECONDS,
    ) -> datetime:
        """Return the row to PENDING with bounded backoff."""

        if outcome not in {"RETRYABLE_FAILURE", "AMBIGUOUS"}:
            raise ValueError("record_retry accepts only retryable or ambiguous outcomes")
        if leased.is_final_attempt:
            raise ConflictError(
                "OUTBOX_RETRY_BUDGET_EXHAUSTED",
                "Retry budget is exhausted; record a dead letter instead",
            )
        delay = backoff_delay_seconds(leased.attempt_number, base_seconds=backoff_base_seconds)
        next_attempt_at = completed_at + timedelta(seconds=delay)
        with self.database.connect() as connection, connection.transaction():
            self._append_attempt_event(
                connection,
                leased,
                outcome=outcome,
                http_status=http_status,
                error_class=error_class,
                started_at=started_at,
                completed_at=completed_at,
            )
            self._transition(
                connection,
                leased,
                state="PENDING",
                next_attempt_at=next_attempt_at,
                last_http_status=http_status,
                last_error_class=error_class,
                completed_at=None,
                now=completed_at,
            )
        return next_attempt_at

    def record_dead_letter(
        self,
        leased: LeasedDelivery,
        *,
        outcome: AttemptOutcome,
        http_status: int | None,
        error_class: str,
        started_at: datetime,
        completed_at: datetime,
    ) -> None:
        if outcome not in {"RETRYABLE_FAILURE", "PERMANENT_FAILURE", "AMBIGUOUS"}:
            raise ValueError("record_dead_letter requires a failure or ambiguous outcome")
        with self.database.connect() as connection, connection.transaction():
            self._append_attempt_event(
                connection,
                leased,
                outcome=outcome,
                http_status=http_status,
                error_class=error_class,
                started_at=started_at,
                completed_at=completed_at,
            )
            self._write_terminal_ledger(
                connection,
                leased,
                status="FAILED",
                http_status=http_status,
                error_class=error_class,
                completed_at=completed_at,
            )
            self._transition(
                connection,
                leased,
                state="DEAD_LETTER",
                next_attempt_at=None,
                last_http_status=http_status,
                last_error_class=error_class,
                completed_at=completed_at,
                now=completed_at,
            )

    # -- re-drive ----------------------------------------------------------

    def redrive(
        self,
        principal: Principal,
        outbox_id: int,
        *,
        now: datetime,
        additional_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> None:
        """Move one dead-lettered row back to PENDING with a raised ceiling.

        Deliberately explicit and tenant-scoped: re-drive is an operator action,
        never automatic.
        """

        if additional_attempts < 1:
            raise ValueError("additional_attempts must be >= 1")
        with self.database.connect() as connection, connection.transaction():
            row = connection.execute(
                """
                SELECT outbox_id, attempt_count, max_attempts, redrive_count, state
                FROM alert_outbox
                WHERE tenant_id = %s AND outbox_id = %s
                FOR UPDATE
                """,
                (principal.tenant_id, outbox_id),
            ).fetchone()
            if row is None:
                raise NotFoundError()
            if row["state"] != "DEAD_LETTER":
                raise ConflictError(
                    "OUTBOX_NOT_DEAD_LETTERED",
                    "Only a DEAD_LETTER row may be re-driven",
                )
            new_ceiling = min(int(row["attempt_count"]) + additional_attempts, MAX_ATTEMPT_CEILING)
            if new_ceiling <= int(row["attempt_count"]):
                raise ConflictError(
                    "OUTBOX_ATTEMPT_CEILING_REACHED",
                    "Re-drive cannot raise the attempt ceiling any further",
                )
            connection.execute(
                """
                UPDATE alert_outbox
                SET state = 'PENDING',
                    max_attempts = %s,
                    redrive_count = redrive_count + 1,
                    next_attempt_at = %s,
                    completed_at = NULL,
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    updated_at = %s
                WHERE tenant_id = %s AND outbox_id = %s AND state = 'DEAD_LETTER'
                """,
                (new_ceiling, now, now, principal.tenant_id, outbox_id),
            )

    # -- reads -------------------------------------------------------------

    def get(self, principal: Principal, outbox_id: int) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM alert_outbox WHERE tenant_id = %s AND outbox_id = %s",
                (principal.tenant_id, outbox_id),
            ).fetchone()
        if row is None:
            raise NotFoundError()
        return dict(row)

    def for_evaluation(self, principal: Principal, evaluation_id: int) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM alert_outbox WHERE tenant_id = %s AND evaluation_id = %s",
                (principal.tenant_id, evaluation_id),
            ).fetchone()
        return None if row is None else dict(row)

    def attempt_events(self, principal: Principal, outbox_id: int) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM alert_delivery_attempt_event
                WHERE tenant_id = %s AND outbox_id = %s
                ORDER BY attempt_number
                """,
                (principal.tenant_id, outbox_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def dead_letters(self, principal: Principal) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM alert_outbox
                WHERE tenant_id = %s AND state = 'DEAD_LETTER'
                ORDER BY outbox_id
                """,
                (principal.tenant_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def pending_backlog(self, principal: Principal) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM alert_outbox
                WHERE tenant_id = %s AND state IN ('PENDING', 'IN_FLIGHT')
                ORDER BY outbox_id
                """,
                (principal.tenant_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    # -- internals ---------------------------------------------------------

    def _append_attempt_event(
        self,
        connection: Connection[dict[str, Any]],
        leased: LeasedDelivery,
        *,
        outcome: AttemptOutcome,
        http_status: int | None,
        error_class: str | None,
        started_at: datetime,
        completed_at: datetime,
    ) -> None:
        active = connection.execute(
            """
            SELECT outbox_id
            FROM alert_outbox
            WHERE outbox_id = %s
              AND state = 'IN_FLIGHT'
              AND attempt_count = %s
              AND lease_owner = %s
            FOR UPDATE
            """,
            (
                leased.outbox_id,
                leased.attempt_number,
                leased.lease_owner,
            ),
        ).fetchone()
        if active is None:
            raise ConflictError(
                "OUTBOX_LEASE_LOST",
                "The delivery lease was taken over before this outcome was recorded",
            )
        connection.execute(
            """
            INSERT INTO alert_delivery_attempt_event (
                outbox_id, tenant_id, evaluation_id, attempt_number, outcome,
                http_status, error_class, lease_owner, idempotency_key,
                started_at, completed_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (outbox_id, attempt_number) DO NOTHING
            """,
            (
                leased.outbox_id,
                leased.tenant_id,
                leased.evaluation_id,
                leased.attempt_number,
                outcome,
                http_status,
                error_class,
                leased.lease_owner,
                leased.idempotency_key,
                started_at,
                completed_at,
            ),
        )

    def _transition(
        self,
        connection: Connection[dict[str, Any]],
        leased: LeasedDelivery,
        *,
        state: OutboxState,
        next_attempt_at: datetime | None,
        last_http_status: int | None,
        last_error_class: str | None,
        completed_at: datetime | None,
        now: datetime,
    ) -> None:
        """Apply the outcome only if this worker still holds the lease.

        A worker whose lease expired and was taken over must not overwrite the
        new owner's progress, so the update is conditional on lease ownership.
        """

        updated = connection.execute(
            """
            UPDATE alert_outbox
            SET state = %s,
                next_attempt_at = COALESCE(%s, next_attempt_at),
                last_http_status = %s,
                last_error_class = %s,
                completed_at = %s,
                lease_owner = NULL,
                lease_expires_at = NULL,
                updated_at = %s
            WHERE outbox_id = %s
              AND tenant_id = %s
              AND state = 'IN_FLIGHT'
              AND lease_owner = %s
            RETURNING outbox_id
            """,
            (
                state,
                next_attempt_at,
                last_http_status,
                last_error_class,
                completed_at,
                now,
                leased.outbox_id,
                leased.tenant_id,
                leased.lease_owner,
            ),
        ).fetchone()
        if updated is None:
            raise ConflictError(
                "OUTBOX_LEASE_LOST",
                "The delivery lease was taken over before this outcome was recorded",
            )

    def _write_terminal_ledger(
        self,
        connection: Connection[dict[str, Any]],
        leased: LeasedDelivery,
        *,
        status: Literal["DELIVERED", "FAILED"],
        http_status: int | None,
        error_class: str | None,
        completed_at: datetime,
    ) -> None:
        """Write the 0007 terminal ledger row inside the same transaction.

        No network call sits between the CLAIMED insert and the terminal update,
        so the 0007 guards keep holding without reintroducing a crash gap. A row
        left CLAIMED by an earlier crash is completed here instead of duplicated.
        """

        connection.execute(
            """
            INSERT INTO alert_delivery_attempt (
                tenant_id, evaluation_id, alert_fingerprint, transition,
                destination_host, status, attempt_count, payload_hash, claimed_at
            ) VALUES (%s, %s, %s, %s, %s, 'CLAIMED', 0, %s, %s)
            ON CONFLICT (tenant_id, evaluation_id) DO NOTHING
            """,
            (
                leased.tenant_id,
                leased.evaluation_id,
                leased.alert_fingerprint,
                leased.transition,
                leased.destination_host,
                leased.payload_hash,
                completed_at,
            ),
        )
        connection.execute(
            """
            UPDATE alert_delivery_attempt
            SET status = %s,
                attempt_count = %s,
                http_status = %s,
                error_class = %s,
                completed_at = %s
            WHERE tenant_id = %s AND evaluation_id = %s AND status = 'CLAIMED'
            """,
            (
                status,
                leased.attempt_number,
                http_status,
                error_class,
                completed_at,
                leased.tenant_id,
                leased.evaluation_id,
            ),
        )


def utcnow() -> datetime:
    return datetime.now(UTC)
