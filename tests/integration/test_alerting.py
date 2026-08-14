from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from inspect import signature
from pathlib import Path

import psycopg
import pytest

from stockoutops.alerting.contracts import AlertCorrelation, AlertMetricSnapshot
from stockoutops.alerting.report import (
    ALERT_REPORT_TITLE,
    build_alert_report,
    load_shadow_alert_source,
    write_alert_reports,
)
from stockoutops.alerting.repository import AlertRepository
from stockoutops.alerting.service import AlertService
from stockoutops.database import Database, run_migrations
from stockoutops.errors import ConflictError, NotFoundError
from stockoutops.identity import Principal
from tests.integration.conftest import ADMIN_DSN, APP_DSN


def _principal(tenant_id: str = "t_alpha") -> Principal:
    return Principal("alert-test-operator", tenant_id, frozenset({"operator"}))


def _snapshot(**overrides) -> AlertMetricSnapshot:
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


@pytest.fixture
def alert_repository(clean_database) -> AlertRepository:
    return AlertRepository(Database(APP_DSN))


@pytest.fixture
def alert_service(alert_repository: AlertRepository) -> AlertService:
    return AlertService(
        alert_repository,
        clock=lambda: datetime(2026, 8, 14, 12, 0, tzinfo=UTC),
    )


def _count_alert_events() -> int:
    with psycopg.connect(ADMIN_DSN) as connection:
        return connection.execute("SELECT count(*) FROM alert_evaluation_event").fetchone()[0]


@pytest.mark.integration
def test_alert_migration_is_recorded_and_repeat_is_noop(postgres_schema) -> None:
    with psycopg.connect(ADMIN_DSN) as connection:
        versions = {
            row[0] for row in connection.execute("SELECT version FROM schema_migration").fetchall()
        }
    assert "0006_m2_alert_policy_foundation.sql" in versions
    assert (
        run_migrations(
            ADMIN_DSN,
            migrations_dir=Path("migrations"),
            app_role_password="app-local-only",
        )
        == []
    )


@pytest.mark.integration
def test_duplicate_evaluation_is_idempotent_and_conflict_fails_closed(
    alert_service: AlertService,
) -> None:
    first = alert_service.evaluate(_principal(), _snapshot(), idempotency_prefix="same-input")
    replay = alert_service.evaluate(_principal(), _snapshot(), idempotency_prefix="same-input")
    assert [item.evaluation_id for item in replay] == [item.evaluation_id for item in first]
    assert all(item.idempotent_replay for item in replay)
    assert _count_alert_events() == 5
    with pytest.raises(ConflictError) as conflict:
        alert_service.evaluate(
            _principal(),
            _snapshot(window_id="changed-window", source_report_sha256="b" * 64),
            idempotency_prefix="same-input",
        )
    assert conflict.value.code == "ALERT_IDEMPOTENCY_CONFLICT"
    assert _count_alert_events() == 5


@pytest.mark.integration
def test_concurrent_same_alert_evaluation_converges_on_one_event_per_policy(
    alert_service: AlertService,
) -> None:
    def evaluate_once():
        return alert_service.evaluate(
            _principal(), _snapshot(), idempotency_prefix="concurrent-input"
        )

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = [future.result() for future in [pool.submit(evaluate_once) for _ in range(6)]]
    assert _count_alert_events() == 5
    assert len({item.evaluation_id for result in results for item in result}) == 5
    assert sum(not item.idempotent_replay for result in results for item in result) == 5
    assert sum(item.idempotent_replay for result in results for item in result) == 25


@pytest.mark.integration
def test_firing_to_resolved_is_explicit_and_current_state_converges(
    alert_service: AlertService,
    alert_repository: AlertRepository,
) -> None:
    firing = alert_service.evaluate(
        _principal(),
        _snapshot(escalation_disagreement_count=3),
        idempotency_prefix="firing-window",
    )[1]
    assert firing.state == "FIRING"
    assert firing.transition == "FIRED"
    resolved = alert_service.evaluate(
        _principal(),
        _snapshot(
            window_id="alert-window-002",
            source_report_sha256="b" * 64,
            escalation_disagreement_count=1,
        ),
        idempotency_prefix="resolved-window",
    )[1]
    assert resolved.previous_state == "FIRING"
    assert resolved.state == "RESOLVED"
    assert resolved.transition == "RESOLVED"
    current = alert_repository.current(_principal(), resolved.alert_fingerprint)
    assert current.evaluation_id == resolved.evaluation_id
    assert [
        item.state for item in alert_repository.events(_principal(), resolved.alert_fingerprint)
    ] == [
        "FIRING",
        "RESOLVED",
    ]


@pytest.mark.integration
def test_persisted_alert_reads_are_tenant_scoped(
    alert_service: AlertService,
    alert_repository: AlertRepository,
) -> None:
    evaluation = alert_service.evaluate(
        _principal(), _snapshot(), idempotency_prefix="tenant-boundary"
    )[0]
    with pytest.raises(NotFoundError):
        alert_repository.events(_principal("t_beta"), evaluation.alert_fingerprint)
    assert _count_alert_events() == 5


