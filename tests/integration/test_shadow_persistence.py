from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest

from stockoutops.database import Database, run_migrations
from stockoutops.errors import ConflictError, NotFoundError, ValidationError
from stockoutops.evidence.tools import EvidenceTools
from stockoutops.identity import Principal
from stockoutops.schemas import ReviewRequest
from stockoutops.shadow.cases import load_case_pack, seed_case_fixtures
from stockoutops.shadow.report import aggregate_report, write_reports
from stockoutops.shadow.repository import ShadowRepository
from stockoutops.shadow.service import ShadowService
from tests.integration.conftest import ADMIN_DSN, APP_DSN

CASES_DIR = Path("evaluation/shadow/cases/v1")


def _count(table: str) -> int:
    assert table in {
        "shadow_run",
        "shadow_diff",
        "shadow_control_event",
        "investigation_run",
        "workflow_event",
        "review_decision",
        "tool_invocation",
    }
    with psycopg.connect(ADMIN_DSN) as connection:
        return connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


@pytest.fixture
def loaded_pack(clean_database):
    loaded = load_case_pack(CASES_DIR)
    seed_case_fixtures(ADMIN_DSN, loaded.pack)
    return loaded


@pytest.fixture
def shadow_service(service, clock, loaded_pack) -> ShadowService:
    service.evidence_tools = EvidenceTools(
        service.repository, manifest_version=loaded_pack.pack.case_pack_version
    )
    return ShadowService(ShadowRepository(Database(APP_DSN)), service, clock=clock)


def _principal(tenant_id: str = "t_alpha") -> Principal:
    return Principal(f"shadow-operator-{tenant_id}", tenant_id, frozenset({"operator"}))


@pytest.mark.integration
def test_migration_is_recorded_and_repeat_is_noop(postgres_schema) -> None:
    with psycopg.connect(ADMIN_DSN) as connection:
        versions = {
            row[0] for row in connection.execute("SELECT version FROM schema_migration").fetchall()
        }
    assert "0004_m2_shadow_foundation.sql" in versions
    assert (
        run_migrations(
            ADMIN_DSN,
            migrations_dir=Path("migrations"),
            app_role_password="app-local-only",
        )
        == []
    )


@pytest.mark.integration
def test_execute_true_fails_before_analysis_or_persistence(
    shadow_service: ShadowService, loaded_pack
) -> None:
    case = loaded_pack.pack.cases[0]
    with pytest.raises(ValidationError, match="execute=false"):
        shadow_service.process(
            _principal(case.tenant_id),
            case,
            case_pack_version=loaded_pack.pack.case_pack_version,
            idempotency_key="execute-true-rejected",
            execute=True,
        )
    assert _count("shadow_run") == 0
    assert _count("investigation_run") == 0
    assert _count("tool_invocation") == 0


@pytest.mark.integration
def test_shadow_run_is_durable_idempotent_and_restart_safe(
    shadow_service: ShadowService, loaded_pack, service, clock
) -> None:
    case = loaded_pack.pack.cases[0]
    principal = _principal(case.tenant_id)
    first = shadow_service.process(
        principal,
        case,
        case_pack_version=loaded_pack.pack.case_pack_version,
        idempotency_key="shadow-stable",
    )
    replacement = ShadowService(ShadowRepository(Database(APP_DSN)), service, clock=clock)
    second = replacement.process(
        principal,
        case,
        case_pack_version=loaded_pack.pack.case_pack_version,
        idempotency_key="different-key-same-case",
    )
    assert second.shadow_run_id == first.shadow_run_id
    assert second.investigation_run_id == first.investigation_run_id
    assert second.output_hash == first.output_hash
    assert second.diff_hash == first.diff_hash
    assert second.idempotent_replay is True
    assert _count("shadow_run") == 1
    assert _count("investigation_run") == 1
    assert _count("review_decision") == 0
    assert first.actual.execute is False
    assert first.actual.external_action_count == 0


@pytest.mark.integration
def test_conflicting_payload_rejected_before_duplicate_analysis(
    shadow_service: ShadowService, loaded_pack
) -> None:
    case = loaded_pack.pack.cases[0]
    principal = _principal(case.tenant_id)
    first = shadow_service.process(
        principal,
        case,
        case_pack_version=loaded_pack.pack.case_pack_version,
        idempotency_key="shadow-conflict",
    )
    changed = case.model_copy(update={"notes": "Changed controlled payload."})
    with pytest.raises(ConflictError, match="different payload"):
        shadow_service.process(
            principal,
            changed,
            case_pack_version=loaded_pack.pack.case_pack_version,
            idempotency_key="shadow-conflict",
        )
    assert _count("shadow_run") == 1
    assert _count("investigation_run") == 1
    events = shadow_service.repository.events(principal, first.shadow_run_id)
    assert events[-1]["payload"]["code"] == "SHADOW_IDEMPOTENCY_CONFLICT"


