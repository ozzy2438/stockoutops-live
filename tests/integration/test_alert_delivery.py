from __future__ import annotations

import json
import socket
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from inspect import signature
from pathlib import Path

import psycopg
import pytest

from stockoutops.alerting.contracts import AlertCorrelation, AlertEvaluation, AlertMetricSnapshot
from stockoutops.alerting.delivery import AlertDeliveryRepository
from stockoutops.alerting.delivery_settings import AlertDeliverySettings
from stockoutops.alerting.repository import AlertRepository
from stockoutops.alerting.service import AlertService
from stockoutops.alerting.sink import DisabledAlertSink, build_alert_sink
from stockoutops.database import Database, run_migrations
from stockoutops.errors import ConflictError, NotFoundError
from stockoutops.identity import Principal
from tests.integration.conftest import ADMIN_DSN, APP_DSN
from tests.webhook_receiver import RecordingWebhookServer

SECRET_TOKEN = "super-secret-webhook-token-value"


def _principal(tenant_id: str = "t_alpha") -> Principal:
    return Principal("alert-test-operator", tenant_id, frozenset({"operator"}))


def _snapshot(**overrides: object) -> AlertMetricSnapshot:
    payload = {
        "correlation": AlertCorrelation(tenant_id="t_alpha"),
        "window_id": "alert-window-001",
        "source_report_sha256": "a" * 64,
        "source_report_label": ("M2 SHADOW FOUNDATION — SIMULATED ENGINEERING REHEARSAL"),
        "evidence_label": "SIMULATED",
        "execute": False,
        "case_count": 10,
        "escalation_disagreement_count": 1,
        "missing_required_evidence_count": 0,
        "unsupported_claim_count": 0,
        "external_action_count": 0,
        "shadow_processing_failure_count": None,
        "deterministic_provider_latency_ms": 4.0,
    }
    payload.update(overrides)
    return AlertMetricSnapshot(**payload)


def _firing_snapshot(**overrides: object) -> AlertMetricSnapshot:
    payload = {"escalation_disagreement_count": 3}
    payload.update(overrides)
    return _snapshot(**payload)


def _count_alert_events() -> int:
    with psycopg.connect(ADMIN_DSN) as connection:
        return connection.execute("SELECT count(*) FROM alert_evaluation_event").fetchone()[0]


def _count_delivery_attempts() -> int:
    with psycopg.connect(ADMIN_DSN) as connection:
        return connection.execute("SELECT count(*) FROM alert_delivery_attempt").fetchone()[0]


def _delivery_rows() -> list[dict[str, object]]:
    with psycopg.connect(ADMIN_DSN, row_factory=psycopg.rows.dict_row) as connection:
        return list(
            connection.execute("SELECT * FROM alert_delivery_attempt ORDER BY delivery_attempt_id")
        )


@pytest.fixture
def alert_repository(clean_database) -> AlertRepository:
    return AlertRepository(Database(APP_DSN))


def _service(alert_repository: AlertRepository, sink) -> AlertService:
    return AlertService(
        alert_repository,
        clock=lambda: datetime(2026, 8, 14, 12, 0, tzinfo=UTC),
        sink=sink,
    )


def _enabled_settings(url: str, **overrides: object) -> AlertDeliverySettings:
    payload = {
        "enabled": True,
        "webhook_url": url,
        "timeout_seconds": 1.0,
        "max_attempts": 2,
        "token": None,
    }
    payload.update(overrides)
    return AlertDeliverySettings(**payload)


@pytest.mark.integration
def test_alert_delivery_migration_is_recorded_and_repeat_is_noop(postgres_schema) -> None:
    with psycopg.connect(ADMIN_DSN) as connection:
        versions = {
            row[0] for row in connection.execute("SELECT version FROM schema_migration").fetchall()
        }
    assert "0006_m2_alert_policy_foundation.sql" in versions
    assert "0007_m2_alert_webhook_delivery.sql" in versions
    assert (
        run_migrations(
            ADMIN_DSN,
            migrations_dir=Path("migrations"),
            app_role_password="app-local-only",
        )
        == []
    )


