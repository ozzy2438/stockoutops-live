"""Tenant-scoped terminal ledger for alert-delivery outcomes.

`claim` and `complete` are ledger primitives, not a delivery path. Durable
delivery is owned by `alerting.outbox`; the outbox worker writes this ledger's
CLAIMED and terminal rows inside one transaction with no network call between
them. Nothing here may be used to claim a row and then perform HTTP — that was
the ADR-0008 crash gap ADR-0009 removes.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Literal

from stockoutops.alerting.contracts import AlertEvaluation
from stockoutops.database import Database
from stockoutops.errors import NotFoundError
from stockoutops.identity import Principal

LIFECYCLE_TRANSITIONS = frozenset({"FIRED", "RESOLVED"})
DeliveryStatus = Literal["CLAIMED", "DELIVERED", "FAILED"]


def _lock_key(value: str) -> int:
    digest = hashlib.sha256(value.encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


def should_notify(evaluation: AlertEvaluation) -> bool:
    return not evaluation.idempotent_replay and evaluation.transition in LIFECYCLE_TRANSITIONS


class AlertDeliveryRepository:
    """All tenant-scoped public methods receive Principal first."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def claim(
        self,
        principal: Principal,
        evaluation: AlertEvaluation,
        *,
        destination_host: str,
        payload_hash: str,
        claimed_at: datetime,
    ) -> bool:
        if evaluation.tenant_id != principal.tenant_id:
            raise NotFoundError()
        if not should_notify(evaluation):
            return False
        with self.database.connect() as connection, connection.transaction():
            connection.execute(
                "SELECT pg_advisory_xact_lock(%s)",
                (_lock_key(f"alert-delivery:{principal.tenant_id}:{evaluation.evaluation_id}"),),
            )
            row = connection.execute(
                """
                INSERT INTO alert_delivery_attempt (
                    tenant_id, evaluation_id, alert_fingerprint, transition,
                    destination_host, status, attempt_count, payload_hash, claimed_at
                ) VALUES (
                    %s, %s, %s, %s, %s, 'CLAIMED', 0, %s, %s
                )
                ON CONFLICT (tenant_id, evaluation_id) DO NOTHING
                RETURNING delivery_attempt_id
                """,
                (
                    principal.tenant_id,
                    evaluation.evaluation_id,
                    evaluation.alert_fingerprint,
                    evaluation.transition,
                    destination_host,
                    payload_hash,
                    claimed_at,
                ),
            ).fetchone()
        return row is not None

    def complete(
        self,
        principal: Principal,
        evaluation: AlertEvaluation,
        *,
        status: DeliveryStatus,
        attempt_count: int,
        http_status: int | None,
        error_class: str | None,
        completed_at: datetime,
    ) -> None:
        if evaluation.tenant_id != principal.tenant_id:
            raise NotFoundError()
        if status not in {"DELIVERED", "FAILED"}:
            raise ValueError("Delivery completion status must be DELIVERED or FAILED")
        with self.database.connect() as connection, connection.transaction():
            updated = connection.execute(
                """
                UPDATE alert_delivery_attempt
                SET status = %s,
                    attempt_count = %s,
                    http_status = %s,
                    error_class = %s,
                    completed_at = %s
                WHERE tenant_id = %s
                  AND evaluation_id = %s
                  AND status = 'CLAIMED'
                RETURNING delivery_attempt_id
                """,
                (
                    status,
                    attempt_count,
                    http_status,
                    error_class,
                    completed_at,
                    principal.tenant_id,
                    evaluation.evaluation_id,
                ),
            ).fetchone()
        if updated is None:
            raise NotFoundError()

    def attempts(self, principal: Principal, evaluation_id: int) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM alert_delivery_attempt
                WHERE tenant_id = %s AND evaluation_id = %s
                ORDER BY delivery_attempt_id
                """,
                (principal.tenant_id, evaluation_id),
            ).fetchall()
        return [dict(row) for row in rows]
