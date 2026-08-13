from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest

from stockoutops.database import Database, run_migrations
from stockoutops.errors import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from stockoutops.identity import Principal
from stockoutops.shadow.cases import load_case_pack
from stockoutops.shadow.collection import aggregate_collection
from stockoutops.shadow.intake import ShadowIntakeRepository, ShadowIntakeService, exclude_main
from tests.integration.conftest import ADMIN_DSN, APP_DSN
from tests.shadow_fixtures import genuine_uat_schema_fixture

CASES_DIR = Path("evaluation/shadow/cases/v1")


def _count(table: str) -> int:
    assert table in {
        "shadow_case_intake",
        "shadow_case_intake_event",
        "shadow_run",
        "investigation_run",
        "review_decision",
        "tool_invocation",
    }
    with psycopg.connect(ADMIN_DSN) as connection:
        return connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


@pytest.fixture
def intake_service(clean_database) -> ShadowIntakeService:
    return ShadowIntakeService(
        ShadowIntakeRepository(Database(APP_DSN)),
        clock=lambda: datetime(2026, 8, 13, 12, 0, tzinfo=UTC),
    )


def _operator(tenant_id: str = "t_alpha") -> Principal:
    return Principal(f"shadow-intake-{tenant_id}", tenant_id, frozenset({"operator"}))


def _reviewer(tenant_id: str = "t_alpha") -> Principal:
    return Principal(f"shadow-reviewer-{tenant_id}", tenant_id, frozenset({"reviewer"}))


@pytest.mark.integration
def test_migration_0005_is_recorded_and_repeat_is_noop(postgres_schema) -> None:
    with psycopg.connect(ADMIN_DSN) as connection:
        versions = {
            row[0] for row in connection.execute("SELECT version FROM schema_migration").fetchall()
        }
    assert "0005_m2_uat_shadow_intake.sql" in versions
    assert (
        run_migrations(
            ADMIN_DSN,
            migrations_dir=Path("migrations"),
            app_role_password="app-local-only",
        )
        == []
    )


@pytest.mark.integration
def test_execute_true_is_rejected_before_intake_persistence(
    intake_service: ShadowIntakeService,
) -> None:
    case = genuine_uat_schema_fixture()
    with pytest.raises(ValidationError, match="execute=false"):
        intake_service.import_case(_operator(), case, execute=True)
    assert _count("shadow_case_intake") == 0
    assert _count("investigation_run") == 0
    assert _count("tool_invocation") == 0
    assert _count("shadow_run") == 0


@pytest.mark.integration
def test_simulated_pack_case_cannot_be_imported_as_genuine(
    intake_service: ShadowIntakeService,
) -> None:
    case = load_case_pack(CASES_DIR).pack.cases[0]
    with pytest.raises(ValidationError, match="rejects SIMULATED"):
        intake_service.import_case(_operator(case.tenant_id), case, execute=False)
    assert _count("shadow_case_intake") == 0


@pytest.mark.integration
def test_duplicate_case_version_replays_and_conflict_fails_closed(
    intake_service: ShadowIntakeService,
) -> None:
    case = genuine_uat_schema_fixture()
    first, created = intake_service.import_case(_operator(), case, execute=False)
    assert created is True
    replay, replayed_created = intake_service.import_case(_operator(), case, execute=False)
    assert replayed_created is False
    assert replay.intake_id == first.intake_id
    changed = genuine_uat_schema_fixture(notes="Changed fixture payload; still not genuine UAT.")
    with pytest.raises(ConflictError, match="different payload"):
        intake_service.import_case(_operator(), changed, execute=False)
    assert _count("shadow_case_intake") == 1
    assert _count("investigation_run") == 0
    events = intake_service.repository.events(_operator(), first.intake_id)
    assert events[-1]["payload"]["code"] == "SHADOW_INTAKE_CONFLICT"


@pytest.mark.integration
def test_tenant_mismatch_fails_closed_without_persistence(
    intake_service: ShadowIntakeService,
) -> None:
    case = genuine_uat_schema_fixture()
    with pytest.raises(NotFoundError):
        intake_service.import_case(_operator("t_beta"), case, execute=False)
    assert _count("shadow_case_intake") == 0


@pytest.mark.integration
def test_intake_does_not_create_external_or_analysis_actions(
    intake_service: ShadowIntakeService,
) -> None:
    case = genuine_uat_schema_fixture()
    record, created = intake_service.import_case(_operator(), case, execute=False)
    assert created is True
    assert record.execute is False
    assert record.external_action_count == 0
    assert _count("shadow_run") == 0
    assert _count("investigation_run") == 0
    assert _count("review_decision") == 0
    assert _count("tool_invocation") == 0


@pytest.mark.integration
def test_concurrent_same_case_intake_converges_on_one_row(
    intake_service: ShadowIntakeService,
) -> None:
    case = genuine_uat_schema_fixture()
    principal = _operator()

    def import_once():
        return intake_service.import_case(principal, case, execute=False)

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = [future.result() for future in [pool.submit(import_once) for _ in range(6)]]
    assert len({record.intake_id for record, _created in results}) == 1
    assert sum(created for _record, created in results) == 1
    assert _count("shadow_case_intake") == 1
    assert _count("shadow_run") == 0