@pytest.mark.integration
def test_delivery_disabled_makes_zero_outbound_requests(
    alert_repository: AlertRepository,
) -> None:
    with RecordingWebhookServer() as receiver:
        settings = AlertDeliverySettings(enabled=False, webhook_url=receiver.url)
        service = _service(alert_repository, build_alert_sink(Database(APP_DSN), settings))
        results = service.evaluate(
            _principal(), _firing_snapshot(), idempotency_prefix="disabled-delivery"
        )
        assert isinstance(service.sink, DisabledAlertSink)
        assert receiver.requests == []
        assert _count_delivery_attempts() == 0
        assert _count_alert_events() == 5
        assert all(item.external_alert_delivery_count == 0 for item in results)
        assert all(item.live_slo_evidence_eligible is False for item in results)


@pytest.mark.integration
def test_enabled_firing_alert_makes_one_bounded_delivery(
    alert_repository: AlertRepository,
) -> None:
    with RecordingWebhookServer() as receiver:
        service = _service(
            alert_repository,
            build_alert_sink(Database(APP_DSN), _enabled_settings(receiver.url)),
        )
        results = service.evaluate(
            _principal(), _firing_snapshot(), idempotency_prefix="enabled-firing"
        )
        firing = next(item for item in results if item.transition == "FIRED")
        assert firing.policy_id == "shadow-escalation-disagreement-rate"
        assert firing.evidence_label == "SIMULATED"
        assert len(receiver.requests) == 1
        body = receiver.requests[0]["body"]
        assert body["transition"] == "FIRED"
        assert body["evaluation_id"] == firing.evaluation_id
        assert body["live_slo_evidence_eligible"] is False
        assert body["evidence_label"] == "SIMULATED"
    rows = _delivery_rows()
    assert len(rows) == 1
    assert rows[0]["status"] == "DELIVERED"
    assert rows[0]["attempt_count"] == 1
    assert rows[0]["destination_host"] == "127.0.0.1"
    assert firing.external_alert_delivery_count == 0


@pytest.mark.integration
def test_replay_does_not_duplicate_delivery(alert_repository: AlertRepository) -> None:
    with RecordingWebhookServer() as receiver:
        service = _service(
            alert_repository,
            build_alert_sink(Database(APP_DSN), _enabled_settings(receiver.url)),
        )
        first = service.evaluate(
            _principal(), _firing_snapshot(), idempotency_prefix="replay-delivery"
        )
        replay = service.evaluate(
            _principal(), _firing_snapshot(), idempotency_prefix="replay-delivery"
        )
        assert all(item.idempotent_replay for item in replay)
        assert [item.evaluation_id for item in replay] == [item.evaluation_id for item in first]
        assert len(receiver.requests) == 1
    assert _count_delivery_attempts() == 1
    assert _count_alert_events() == 5


@pytest.mark.integration
def test_concurrent_delivery_converges_without_alert_storm(
    alert_repository: AlertRepository,
) -> None:
    with RecordingWebhookServer() as receiver:
        service = _service(
            alert_repository,
            build_alert_sink(Database(APP_DSN), _enabled_settings(receiver.url)),
        )

        def evaluate_once():
            return service.evaluate(
                _principal(),
                _firing_snapshot(),
                idempotency_prefix="concurrent-delivery",
            )

        with ThreadPoolExecutor(max_workers=6) as pool:
            results = [future.result() for future in [pool.submit(evaluate_once) for _ in range(6)]]
        assert len(receiver.requests) == 1
        assert _count_delivery_attempts() == 1
        assert _count_alert_events() == 5
        assert len({item.evaluation_id for result in results for item in result}) == 5