@pytest.mark.integration
def test_alert_history_rejects_update_and_delete(
    alert_service: AlertService,
) -> None:
    evaluation = alert_service.evaluate(
        _principal(), _snapshot(), idempotency_prefix="append-only"
    )[0]
    for dsn in (ADMIN_DSN, APP_DSN):
        with psycopg.connect(dsn) as connection, pytest.raises(psycopg.Error):
            connection.execute(
                "UPDATE alert_evaluation_event SET state = 'FIRING' WHERE alert_evaluation_id = %s",
                (evaluation.evaluation_id,),
            )
        with psycopg.connect(dsn) as connection, pytest.raises(psycopg.Error):
            connection.execute(
                "DELETE FROM alert_evaluation_event WHERE alert_evaluation_id = %s",
                (evaluation.evaluation_id,),
            )


@pytest.mark.integration
def test_external_action_violation_fires_sev1_and_fails_closed_without_delivery(
    alert_service: AlertService,
) -> None:
    with pytest.raises(ConflictError) as violation:
        alert_service.evaluate(
            _principal(),
            _snapshot(external_action_count=1),
            idempotency_prefix="external-action-violation",
        )
    assert violation.value.code == "SHADOW_EXTERNAL_ACTION_DETECTED"
    with psycopg.connect(ADMIN_DSN, row_factory=psycopg.rows.dict_row) as connection:
        row = connection.execute("SELECT * FROM alert_evaluation_event").fetchone()
    assert row["severity"] == "SEV1"
    assert row["state"] == "FIRING"
    assert row["external_alert_delivery_count"] == 0
    assert row["execute"] is False
    assert _count_alert_events() == 1


@pytest.mark.integration
def test_alert_evaluation_does_not_mutate_workflow_or_review_state(
    alert_service: AlertService,
) -> None:
    with psycopg.connect(ADMIN_DSN) as connection:
        before = connection.execute(
            "SELECT (SELECT count(*) FROM workflow_event), "
            "(SELECT count(*) FROM review_decision), "
            "(SELECT count(*) FROM shadow_run)"
        ).fetchone()
    results = alert_service.evaluate(
        _principal(), _snapshot(), idempotency_prefix="no-workflow-mutation"
    )
    with psycopg.connect(ADMIN_DSN) as connection:
        after = connection.execute(
            "SELECT (SELECT count(*) FROM workflow_event), "
            "(SELECT count(*) FROM review_decision), "
            "(SELECT count(*) FROM shadow_run)"
        ).fetchone()
    assert before == after == (0, 0, 0)
    assert all(item.external_alert_delivery_count == 0 for item in results)
    assert all(item.live_slo_evidence_eligible is False for item in results)


@pytest.mark.integration
def test_alert_source_and_reports_are_deterministic_and_honestly_labelled(
    alert_service: AlertService,
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "shadow-report.json"
    source_path.write_text(
        json.dumps(
            {
                "title": "M2 SHADOW FOUNDATION — SIMULATED ENGINEERING REHEARSAL",
                "evidence_label": "SIMULATED",
                "exact_git_sha": "a" * 40,
                "generated_at": "2026-08-14T12:00:00+00:00",
                "case_pack": {"version": "m2-shadow-cases-v1-2026-08-13"},
                "controls": {
                    "provider": "deterministic-stub-v1",
                    "execute": False,
                    "external_action_count": 0,
                },
                "cases": [
                    {
                        "result": {
                            "tenant_id": "t_alpha",
                            "actual": {
                                "execute": False,
                                "external_action_count": 0,
                                "latency_ms": 0,
                            },
                            "comparison": {
                                "unsupported_citation_count": 0,
                                "missing_required_evidence_count": 0,
                                "entries": [
                                    {
                                        "field_name": "escalated",
                                        "agreement": "exact",
                                    }
                                ],
                            },
                        }
                    }
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    source = load_shadow_alert_source(source_path)
    evaluations = alert_service.evaluate(
        _principal(), source.snapshots[0], idempotency_prefix=source.source_report_sha256
    )
    report = build_alert_report(
        source,
        evaluations,
        git_sha="b" * 40,
        generated_at=datetime(2026, 8, 14, 12, 0, tzinfo=UTC),
    )
    written = write_alert_reports(report, tmp_path / "reports")
    assert report["title"] == ALERT_REPORT_TITLE
    assert report["controls"] == {
        "execute": False,
        "external_action_count": 0,
        "external_alert_delivery_count": 0,
        "live_slo_evidence_eligible": False,
        "provider": "deterministic-policy-evaluator-v1",
        "aws_resources_used": 0,
        "openai_calls": 0,
    }
    assert report["summary"]["measurement_status_counts"] == {
        "EVALUATED": 4,
        "UNMEASURED": 1,
    }
    assert report["m2_status"]["M2-04"].startswith("PENDING")
    assert written.json_path.exists()
    assert written.markdown_path.exists()
    assert len(written.json_sha256) == len(written.markdown_sha256) == 64
    markdown = written.markdown_path.read_text(encoding="utf-8")
    assert "External alert delivery count: `0`" in markdown
    assert "ENGINEERING TEST THRESHOLD" in markdown
    assert "M2-04: PENDING" in markdown


@pytest.mark.integration
def test_alert_repository_tenant_choke_point_is_explicit() -> None:
    for method in (AlertRepository.record, AlertRepository.events, AlertRepository.current):
        assert next(iter(signature(method).parameters)) == "self"
        assert list(signature(method).parameters)[1] == "principal"
