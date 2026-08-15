"""Adversarial durable-outbox and recovery proofs against real PostgreSQL.

Every test in this module exercises the Phase 1 crash-safety properties that
ADR-0008 explicitly could not provide. Nothing here contacts a public endpoint:
the only receiver is a loopback HTTP server owned by the test process.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
import pytest

from stockoutops.alerting.contracts import AlertMetricSnapshot
from stockoutops.alerting.delivery_settings import AlertDeliverySettings
from stockoutops.alerting.enqueue import WebhookOutboxEnqueuer
from stockoutops.alerting.outbox import (
    AlertOutboxRepository,
    LeasedDelivery,
    backoff_delay_seconds,
    delivery_idempotency_key,
)
from stockoutops.alerting.repository import AlertRepository
from stockoutops.alerting.service import AlertService
from stockoutops.alerting.webhook import WebhookTransport
from stockoutops.alerting.worker import AlertOutboxWorker, build_worker
from stockoutops.database import Database
from stockoutops.errors import ConflictError, NotFoundError
from stockoutops.identity import Principal
from tests.integration.conftest import ADMIN_DSN, APP_DSN
from tests.webhook_receiver import RecordingWebhookServer

pytestmark = pytest.mark.integration

BASE_AT = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
SOURCE_SHA = "b" * 64


def _principal(tenant_id: str = "t_alpha") -> Principal:
    return Principal(f"operator-{tenant_id}", tenant_id, frozenset({"operator"}))


def _snapshot(**overrides: object) -> AlertMetricSnapshot:
    payload: dict[str, object] = {
        "correlation": {"tenant_id": "t_alpha", "run_id": "run-outbox", "case_id": "case-outbox"},
        "window_id": "window-outbox-1",
        "source_report_sha256": SOURCE_SHA,
        "source_report_label": "M2 SHADOW FOUNDATION — SIMULATED ENGINEERING REHEARSAL",
        "evidence_label": "SIMULATED",
        "execute": False,
        "case_count": 10,
        "escalation_disagreement_count": 0,
        "missing_required_evidence_count": 0,
        "unsupported_claim_count": 0,
        "external_action_count": 0,
        "shadow_processing_failure_count": 0,
    }
    payload.update(overrides)
    return AlertMetricSnapshot.model_validate(payload)


def _firing_snapshot(**overrides: object) -> AlertMetricSnapshot:
    return _snapshot(missing_required_evidence_count=99, **overrides)


def _settings(url: str, **overrides: object) -> AlertDeliverySettings:
    values: dict[str, Any] = {
        "enabled": True,
        "webhook_url": url,
        "timeout_seconds": 1.0,
        "max_attempts": 5,
        "token": None,
    }
    values.update(overrides)
    return AlertDeliverySettings(**values)


@pytest.fixture
def outbox(clean_database: None) -> AlertOutboxRepository:
    return AlertOutboxRepository(Database(APP_DSN))


def _service(url: str, *, max_attempts: int = 5) -> AlertService:
    enqueuer = WebhookOutboxEnqueuer(_settings(url), max_attempts=max_attempts)
    return AlertService(
        AlertRepository(Database(APP_DSN), delivery_enqueuer=enqueuer),
        clock=lambda: BASE_AT,
    )


def _evaluate(
    url: str,
    *,
    prefix: str,
    snapshot: AlertMetricSnapshot | None = None,
    principal: Principal | None = None,
    max_attempts: int = 5,
) -> list[Any]:
    service = _service(url, max_attempts=max_attempts)
    return service.evaluate(
        principal or _principal(),
        snapshot or _firing_snapshot(),
        idempotency_prefix=prefix,
    )


def _all_outbox_rows() -> list[dict[str, Any]]:
    with psycopg.connect(ADMIN_DSN, row_factory=psycopg.rows.dict_row) as connection:
        return [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM alert_outbox ORDER BY outbox_id"
            ).fetchall()
        ]


def _first_outbox(outbox: AlertOutboxRepository, principal: Principal) -> dict[str, Any]:
    rows = _all_outbox_rows()
    tenant_rows = [row for row in rows if row["tenant_id"] == principal.tenant_id]
    assert tenant_rows, "expected an enqueued delivery intent"
    return tenant_rows[0]


# --------------------------------------------------------------------------
# transactional enqueue and lifecycle
# --------------------------------------------------------------------------


def test_migration_is_recorded_and_repeat_is_a_noop(postgres_schema: None) -> None:
    with psycopg.connect(ADMIN_DSN, row_factory=psycopg.rows.dict_row) as connection:
        row = connection.execute(
            "SELECT version FROM schema_migration WHERE version = %s",
            ("0008_m2_alert_outbox.sql",),
        ).fetchone()
    assert row is not None


def test_firing_evaluation_enqueues_pending_intent_without_network(
    outbox: AlertOutboxRepository,
) -> None:
    # Port 9 is the discard port: any HTTP attempt here would fail loudly.
    evaluations = _evaluate("http://127.0.0.1:9/alerts", prefix="enqueue-only")
    fired = [item for item in evaluations if item.transition == "FIRED"]
    assert fired, "expected at least one FIRED lifecycle transition"

    row = _first_outbox(outbox, _principal())
    assert row["state"] == "PENDING"
    assert row["attempt_count"] == 0
    assert row["lease_owner"] is None
    assert row["completed_at"] is None
    assert row["idempotency_key"] == delivery_idempotency_key(
        "t_alpha", row["evaluation_id"], "FIRED"
    )


def test_non_lifecycle_transitions_are_not_enqueued(outbox: AlertOutboxRepository) -> None:
    _evaluate("http://127.0.0.1:9/alerts", prefix="ok-window", snapshot=_snapshot())
    assert _all_outbox_rows() == []


def test_firing_then_resolved_preserves_lifecycle_ordering(
    outbox: AlertOutboxRepository,
) -> None:
    with RecordingWebhookServer() as receiver:
        _evaluate(receiver.url, prefix="lifecycle-fired")
        _evaluate(
            receiver.url,
            prefix="lifecycle-resolved",
            snapshot=_snapshot(window_id="window-outbox-2"),
        )
        rows = _all_outbox_rows()
        assert [row["transition"] for row in rows] == ["FIRED", "RESOLVED"]

        worker = build_worker(
            outbox, _settings(receiver.url), worker_id="w-lifecycle", clock=lambda: BASE_AT
        )
        result = worker.run_once()

    assert result.delivered == 2
    assert [request["body"]["transition"] for request in receiver.requests] == [
        "FIRED",
        "RESOLVED",
    ]
    assert [row["state"] for row in _all_outbox_rows()] == ["DELIVERED", "DELIVERED"]


def test_replay_does_not_enqueue_a_second_intent(outbox: AlertOutboxRepository) -> None:
    _evaluate("http://127.0.0.1:9/alerts", prefix="replay-key")
    _evaluate("http://127.0.0.1:9/alerts", prefix="replay-key")
    assert len(_all_outbox_rows()) == 1


def test_no_network_call_occurs_inside_the_evaluation_transaction(
    outbox: AlertOutboxRepository,
) -> None:
    """A receiver that never answers must not block or fail evaluation."""

    with RecordingWebhookServer(hang_seconds=30) as receiver:
        evaluations = _evaluate(receiver.url, prefix="no-http-in-txn")
    assert any(item.transition == "FIRED" for item in evaluations)
    assert receiver.requests == []
    assert _first_outbox(outbox, _principal())["state"] == "PENDING"


# --------------------------------------------------------------------------
# crash safety
# --------------------------------------------------------------------------


def test_crash_before_send_leaves_recoverable_intent(outbox: AlertOutboxRepository) -> None:
    """Lease the row, then abandon it as a crashed worker would."""

    with RecordingWebhookServer() as receiver:
        _evaluate(receiver.url, prefix="crash-before-send")
        leased = outbox.lease(worker_id="w-crash", now=BASE_AT, lease_seconds=30)
        assert len(leased) == 1
        # Simulated crash: the process dies here, before any HTTP request.
        assert receiver.requests == []

        recovered = outbox.lease(
            worker_id="w-recovery", now=BASE_AT + timedelta(seconds=31), lease_seconds=30
        )
        assert len(recovered) == 1
        assert recovered[0].outbox_id == leased[0].outbox_id
        assert recovered[0].attempt_number == 2

        worker = AlertOutboxWorker(
            outbox,
            WebhookTransport(_settings(receiver.url)),
            worker_id="w-recovery",
            clock=lambda: BASE_AT + timedelta(seconds=31),
        )
        worker._process(recovered[0])

    assert len(receiver.requests) == 1
    assert _first_outbox(outbox, _principal())["state"] == "DELIVERED"


def test_crash_after_receiver_success_redelivers_under_a_stable_idempotency_key(
    outbox: AlertOutboxRepository,
) -> None:
    """Receiver accepted, local acknowledgement never happened.

    The outbox must redeliver (at-least-once). Suppression is the receiver's
    duty, so both requests must carry the identical Idempotency-Key.
    """

    with RecordingWebhookServer() as receiver:
        _evaluate(receiver.url, prefix="crash-after-success")
        leased = outbox.lease(worker_id="w-a", now=BASE_AT, lease_seconds=30)[0]
        transport = WebhookTransport(_settings(receiver.url))
        status = transport.post(leased.payload, idempotency_key=leased.idempotency_key)
        assert status == 200
        # Simulated crash before record_delivered() commits.

        retaken = outbox.lease(
            worker_id="w-b", now=BASE_AT + timedelta(seconds=31), lease_seconds=30
        )[0]
        worker = AlertOutboxWorker(
            outbox,
            transport,
            worker_id="w-b",
            clock=lambda: BASE_AT + timedelta(seconds=31),
        )
        worker._process(retaken)

    assert len(receiver.requests) == 2
    keys = {request["idempotency_key"] for request in receiver.requests}
    assert len(keys) == 1, "redelivery must reuse the same receiver idempotency key"
    assert _first_outbox(outbox, _principal())["state"] == "DELIVERED"


def test_receiver_side_idempotency_contract_suppresses_the_duplicate_effect(
    outbox: AlertOutboxRepository,
) -> None:
    """Model a conforming receiver: dedupe on Idempotency-Key."""

    applied_effects: list[str] = []
    seen: set[str] = set()

    with RecordingWebhookServer() as receiver:
        _evaluate(receiver.url, prefix="receiver-idempotency")
        transport = WebhookTransport(_settings(receiver.url))
        leased = outbox.lease(worker_id="w-a", now=BASE_AT, lease_seconds=30)[0]

        for _ in range(3):
            transport.post(leased.payload, idempotency_key=leased.idempotency_key)
            request = receiver.requests[-1]
            key = request["idempotency_key"]
            if key not in seen:
                seen.add(key)
                applied_effects.append(key)

    assert len(receiver.requests) == 3
    assert len(applied_effects) == 1, "a conforming receiver applies the effect exactly once"


def test_ambiguous_timeout_is_recorded_as_ambiguous_and_retried(
    outbox: AlertOutboxRepository,
) -> None:
    with RecordingWebhookServer(hang_seconds=3) as receiver:
        _evaluate(receiver.url, prefix="ambiguous-timeout")
        worker = build_worker(
            outbox,
            _settings(receiver.url, timeout_seconds=0.3),
            worker_id="w-timeout",
            clock=lambda: BASE_AT,
        )
        result = worker.run_once()

    assert result.retried == 1
    row = _first_outbox(outbox, _principal())
    assert row["state"] == "PENDING"
    assert row["last_error_class"] == "timeout"
    assert row["next_attempt_at"] > BASE_AT

    events = outbox.attempt_events(_principal(), row["outbox_id"])
    assert [event["outcome"] for event in events] == ["AMBIGUOUS"]
    assert events[0]["http_status"] is None


def test_service_restart_with_durable_state_still_delivers(
    outbox: AlertOutboxRepository,
) -> None:
    """Enqueue with one process object graph, deliver with a brand new one."""

    with RecordingWebhookServer() as receiver:
        _evaluate(receiver.url, prefix="restart-durable")

        # Fresh repository/worker objects stand in for a restarted process.
        restarted = AlertOutboxRepository(Database(APP_DSN))
        worker = build_worker(
            restarted, _settings(receiver.url), worker_id="w-restarted", clock=lambda: BASE_AT
        )
        result = worker.run_once()

    assert result.delivered == 1
    assert len(receiver.requests) == 1


# --------------------------------------------------------------------------
# leasing and concurrency
# --------------------------------------------------------------------------


def test_stale_lease_is_not_reclaimed_before_expiry(outbox: AlertOutboxRepository) -> None:
    _evaluate("http://127.0.0.1:9/alerts", prefix="lease-not-expired")
    first = outbox.lease(worker_id="w-a", now=BASE_AT, lease_seconds=60)
    assert len(first) == 1
    second = outbox.lease(worker_id="w-b", now=BASE_AT + timedelta(seconds=30), lease_seconds=60)
    assert second == []


def test_stale_lease_recovery_after_expiry(outbox: AlertOutboxRepository) -> None:
    _evaluate("http://127.0.0.1:9/alerts", prefix="lease-expired")
    outbox.lease(worker_id="w-a", now=BASE_AT, lease_seconds=30)
    recovered = outbox.lease(worker_id="w-b", now=BASE_AT + timedelta(seconds=31), lease_seconds=30)
    assert len(recovered) == 1
    assert recovered[0].lease_owner == "w-b"
    assert recovered[0].attempt_number == 2


def test_worker_that_lost_its_lease_cannot_overwrite_the_new_owner(
    outbox: AlertOutboxRepository,
) -> None:
    with RecordingWebhookServer() as receiver:
        _evaluate(receiver.url, prefix="lease-lost")
        stale = outbox.lease(worker_id="w-stale", now=BASE_AT, lease_seconds=30)[0]
        fresh = outbox.lease(
            worker_id="w-fresh", now=BASE_AT + timedelta(seconds=31), lease_seconds=30
        )[0]
        assert fresh.lease_owner == "w-fresh"

        stale_worker = AlertOutboxWorker(
            outbox,
            WebhookTransport(_settings(receiver.url)),
            worker_id="w-stale",
            clock=lambda: BASE_AT + timedelta(seconds=32),
        )
        outcome = stale_worker._process(stale)

    assert outcome.lease_lost == 1
    row = _first_outbox(outbox, _principal())
    assert row["state"] == "IN_FLIGHT"
    assert row["lease_owner"] == "w-fresh"


def test_two_competing_workers_lease_disjoint_work(outbox: AlertOutboxRepository) -> None:
    for index in range(6):
        _evaluate(
            "http://127.0.0.1:9/alerts",
            prefix=f"competing-{index}",
            snapshot=_firing_snapshot(
                correlation={
                    "tenant_id": "t_alpha",
                    "run_id": f"run-{index}",
                    "case_id": f"case-{index}",
                },
                window_id=f"window-competing-{index}",
            ),
        )
    assert len(_all_outbox_rows()) == 6

    results: dict[str, list[int]] = {}
    barrier = threading.Barrier(2)

    def claim(worker_id: str) -> None:
        repository = AlertOutboxRepository(Database(APP_DSN))
        barrier.wait(timeout=10)
        leased = repository.lease(worker_id=worker_id, now=BASE_AT, batch_size=6)
        results[worker_id] = [item.outbox_id for item in leased]

    threads = [threading.Thread(target=claim, args=(f"w-{name}",)) for name in ("a", "b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    claimed_a, claimed_b = results["w-a"], results["w-b"]
    assert set(claimed_a).isdisjoint(claimed_b), "two workers must never claim the same row"
    assert sorted(claimed_a + claimed_b) == sorted(row["outbox_id"] for row in _all_outbox_rows())


def test_concurrent_workers_produce_exactly_one_delivery_per_intent(
    outbox: AlertOutboxRepository,
) -> None:
    with RecordingWebhookServer() as receiver:
        for index in range(4):
            _evaluate(
                receiver.url,
                prefix=f"converge-{index}",
                snapshot=_firing_snapshot(
                    correlation={
                        "tenant_id": "t_alpha",
                        "run_id": f"conv-{index}",
                        "case_id": f"conv-{index}",
                    },
                    window_id=f"window-converge-{index}",
                ),
            )

        barrier = threading.Barrier(3)

        def drain(worker_id: str) -> None:
            repository = AlertOutboxRepository(Database(APP_DSN))
            worker = build_worker(
                repository, _settings(receiver.url), worker_id=worker_id, clock=lambda: BASE_AT
            )
            barrier.wait(timeout=10)
            worker.run_once(batch_size=4)

        threads = [threading.Thread(target=drain, args=(f"w-{n}",)) for n in ("a", "b", "c")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

    assert len(receiver.requests) == 4, "each intent must be sent exactly once"
    assert {row["state"] for row in _all_outbox_rows()} == {"DELIVERED"}
    keys = [request["idempotency_key"] for request in receiver.requests]
    assert len(set(keys)) == 4


# --------------------------------------------------------------------------
# retry, dead letter, re-drive
# --------------------------------------------------------------------------


def test_retryable_5xx_retries_with_bounded_backoff(outbox: AlertOutboxRepository) -> None:
    with RecordingWebhookServer(status=503) as receiver:
        _evaluate(receiver.url, prefix="retry-5xx")
        worker = build_worker(
            outbox, _settings(receiver.url), worker_id="w-5xx", clock=lambda: BASE_AT
        )
        result = worker.run_once()

    assert result.retried == 1
    row = _first_outbox(outbox, _principal())
    assert row["state"] == "PENDING"
    assert row["last_http_status"] == 503
    assert row["next_attempt_at"] == BASE_AT + timedelta(seconds=backoff_delay_seconds(1))


def test_permanent_4xx_dead_letters_without_retry(outbox: AlertOutboxRepository) -> None:
    with RecordingWebhookServer(status=400) as receiver:
        _evaluate(receiver.url, prefix="permanent-4xx")
        worker = build_worker(
            outbox, _settings(receiver.url), worker_id="w-4xx", clock=lambda: BASE_AT
        )
        result = worker.run_once()

    assert result.dead_lettered == 1
    assert len(receiver.requests) == 1
    row = _first_outbox(outbox, _principal())
    assert row["state"] == "DEAD_LETTER"
    assert row["last_error_class"] == "http_400"
    assert row["attempt_count"] == 1


def test_retry_exhaustion_dead_letters_after_the_attempt_budget(
    outbox: AlertOutboxRepository,
) -> None:
    with RecordingWebhookServer(status=500) as receiver:
        _evaluate(receiver.url, prefix="exhaustion", max_attempts=3)
        now = BASE_AT
        for _ in range(3):
            worker = build_worker(
                outbox,
                _settings(receiver.url),
                worker_id="w-exhaust",
                clock=lambda captured=now: captured,
            )
            worker.run_once()
            now = now + timedelta(seconds=600)

    row = _first_outbox(outbox, _principal())
    assert row["state"] == "DEAD_LETTER"
    assert row["attempt_count"] == 3
    assert len(receiver.requests) == 3

    events = outbox.attempt_events(_principal(), row["outbox_id"])
    assert [event["attempt_number"] for event in events] == [1, 2, 3]
    assert {event["outcome"] for event in events} == {"RETRYABLE_FAILURE"}


def test_dead_letter_is_not_leased_again_without_an_explicit_redrive(
    outbox: AlertOutboxRepository,
) -> None:
    with RecordingWebhookServer(status=400) as receiver:
        _evaluate(receiver.url, prefix="no-auto-redrive")
        build_worker(
            outbox, _settings(receiver.url), worker_id="w-dl", clock=lambda: BASE_AT
        ).run_once()

    later = outbox.lease(worker_id="w-dl", now=BASE_AT + timedelta(hours=6))
    assert later == []


def test_redrive_returns_a_dead_letter_to_pending_and_delivers(
    outbox: AlertOutboxRepository,
) -> None:
    # Two failures exhaust the budget; the sequence then falls through to 200.
    with RecordingWebhookServer(status_sequence=[500, 500]) as receiver:
        _evaluate(receiver.url, prefix="redrive", max_attempts=2)
        now = BASE_AT
        for _ in range(2):
            build_worker(
                outbox,
                _settings(receiver.url),
                worker_id="w-r",
                clock=lambda captured=now: captured,
            ).run_once()
            now = now + timedelta(seconds=600)

        row = _first_outbox(outbox, _principal())
        assert row["state"] == "DEAD_LETTER"

        redrive_at = now + timedelta(seconds=1)
        outbox.redrive(_principal(), row["outbox_id"], now=redrive_at, additional_attempts=2)

        after = outbox.get(_principal(), row["outbox_id"])
        assert after["state"] == "PENDING"
        assert after["redrive_count"] == 1
        assert after["completed_at"] is None
        assert after["max_attempts"] == 4

        # Receiver now succeeds (sequence exhausted -> default 200).
        result = build_worker(
            outbox,
            _settings(receiver.url),
            worker_id="w-r2",
            clock=lambda: redrive_at + timedelta(seconds=1),
        ).run_once()

    assert result.delivered == 1
    assert outbox.get(_principal(), row["outbox_id"])["state"] == "DELIVERED"


def test_redrive_rejects_a_row_that_is_not_dead_lettered(
    outbox: AlertOutboxRepository,
) -> None:
    _evaluate("http://127.0.0.1:9/alerts", prefix="redrive-wrong-state")
    row = _first_outbox(outbox, _principal())
    with pytest.raises(ConflictError):
        outbox.redrive(_principal(), row["outbox_id"], now=BASE_AT)


def test_redrive_is_tenant_scoped(outbox: AlertOutboxRepository) -> None:
    with RecordingWebhookServer(status=400) as receiver:
        _evaluate(receiver.url, prefix="redrive-tenant")
        build_worker(
            outbox, _settings(receiver.url), worker_id="w-t", clock=lambda: BASE_AT
        ).run_once()
    row = _first_outbox(outbox, _principal())
    with pytest.raises(NotFoundError):
        outbox.redrive(_principal("t_beta"), row["outbox_id"], now=BASE_AT)


def test_backoff_is_bounded_and_monotonic() -> None:
    delays = [backoff_delay_seconds(n) for n in range(1, 12)]
    assert delays == sorted(delays)
    assert max(delays) <= 300.0
    with pytest.raises(ValueError):
        backoff_delay_seconds(0)


# --------------------------------------------------------------------------
# tenant isolation and worker tenant context
# --------------------------------------------------------------------------


def test_outbox_reads_are_tenant_scoped(outbox: AlertOutboxRepository) -> None:
    _evaluate("http://127.0.0.1:9/alerts", prefix="tenant-alpha")
    row = _first_outbox(outbox, _principal())

    assert outbox.for_evaluation(_principal("t_beta"), row["evaluation_id"]) is None
    assert outbox.attempt_events(_principal("t_beta"), row["outbox_id"]) == []
    assert outbox.pending_backlog(_principal("t_beta")) == []
    with pytest.raises(NotFoundError):
        outbox.get(_principal("t_beta"), row["outbox_id"])


def test_worker_carries_each_rows_own_tenant_context(outbox: AlertOutboxRepository) -> None:
    with RecordingWebhookServer() as receiver:
        _evaluate(receiver.url, prefix="tenant-ctx-alpha")
        _evaluate(
            receiver.url,
            prefix="tenant-ctx-beta",
            principal=_principal("t_beta"),
            snapshot=_firing_snapshot(
                correlation={"tenant_id": "t_beta", "run_id": "run-b", "case_id": "case-b"},
                window_id="window-beta",
            ),
        )
        result = build_worker(
            outbox, _settings(receiver.url), worker_id="w-multi", clock=lambda: BASE_AT
        ).run_once()

    assert result.delivered == 2
    rows = _all_outbox_rows()
    assert {row["tenant_id"] for row in rows} == {"t_alpha", "t_beta"}
    for row in rows:
        events = AlertOutboxRepository(Database(APP_DSN)).attempt_events(
            _principal(row["tenant_id"]), row["outbox_id"]
        )
        assert [event["tenant_id"] for event in events] == [row["tenant_id"]]
        assert row["idempotency_key"].startswith(f"{row['tenant_id']}:")

    delivered_tenants = [request["body"]["tenant_id"] for request in receiver.requests]
    assert sorted(delivered_tenants) == ["t_alpha", "t_beta"]


def test_attempt_evidence_cannot_cross_tenants(outbox: AlertOutboxRepository) -> None:
    _evaluate("http://127.0.0.1:9/alerts", prefix="evidence-tenant")
    row = _first_outbox(outbox, _principal())
    leased = outbox.lease(worker_id="w-x", now=BASE_AT)[0]
    forged = LeasedDelivery(
        outbox_id=leased.outbox_id,
        tenant_id="t_beta",
        evaluation_id=leased.evaluation_id,
        alert_fingerprint=leased.alert_fingerprint,
        transition=leased.transition,
        destination_host=leased.destination_host,
        payload=leased.payload,
        payload_hash=leased.payload_hash,
        idempotency_key=leased.idempotency_key,
        attempt_number=leased.attempt_number,
        max_attempts=leased.max_attempts,
        lease_owner="w-x",
        lease_expires_at=leased.lease_expires_at,
    )
    with pytest.raises(psycopg.Error):
        outbox.record_delivered(forged, http_status=200, started_at=BASE_AT, completed_at=BASE_AT)
    assert outbox.get(_principal(), row["outbox_id"])["state"] == "IN_FLIGHT"


# --------------------------------------------------------------------------
# database-level integrity
# --------------------------------------------------------------------------


def _app_execute(sql: str, params: tuple[Any, ...] = ()) -> None:
    with psycopg.connect(APP_DSN) as connection, connection.transaction():
        connection.execute(sql, params)


def test_app_role_cannot_delete_outbox_or_attempt_evidence(
    outbox: AlertOutboxRepository,
) -> None:
    with RecordingWebhookServer() as receiver:
        _evaluate(receiver.url, prefix="no-delete")
        build_worker(
            outbox, _settings(receiver.url), worker_id="w-nd", clock=lambda: BASE_AT
        ).run_once()

    for table in ("alert_outbox", "alert_delivery_attempt_event"):
        for dsn in (ADMIN_DSN, APP_DSN):
            with psycopg.connect(dsn) as connection, pytest.raises(psycopg.Error):
                connection.execute(f"DELETE FROM {table}")


def test_attempt_evidence_is_append_only(outbox: AlertOutboxRepository) -> None:
    with RecordingWebhookServer() as receiver:
        _evaluate(receiver.url, prefix="append-only")
        build_worker(
            outbox, _settings(receiver.url), worker_id="w-ao", clock=lambda: BASE_AT
        ).run_once()

    for dsn in (ADMIN_DSN, APP_DSN):
        with psycopg.connect(dsn) as connection, pytest.raises(psycopg.Error):
            connection.execute("UPDATE alert_delivery_attempt_event SET outcome = 'DELIVERED'")


def test_outbox_identity_and_payload_are_immutable(outbox: AlertOutboxRepository) -> None:
    _evaluate("http://127.0.0.1:9/alerts", prefix="immutable")
    for column, value in (
        ("tenant_id", "'t_beta'"),
        ("evaluation_id", "999999"),
        ("payload_hash", "'" + "f" * 64 + "'"),
        ("idempotency_key", "'forged'"),
        ("destination_host", "'evil.example'"),
    ):
        with psycopg.connect(ADMIN_DSN) as connection, pytest.raises(psycopg.Error):
            connection.execute(f"UPDATE alert_outbox SET {column} = {value}")


def test_delivered_is_a_final_state(outbox: AlertOutboxRepository) -> None:
    with RecordingWebhookServer() as receiver:
        _evaluate(receiver.url, prefix="final-delivered")
        build_worker(
            outbox, _settings(receiver.url), worker_id="w-fd", clock=lambda: BASE_AT
        ).run_once()

    for dsn in (ADMIN_DSN, APP_DSN):
        with psycopg.connect(dsn) as connection, pytest.raises(psycopg.Error):
            connection.execute("UPDATE alert_outbox SET state = 'PENDING'")


def test_forbidden_state_transitions_are_rejected(outbox: AlertOutboxRepository) -> None:
    _evaluate("http://127.0.0.1:9/alerts", prefix="bad-transition")
    # PENDING -> DELIVERED skips the lease entirely.
    with psycopg.connect(ADMIN_DSN) as connection, pytest.raises(psycopg.Error):
        connection.execute(
            "UPDATE alert_outbox SET state = 'DELIVERED', completed_at = now(), "
            "attempt_count = 1, last_http_status = 200"
        )


def test_outbox_rows_must_begin_pending_and_unattempted(outbox: AlertOutboxRepository) -> None:
    _evaluate("http://127.0.0.1:9/alerts", prefix="insert-guard")
    row = _first_outbox(outbox, _principal())
    with psycopg.connect(ADMIN_DSN) as connection, pytest.raises(psycopg.Error):
        connection.execute(
            """
            INSERT INTO alert_outbox (
                tenant_id, evaluation_id, alert_fingerprint, transition,
                destination_host, payload_json, payload_hash, idempotency_key,
                state, attempt_count, max_attempts, redrive_count,
                next_attempt_at, enqueued_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, 'x.example', '{}'::jsonb, %s, 'forced',
                'IN_FLIGHT', 3, 5, 0, now(), now(), now()
            )
            """,
            (
                row["tenant_id"],
                row["evaluation_id"],
                row["alert_fingerprint"],
                row["transition"],
                "a" * 64,
            ),
        )


def test_outbox_identity_must_match_its_evaluation(outbox: AlertOutboxRepository) -> None:
    _evaluate("http://127.0.0.1:9/alerts", prefix="identity-match")
    row = _first_outbox(outbox, _principal())
    with psycopg.connect(ADMIN_DSN) as connection, pytest.raises(psycopg.Error):
        connection.execute(
            """
            INSERT INTO alert_outbox (
                tenant_id, evaluation_id, alert_fingerprint, transition,
                destination_host, payload_json, payload_hash, idempotency_key,
                state, attempt_count, max_attempts, redrive_count,
                next_attempt_at, enqueued_at, updated_at
            ) VALUES (
                't_beta', %s, %s, %s, 'x.example', '{}'::jsonb, %s, 'mismatch',
                'PENDING', 0, 5, 0, now(), now(), now()
            )
            """,
            (row["evaluation_id"], row["alert_fingerprint"], row["transition"], "a" * 64),
        )


def test_terminal_ledger_row_is_written_once_per_delivery(
    outbox: AlertOutboxRepository,
) -> None:
    with RecordingWebhookServer() as receiver:
        _evaluate(receiver.url, prefix="terminal-ledger")
        build_worker(
            outbox, _settings(receiver.url), worker_id="w-tl", clock=lambda: BASE_AT
        ).run_once()

    with psycopg.connect(ADMIN_DSN, row_factory=psycopg.rows.dict_row) as connection:
        rows = connection.execute("SELECT * FROM alert_delivery_attempt").fetchall()
    assert len(rows) == 1
    assert rows[0]["status"] == "DELIVERED"
    assert rows[0]["attempt_count"] == 1
    assert rows[0]["http_status"] == 200


def test_dead_letter_writes_a_failed_terminal_ledger_row(
    outbox: AlertOutboxRepository,
) -> None:
    with RecordingWebhookServer(status=400) as receiver:
        _evaluate(receiver.url, prefix="terminal-failed")
        build_worker(
            outbox, _settings(receiver.url), worker_id="w-tf", clock=lambda: BASE_AT
        ).run_once()

    with psycopg.connect(ADMIN_DSN, row_factory=psycopg.rows.dict_row) as connection:
        rows = connection.execute("SELECT * FROM alert_delivery_attempt").fetchall()
    assert len(rows) == 1
    assert rows[0]["status"] == "FAILED"
    assert rows[0]["error_class"] == "http_400"


def test_secrets_never_reach_outbox_rows_or_evidence(outbox: AlertOutboxRepository) -> None:
    token = "super-secret-token-value"
    with RecordingWebhookServer() as receiver:
        enqueuer = WebhookOutboxEnqueuer(_settings(receiver.url, token=token))
        service = AlertService(
            AlertRepository(Database(APP_DSN), delivery_enqueuer=enqueuer),
            clock=lambda: BASE_AT,
        )
        service.evaluate(_principal(), _firing_snapshot(), idempotency_prefix="secret-check")
        build_worker(
            outbox,
            _settings(receiver.url, token=token),
            worker_id="w-secret",
            clock=lambda: BASE_AT,
        ).run_once()

    assert receiver.requests[0]["authorization"] == f"Bearer {token}"
    with psycopg.connect(ADMIN_DSN) as connection:
        for table in ("alert_outbox", "alert_delivery_attempt_event", "alert_delivery_attempt"):
            dumped = connection.execute(
                f"SELECT coalesce(string_agg(t::text, ' '), '') FROM {table} t"
            ).fetchone()
            assert token not in str(dumped[0])