@pytest.mark.integration
def test_firing_then_resolved_sends_second_lifecycle_notification(
    alert_repository: AlertRepository,
) -> None:
    with RecordingWebhookServer() as receiver:
        service = _service(
            alert_repository,
            build_alert_sink(Database(APP_DSN), _enabled_settings(receiver.url)),
        )
        firing = service.evaluate(
            _principal(), _firing_snapshot(), idempotency_prefix="lifecycle-firing"
        )
        resolved = service.evaluate(
            _principal(),
            _snapshot(
                window_id="alert-window-002",
                source_report_sha256="b" * 64,
                escalation_disagreement_count=1,
            ),
            idempotency_prefix="lifecycle-resolved",
        )
        transitions = [item["body"]["transition"] for item in receiver.requests]
        assert transitions == ["FIRED", "RESOLVED"]
        assert next(item.transition for item in firing if item.transition == "FIRED") == "FIRED"
        assert next(item.transition for item in resolved if item.transition == "RESOLVED") == (
            "RESOLVED"
        )
    rows = _delivery_rows()
    assert [row["status"] for row in rows] == ["DELIVERED", "DELIVERED"]
    assert {row["transition"] for row in rows} == {"FIRED", "RESOLVED"}


@pytest.mark.integration
def test_timeout_preserves_original_alert_evidence(alert_repository: AlertRepository) -> None:
    with RecordingWebhookServer(hang_seconds=0.6) as receiver:
        service = _service(
            alert_repository,
            build_alert_sink(
                Database(APP_DSN),
                _enabled_settings(receiver.url, timeout_seconds=0.2, max_attempts=2),
            ),
        )
        results = service.evaluate(
            _principal(), _firing_snapshot(), idempotency_prefix="timeout-delivery"
        )
        assert _count_alert_events() == 5
        assert any(item.transition == "FIRED" for item in results)
    rows = _delivery_rows()
    assert len(rows) == 1
    assert rows[0]["status"] == "FAILED"
    assert rows[0]["error_class"] == "timeout"
    assert rows[0]["attempt_count"] == 2
    firing = next(item for item in results if item.transition == "FIRED")
    assert firing.external_alert_delivery_count == 0
    assert firing.live_slo_evidence_eligible is False


@pytest.mark.integration
def test_unreachable_receiver_preserves_alert_evidence(
    alert_repository: AlertRepository,
) -> None:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    service = _service(
        alert_repository,
        build_alert_sink(
            Database(APP_DSN),
            _enabled_settings(f"http://127.0.0.1:{port}/alerts", timeout_seconds=0.2),
        ),
    )
    results = service.evaluate(
        _principal(), _firing_snapshot(), idempotency_prefix="unreachable-delivery"
    )
    assert _count_alert_events() == 5
    assert any(item.state == "FIRING" for item in results)
    rows = _delivery_rows()
    assert len(rows) == 1
    assert rows[0]["status"] == "FAILED"
    assert rows[0]["error_class"] == "connection_error"


@pytest.mark.integration
def test_secrets_are_absent_from_delivery_rows_and_payloads(
    alert_repository: AlertRepository,
) -> None:
    with RecordingWebhookServer() as receiver:
        service = _service(
            alert_repository,
            build_alert_sink(
                Database(APP_DSN),
                _enabled_settings(receiver.url, token=SECRET_TOKEN),
            ),
        )
        service.evaluate(_principal(), _firing_snapshot(), idempotency_prefix="secret-delivery")
        request = receiver.requests[0]
        assert request["authorization"] == f"Bearer {SECRET_TOKEN}"
        assert SECRET_TOKEN not in json.dumps(request["body"])
    for row in _delivery_rows():
        dumped = json.dumps(row, default=str)
        assert SECRET_TOKEN not in dumped
        assert "Authorization" not in dumped
        assert "Bearer" not in dumped