@pytest.mark.integration
def test_cross_tenant_reads_and_processing_fail_closed(
    shadow_service: ShadowService, loaded_pack
) -> None:
    case = loaded_pack.pack.cases[0]
    alpha = _principal(case.tenant_id)
    result = shadow_service.process(
        alpha,
        case,
        case_pack_version=loaded_pack.pack.case_pack_version,
        idempotency_key="shadow-tenant",
    )
    beta = _principal("t_beta")
    with pytest.raises(NotFoundError):
        shadow_service.repository.get(beta, result.shadow_run_id)
    with pytest.raises(NotFoundError):
        shadow_service.process(
            beta,
            case,
            case_pack_version=loaded_pack.pack.case_pack_version,
            idempotency_key="shadow-cross-tenant",
        )
    assert _count("shadow_run") == 1


@pytest.mark.integration
def test_shadow_analysis_cannot_accept_a_human_review_decision(
    shadow_service: ShadowService, loaded_pack, service
) -> None:
    case = loaded_pack.pack.cases[0]
    operator = _principal(case.tenant_id)
    result = shadow_service.process(
        operator,
        case,
        case_pack_version=loaded_pack.pack.case_pack_version,
        idempotency_key="shadow-review-forbidden",
    )
    detail = service.detail(operator, result.investigation_run_id)
    reviewer = Principal("reviewer-alpha-primary", case.tenant_id, frozenset({"reviewer"}))
    with pytest.raises(ConflictError) as rejected:
        service.review(
            reviewer,
            result.investigation_run_id,
            ReviewRequest(action="approve", draft_hash=detail["draft_hash"]),
            idempotency_key="shadow-review-attempt",
        )
    assert rejected.value.code == "SHADOW_REVIEW_FORBIDDEN"
    assert _count("review_decision") == 0
    audit = service.audit(operator, result.investigation_run_id)
    assert audit["events"][-1]["payload"]["code"] == "SHADOW_REVIEW_FORBIDDEN"


@pytest.mark.integration
def test_shadow_results_and_control_events_reject_mutation(
    shadow_service: ShadowService, loaded_pack
) -> None:
    case = loaded_pack.pack.cases[0]
    result = shadow_service.process(
        _principal(case.tenant_id),
        case,
        case_pack_version=loaded_pack.pack.case_pack_version,
        idempotency_key="shadow-mutation",
    )
    statements = (
        ("UPDATE shadow_run SET provider_label = 'tampered' WHERE shadow_run_id = %s",),
        ("DELETE FROM shadow_run WHERE shadow_run_id = %s",),
        ("UPDATE shadow_diff SET category = 'tampered' WHERE shadow_run_id = %s",),
        ("DELETE FROM shadow_control_event WHERE shadow_run_id = %s",),
    )
    for (statement,) in statements:
        with psycopg.connect(ADMIN_DSN) as connection, pytest.raises(psycopg.Error):
            connection.execute(statement, (result.shadow_run_id,))
        with psycopg.connect(APP_DSN) as connection, pytest.raises(psycopg.Error):
            connection.execute(statement, (result.shadow_run_id,))


@pytest.mark.integration
def test_report_generation_does_not_mutate_workflow_or_review_state(
    shadow_service: ShadowService, loaded_pack, tmp_path: Path
) -> None:
    case = loaded_pack.pack.cases[0]
    result = shadow_service.process(
        _principal(case.tenant_id),
        case,
        case_pack_version=loaded_pack.pack.case_pack_version,
        idempotency_key="shadow-report-no-mutation",
    )
    before_events = _count("workflow_event")
    before_reviews = _count("review_decision")
    report = aggregate_report(
        [result],
        loaded_pack,
        git_sha="a" * 40,
        generated_at=datetime(2026, 8, 13, tzinfo=UTC),
        test_evidence="MEASURED — integration test only.",
    )
    write_reports(report, tmp_path)
    assert _count("workflow_event") == before_events
    assert _count("review_decision") == before_reviews == 0
    assert (
        shadow_service.investigation_service.repository.get_run(
            _principal(case.tenant_id), result.investigation_run_id
        ).state.value
        == "awaiting_human"
    )


@pytest.mark.integration
def test_concurrent_same_case_produces_one_effective_shadow_and_reasoning_run(
    shadow_service: ShadowService, loaded_pack
) -> None:
    case = loaded_pack.pack.cases[0]
    principal = _principal(case.tenant_id)

    def process_once():
        return shadow_service.process(
            principal,
            case,
            case_pack_version=loaded_pack.pack.case_pack_version,
            idempotency_key="shadow-concurrent",
        )

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = [future.result() for future in [pool.submit(process_once) for _ in range(6)]]
    assert len({result.shadow_run_id for result in results}) == 1
    assert len({result.investigation_run_id for result in results}) == 1
    assert _count("shadow_run") == 1
    assert _count("investigation_run") == 1
    with psycopg.connect(ADMIN_DSN) as connection:
        reasoning_count = connection.execute(
            "SELECT count(*) FROM tool_invocation WHERE tool_name = 'reasoning'"
        ).fetchone()[0]
    assert reasoning_count == 1
    assert sum(not result.idempotent_replay for result in results) == 1
    assert sum(result.actual.external_action_count for result in results) == 0


@pytest.mark.integration
def test_shadow_repository_tenant_choke_point_is_explicit() -> None:
    for method in (ShadowRepository.get, ShadowRepository.events):
        assert next(iter(method.__annotations__)) == "principal"
