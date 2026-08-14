"""Tenant-scoped append-only PostgreSQL alert evaluation history."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from psycopg.types.json import Jsonb

from stockoutops.alerting.contracts import (
    AlertEvaluation,
    AlertMetricSnapshot,
    AlertState,
    PolicyAssessment,
)
from stockoutops.database import Database
from stockoutops.errors import ConflictError, NotFoundError
from stockoutops.evidence.provenance import canonical_hash
from stockoutops.identity import Principal


def _lock_key(value: str) -> int:
    digest = hashlib.sha256(value.encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


def alert_fingerprint(snapshot: AlertMetricSnapshot, assessment: PolicyAssessment) -> str:
    """Fingerprint excludes window/input values so later windows can resolve one alert."""

    return canonical_hash(
        {
            "policy_id": assessment.policy_id,
            "policy_version": assessment.policy_version,
            "tenant_id": snapshot.correlation.tenant_id,
            "run_id": snapshot.correlation.run_id,
            "case_id": snapshot.correlation.case_id,
        }
    )


def _row_to_evaluation(row: dict[str, Any], *, idempotent_replay: bool) -> AlertEvaluation:
    return AlertEvaluation(
        evaluation_id=row["alert_evaluation_id"],
        alert_fingerprint=row["alert_fingerprint"],
        policy_id=row["policy_id"],
        policy_version=row["policy_version"],
        metric_name=row["metric_name"],
        tenant_id=row["tenant_id"],
        correlation=row["correlation_json"],
        severity=row["severity"],
        state=row["state"],
        previous_state=row["previous_state"],
        transition=row["transition"],
        measurement_status=row["measurement_status"],
        threshold_classification=row["threshold_classification"],
        threshold_value=float(row["threshold_value"]),
        comparator=row["comparator"],
        observed_value=(
            float(row["observed_value"]) if row["observed_value"] is not None else None
        ),
        window=row["window_label"],
        window_id=row["window_id"],
        evidence_label=row["evidence_label"],
        source_report_sha256=row["source_report_sha256"],
        payload_hash=row["payload_hash"],
        idempotency_key=row["idempotency_key"],
        live_slo_evidence_eligible=row["live_slo_evidence_eligible"],
        execute=row["execute"],
        external_alert_delivery_count=row["external_alert_delivery_count"],
        actor_id=row["actor_id"],
        evaluated_at=row["evaluated_at"],
        idempotent_replay=idempotent_replay,
    )


def _next_state(
    previous: AlertState | None,
    assessment: PolicyAssessment,
) -> tuple[AlertState | None, str]:
    if assessment.measurement_status == "UNMEASURED":
        return None, "UNMEASURED"
    if assessment.breached:
        return "FIRING", "STILL_FIRING" if previous == "FIRING" else "FIRED"
    if previous == "FIRING":
        return "RESOLVED", "RESOLVED"
    return "OK", "STILL_OK" if previous is not None else "INITIAL_OK"


class AlertRepository:
    """All tenant-scoped public methods receive Principal first."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def record(
        self,
        principal: Principal,
        snapshot: AlertMetricSnapshot,
        assessment: PolicyAssessment,
        *,
        idempotency_key: str,
        evaluated_at: datetime,
    ) -> AlertEvaluation:
        if snapshot.correlation.tenant_id != principal.tenant_id:
            raise NotFoundError()
        fingerprint = alert_fingerprint(snapshot, assessment)
        payload_hash = canonical_hash(
            {
                "snapshot": snapshot.model_dump(mode="json"),
                "assessment": assessment.model_dump(mode="json"),
            }
        )
        with self.database.connect() as connection, connection.transaction():
            connection.execute(
                "SELECT pg_advisory_xact_lock(%s)",
                (_lock_key(f"alert:{principal.tenant_id}:{fingerprint}"),),
            )
            existing = connection.execute(
                """
                SELECT * FROM alert_evaluation_event
                WHERE tenant_id = %s AND alert_fingerprint = %s AND idempotency_key = %s
                """,
                (principal.tenant_id, fingerprint, idempotency_key),
            ).fetchone()
            if existing is not None:
                if existing["payload_hash"] != payload_hash:
                    raise ConflictError(
                        "ALERT_IDEMPOTENCY_CONFLICT",
                        "Alert idempotency key was already used with a different payload",
                    )
                return _row_to_evaluation(existing, idempotent_replay=True)

            duplicate = connection.execute(
                """
                SELECT * FROM alert_evaluation_event
                WHERE tenant_id = %s AND alert_fingerprint = %s AND payload_hash = %s
                """,
                (principal.tenant_id, fingerprint, payload_hash),
            ).fetchone()
            if duplicate is not None:
                return _row_to_evaluation(duplicate, idempotent_replay=True)

            latest = connection.execute(
                """
                SELECT state FROM alert_evaluation_event
                WHERE tenant_id = %s AND alert_fingerprint = %s AND state IS NOT NULL
                ORDER BY alert_evaluation_id DESC LIMIT 1
                """,
                (principal.tenant_id, fingerprint),
            ).fetchone()
            previous: AlertState | None = latest["state"] if latest is not None else None
            state, transition = _next_state(previous, assessment)
            row = connection.execute(
                """
                INSERT INTO alert_evaluation_event (
                    alert_fingerprint, tenant_id, policy_id, policy_version, metric_name,
                    severity, state, previous_state, transition, measurement_status,
                    threshold_classification, threshold_value, comparator, observed_value,
                    window_label, window_id, evidence_label, source_report_sha256,
                    correlation_json, payload_hash, idempotency_key,
                    live_slo_evidence_eligible, execute, external_alert_delivery_count,
                    actor_id, evaluated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '>', %s,
                    %s, %s, %s, %s, %s, %s, %s, false, false, 0, %s, %s
                ) RETURNING *
                """,
                (
                    fingerprint,
                    principal.tenant_id,
                    assessment.policy_id,
                    assessment.policy_version,
                    assessment.metric_name,
                    assessment.severity,
                    state,
                    previous,
                    transition,
                    assessment.measurement_status,
                    assessment.threshold_classification,
                    assessment.threshold_value,
                    assessment.observed_value,
                    assessment.window,
                    snapshot.window_id,
                    snapshot.evidence_label,
                    snapshot.source_report_sha256,
                    Jsonb(snapshot.correlation.model_dump(mode="json")),
                    payload_hash,
                    idempotency_key,
                    principal.actor_id,
                    evaluated_at,
                ),
            ).fetchone()
        return _row_to_evaluation(row, idempotent_replay=False)

    def events(self, principal: Principal, fingerprint: str) -> list[AlertEvaluation]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM alert_evaluation_event
                WHERE tenant_id = %s AND alert_fingerprint = %s
                ORDER BY alert_evaluation_id
                """,
                (principal.tenant_id, fingerprint),
            ).fetchall()
        if not rows:
            raise NotFoundError()
        return [_row_to_evaluation(row, idempotent_replay=False) for row in rows]

    def current(self, principal: Principal, fingerprint: str) -> AlertEvaluation:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM alert_evaluation_event
                WHERE tenant_id = %s AND alert_fingerprint = %s AND state IS NOT NULL
                ORDER BY alert_evaluation_id DESC LIMIT 1
                """,
                (principal.tenant_id, fingerprint),
            ).fetchone()
        if row is None:
            raise NotFoundError()
        return _row_to_evaluation(row, idempotent_replay=False)