@pytest.mark.integration
def test_sev1_fail_closed_still_persists_and_may_notify(
    alert_repository: AlertRepository,
) -> None:
    with RecordingWebhookServer() as receiver:
        service = _service(
            alert_repository,
            build_alert_sink(Database(APP_DSN), _enabled_settings(receiver.url)),
        )
        with pytest.raises(ConflictError) as violation:
            service.evaluate(
                _principal(),
                _snapshot(external_action_count=1),
                idempotency_prefix="sev1-delivery",
            )
        assert violation.value.code == "SHADOW_EXTERNAL_ACTION_DETECTED"
        assert len(receiver.requests) == 1
        assert receiver.requests[0]["body"]["policy_id"] == "shadow-external-action-safety"
        assert receiver.requests[0]["body"]["transition"] == "FIRED"
    assert _count_alert_events() == 1
    assert _delivery_rows()[0]["status"] == "DELIVERED"


@pytest.mark.integration
def test_delivery_attempts_are_tenant_scoped(alert_repository: AlertRepository) -> None:
    with RecordingWebhookServer() as receiver:
        service = _service(
            alert_repository,
            build_alert_sink(Database(APP_DSN), _enabled_settings(receiver.url)),
        )
        results = service.evaluate(
            _principal(), _firing_snapshot(), idempotency_prefix="tenant-delivery"
        )
        firing = next(item for item in results if item.transition == "FIRED")
        delivery = AlertDeliveryRepository(Database(APP_DSN))
        owned = delivery.attempts(_principal(), firing.evaluation_id)
        assert len(owned) == 1
        assert delivery.attempts(_principal("t_beta"), firing.evaluation_id) == []
        with pytest.raises(NotFoundError):
            delivery.claim(
                _principal("t_beta"),
                firing,
                destination_host="127.0.0.1",
                payload_hash="d" * 64,
                claimed_at=datetime(2026, 8, 14, 12, 0, tzinfo=UTC),
            )


def _claimed_firing(
    alert_repository: AlertRepository, prefix: str
) -> tuple[AlertEvaluation, AlertDeliveryRepository]:
    firing = _firing_without_delivery(alert_repository, prefix)
    delivery = AlertDeliveryRepository(Database(APP_DSN))
    claimed = delivery.claim(
        _principal(),
        firing,
        destination_host="127.0.0.1",
        payload_hash="e" * 64,
        claimed_at=datetime(2026, 8, 14, 12, 0, tzinfo=UTC),
    )
    assert claimed is True
    rows = delivery.attempts(_principal(), firing.evaluation_id)
    assert len(rows) == 1
    assert rows[0]["status"] == "CLAIMED"
    return firing, delivery


def _firing_without_delivery(alert_repository: AlertRepository, prefix: str) -> AlertEvaluation:
    service = _service(alert_repository, DisabledAlertSink())
    results = service.evaluate(_principal(), _firing_snapshot(), idempotency_prefix=prefix)
    return next(item for item in results if item.transition == "FIRED")