@pytest.mark.integration
def test_synthetic_pack_stays_out_of_official_m2_05_after_intake_fixture(
    intake_service: ShadowIntakeService,
) -> None:
    record, _created = intake_service.import_case(
        _operator(), genuine_uat_schema_fixture(), execute=False
    )
    loaded = load_case_pack(CASES_DIR)
    pending = aggregate_collection(
        loaded,
        git_sha="f" * 40,
        generated_at=datetime(2026, 8, 13, tzinfo=UTC),
        intake_records=intake_service.repository.list_all(),
        accepted_ids=set(),
    )
    assert pending["official_m2_05"]["eligible_count"] == 0
    assert pending["simulated"]["case_count"] == 12
    intake_service.repository.accept_for_m2_05(
        _operator(),
        record.intake_id,
        now=datetime(2026, 8, 13, 12, 1, tzinfo=UTC),
    )
    accepted = aggregate_collection(
        loaded,
        git_sha="f" * 40,
        generated_at=datetime(2026, 8, 13, tzinfo=UTC),
        intake_records=intake_service.repository.list_all(),
        accepted_ids=intake_service.repository.accepted_intake_ids(),
    )
    assert accepted["official_m2_05"]["eligible_count"] == 1
    assert accepted["official_m2_05"]["synthetic_contribution"] == 0
    assert accepted["simulated"]["official_m2_05_eligible_count"] == 0


@pytest.mark.integration
def test_concurrent_m2_05_acceptance_appends_one_audit_event(
    intake_service: ShadowIntakeService,
) -> None:
    record, _created = intake_service.import_case(
        _operator(), genuine_uat_schema_fixture(), execute=False
    )

    def accept_once():
        return intake_service.repository.accept_for_m2_05(
            _operator(),
            record.intake_id,
            now=datetime(2026, 8, 13, 12, 1, tzinfo=UTC),
        )

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = [future.result() for future in [pool.submit(accept_once) for _ in range(6)]]
    assert {item.intake_id for item in results} == {record.intake_id}
    events = intake_service.repository.events(_operator(), record.intake_id)
    assert sum(event["event_type"] == "accepted_for_m2_05" for event in events) == 1


@pytest.mark.integration
def test_exclusion_requires_operator_and_preserves_tenant_boundary(
    intake_service: ShadowIntakeService,
) -> None:
    record, _created = intake_service.import_case(
        _operator(), genuine_uat_schema_fixture(), execute=False
    )
    with pytest.raises(AuthorizationError):
        intake_service.exclude_case(_reviewer(), record.intake_id, reason="participant_withdrawal")
    with pytest.raises(NotFoundError):
        intake_service.exclude_case(
            _operator("t_beta"), record.intake_id, reason="participant_withdrawal"
        )
    assert intake_service.repository.excluded_intake_ids() == {}


@pytest.mark.integration
def test_exclusion_rejects_non_allow_listed_reason(
    intake_service: ShadowIntakeService,
) -> None:
    record, _created = intake_service.import_case(
        _operator(), genuine_uat_schema_fixture(), execute=False
    )
    with pytest.raises(ValidationError, match="allow-listed"):
        intake_service.exclude_case(
            _operator(), record.intake_id, reason="person-name-or-free-text"
        )
    assert intake_service.repository.excluded_intake_ids() == {}


@pytest.mark.integration
def test_owner_exclusion_command_is_idempotent_and_removes_collection_eligibility(
    intake_service: ShadowIntakeService,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    record, _created = intake_service.import_case(
        _operator(), genuine_uat_schema_fixture(), execute=False
    )
    intake_service.repository.accept_for_m2_05(
        _operator(),
        record.intake_id,
        now=datetime(2026, 8, 13, 12, 1, tzinfo=UTC),
    )
    monkeypatch.setenv("DATABASE_URL", APP_DSN)
    arguments = [
        "stockoutops-shadow-exclude",
        "--intake-id",
        str(record.intake_id),
        "--tenant-id",
        record.tenant_id,
        "--reason",
        "participant_withdrawal",
    ]
    monkeypatch.setattr(sys, "argv", arguments)
    exclude_main()
    assert json.loads(capsys.readouterr().out)["created"] is True
    exclude_main()
    assert json.loads(capsys.readouterr().out)["created"] is False

    events = intake_service.repository.events(_operator(), record.intake_id)
    assert sum(event["event_type"] == "excluded" for event in events) == 1
    loaded = load_case_pack(CASES_DIR)
    report = aggregate_collection(
        loaded,
        git_sha="f" * 40,
        generated_at=datetime(2026, 8, 13, tzinfo=UTC),
        intake_records=intake_service.repository.list_all(),
        accepted_ids=intake_service.repository.accepted_intake_ids(),
        excluded=intake_service.repository.excluded_intake_ids(),
    )
    assert report["official_m2_05"]["eligible_count"] == 0
    assert report["official_m2_05"]["synthetic_contribution"] == 0
    assert report["cumulative"]["excluded_count"] == 1
    assert report["controls"]["execute"] is False
    assert report["controls"]["external_action_count"] == 0


@pytest.mark.integration
def test_intake_repository_tenant_choke_point_is_explicit() -> None:
    for method in (
        ShadowIntakeRepository.get,
        ShadowIntakeRepository.events,
        ShadowIntakeRepository.exclude,
    ):
        assert next(iter(method.__annotations__)) == "principal"