def _insert_delivery_attempt_as_app(
    firing: AlertEvaluation,
    *,
    status: str,
    attempt_count: int,
    http_status: int | None,
    error_class: str | None,
    completed_at: datetime | None,
) -> None:
    with psycopg.connect(APP_DSN) as connection:
        connection.execute(
            """
            INSERT INTO alert_delivery_attempt (
                tenant_id, evaluation_id, alert_fingerprint, transition,
                destination_host, status, attempt_count, http_status,
                error_class, payload_hash, claimed_at, completed_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                "t_alpha",
                firing.evaluation_id,
                firing.alert_fingerprint,
                firing.transition,
                "127.0.0.1",
                status,
                attempt_count,
                http_status,
                error_class,
                "f" * 64,
                datetime(2026, 8, 14, 12, 0, tzinfo=UTC),
                completed_at,
            ),
        )


@pytest.mark.integration
@pytest.mark.parametrize(
    ("status", "http_status", "error_class"),
    [
        ("DELIVERED", 200, None),
        ("FAILED", None, "timeout"),
    ],
)
def test_app_role_cannot_insert_terminal_delivery_attempt(
    alert_repository: AlertRepository,
    status: str,
    http_status: int | None,
    error_class: str | None,
) -> None:
    firing = _firing_without_delivery(alert_repository, f"insert-terminal-{status}")
    with pytest.raises(psycopg.Error):
        _insert_delivery_attempt_as_app(
            firing,
            status=status,
            attempt_count=1,
            http_status=http_status,
            error_class=error_class,
            completed_at=datetime(2026, 8, 14, 12, 1, tzinfo=UTC),
        )


@pytest.mark.integration
@pytest.mark.parametrize(
    ("attempt_count", "http_status", "error_class", "completed_at"),
    [
        (1, None, None, None),
        (0, 200, None, None),
        (0, None, "timeout", None),
        (0, None, None, datetime(2026, 8, 14, 12, 1, tzinfo=UTC)),
    ],
)
def test_app_role_cannot_insert_malformed_claimed_delivery_attempt(
    alert_repository: AlertRepository,
    attempt_count: int,
    http_status: int | None,
    error_class: str | None,
    completed_at: datetime | None,
) -> None:
    firing = _firing_without_delivery(
        alert_repository,
        f"insert-malformed-claimed-{attempt_count}-{http_status}-{error_class}-{completed_at}",
    )
    with pytest.raises(psycopg.Error):
        _insert_delivery_attempt_as_app(
            firing,
            status="CLAIMED",
            attempt_count=attempt_count,
            http_status=http_status,
            error_class=error_class,
            completed_at=completed_at,
        )


@pytest.mark.integration
def test_app_role_can_insert_valid_claimed_delivery_attempt(
    alert_repository: AlertRepository,
) -> None:
    firing = _firing_without_delivery(alert_repository, "insert-valid-claimed")
    _insert_delivery_attempt_as_app(
        firing,
        status="CLAIMED",
        attempt_count=0,
        http_status=None,
        error_class=None,
        completed_at=None,
    )
    row = _delivery_rows()[0]
    assert row["status"] == "CLAIMED"
    assert row["attempt_count"] == 0
    assert row["http_status"] is None
    assert row["error_class"] is None
    assert row["completed_at"] is None


@pytest.mark.integration
def test_claimed_to_delivered_complete_is_accepted(
    alert_repository: AlertRepository,
) -> None:
    firing, delivery = _claimed_firing(alert_repository, "guard-delivered")
    delivery.complete(
        _principal(),
        firing,
        status="DELIVERED",
        attempt_count=1,
        http_status=200,
        error_class=None,
        completed_at=datetime(2026, 8, 14, 12, 1, tzinfo=UTC),
    )
    row = delivery.attempts(_principal(), firing.evaluation_id)[0]
    assert row["status"] == "DELIVERED"
    assert row["attempt_count"] == 1
    assert row["http_status"] == 200
    assert row["tenant_id"] == "t_alpha"
    assert row["payload_hash"] == "e" * 64


@pytest.mark.integration
def test_claimed_to_failed_complete_is_accepted(
    alert_repository: AlertRepository,
) -> None:
    firing, delivery = _claimed_firing(alert_repository, "guard-failed")
    delivery.complete(
        _principal(),
        firing,
        status="FAILED",
        attempt_count=2,
        http_status=None,
        error_class="timeout",
        completed_at=datetime(2026, 8, 14, 12, 1, tzinfo=UTC),
    )
    row = delivery.attempts(_principal(), firing.evaluation_id)[0]
    assert row["status"] == "FAILED"
    assert row["attempt_count"] == 2
    assert row["error_class"] == "timeout"
    assert row["alert_fingerprint"] == firing.alert_fingerprint


@pytest.mark.integration
@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("tenant_id", "'t_evil'"),
        ("evaluation_id", "999999"),
        ("alert_fingerprint", "'" + "b" * 64 + "'"),
        ("transition", "'RESOLVED'"),
        ("destination_host", "'evil.example'"),
        ("payload_hash", "'" + "c" * 64 + "'"),
        ("claimed_at", "'2020-01-01T00:00:00+00'"),
    ],
)
def test_delivery_identity_fields_are_immutable(
    alert_repository: AlertRepository, column: str, value: str
) -> None:
    _claimed_firing(alert_repository, f"guard-immutable-{column}")
    sql = (
        "UPDATE alert_delivery_attempt SET status = 'DELIVERED', "
        f"attempt_count = 1, completed_at = now(), {column} = {value}"
    )
    for dsn in (ADMIN_DSN, APP_DSN):
        with psycopg.connect(dsn) as connection, pytest.raises(psycopg.Error):
            connection.execute(sql)


@pytest.mark.integration
def test_delivered_cannot_become_failed(alert_repository: AlertRepository) -> None:
    firing, delivery = _claimed_firing(alert_repository, "guard-delivered-to-failed")
    delivery.complete(
        _principal(),
        firing,
        status="DELIVERED",
        attempt_count=1,
        http_status=200,
        error_class=None,
        completed_at=datetime(2026, 8, 14, 12, 1, tzinfo=UTC),
    )
    for dsn in (ADMIN_DSN, APP_DSN):
        with psycopg.connect(dsn) as connection, pytest.raises(psycopg.Error):
            connection.execute("UPDATE alert_delivery_attempt SET status = 'FAILED'")


@pytest.mark.integration
def test_failed_cannot_become_delivered(alert_repository: AlertRepository) -> None:
    firing, delivery = _claimed_firing(alert_repository, "guard-failed-to-delivered")
    delivery.complete(
        _principal(),
        firing,
        status="FAILED",
        attempt_count=2,
        http_status=None,
        error_class="connection_error",
        completed_at=datetime(2026, 8, 14, 12, 1, tzinfo=UTC),
    )
    for dsn in (ADMIN_DSN, APP_DSN):
        with psycopg.connect(dsn) as connection, pytest.raises(psycopg.Error):
            connection.execute("UPDATE alert_delivery_attempt SET status = 'DELIVERED'")


@pytest.mark.integration
@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE alert_delivery_attempt SET attempt_count = 2",
        "UPDATE alert_delivery_attempt SET http_status = 500",
        "UPDATE alert_delivery_attempt SET error_class = 'rewritten'",
        "UPDATE alert_delivery_attempt SET completed_at = '2020-01-01T00:00:00+00'",
    ],
)
def test_terminal_delivery_metadata_cannot_be_rewritten(
    alert_repository: AlertRepository, sql: str
) -> None:
    firing, delivery = _claimed_firing(alert_repository, f"guard-terminal-meta-{sql[:24]}")
    delivery.complete(
        _principal(),
        firing,
        status="DELIVERED",
        attempt_count=1,
        http_status=200,
        error_class=None,
        completed_at=datetime(2026, 8, 14, 12, 1, tzinfo=UTC),
    )
    for dsn in (ADMIN_DSN, APP_DSN):
        with psycopg.connect(dsn) as connection, pytest.raises(psycopg.Error):
            connection.execute(sql)


@pytest.mark.integration
def test_delivery_delete_is_rejected(alert_repository: AlertRepository) -> None:
    with RecordingWebhookServer() as receiver:
        service = _service(
            alert_repository,
            build_alert_sink(Database(APP_DSN), _enabled_settings(receiver.url)),
        )
        service.evaluate(_principal(), _firing_snapshot(), idempotency_prefix="delete-delivery")
    for dsn in (ADMIN_DSN, APP_DSN):
        with psycopg.connect(dsn) as connection, pytest.raises(psycopg.Error):
            connection.execute("DELETE FROM alert_delivery_attempt")


@pytest.mark.integration
def test_delivery_repository_tenant_choke_point_is_explicit() -> None:
    for method in (
        AlertDeliveryRepository.claim,
        AlertDeliveryRepository.complete,
        AlertDeliveryRepository.attempts,
    ):
        assert next(iter(signature(method).parameters)) == "self"
        assert list(signature(method).parameters)[1] == "principal"
