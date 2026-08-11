from __future__ import annotations

from uuid import UUID

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from stockoutops.database import Database
from stockoutops.evidence.provenance import canonical_hash
from stockoutops.reasoning.base import ReasoningOutcome
from stockoutops.reasoning.deterministic_stub import DeterministicStubAdapter
from stockoutops.repository import Repository
from stockoutops.schemas import IntakeRequest
from stockoutops.service import InvestigationService
from stockoutops.state_machine import RunState
from tests.integration.conftest import (
    ADMIN_DSN,
    APP_DSN,
    CANONICAL_REQUEST,
    PRINCIPALS,
    auth,
    create_run,
)


def _count(table: str, where: str = "TRUE", params=()):
    allowed = {
        "investigation_run",
        "tool_invocation",
        "review_decision",
        "workflow_event",
    }
    assert table in allowed
    with psycopg.connect(ADMIN_DSN) as connection:
        return connection.execute(f"SELECT count(*) FROM {table} WHERE {where}", params).fetchone()[
            0
        ]


@pytest.mark.integration
def test_identity_and_client_authority_fail_closed(client: TestClient) -> None:
    assert client.post("/v1/investigations", json=CANONICAL_REQUEST).status_code == 401
    invalid = client.post(
        "/v1/investigations",
        headers={"Authorization": "Bearer invalid", "Idempotency-Key": "x"},
        json=CANONICAL_REQUEST,
    )
    assert invalid.status_code == 401
    body = {**CANONICAL_REQUEST, "tenant_id": "t_beta"}
    injected = client.post(
        "/v1/investigations",
        headers={**auth("operator_alpha"), "Idempotency-Key": "x"},
        json=body,
    )
    assert injected.status_code == 422
    query = client.get("/healthz?role=reviewer")
    assert query.status_code == 400


@pytest.mark.integration
def test_intake_is_restart_safe_and_idempotent(
    client: TestClient,
    service: InvestigationService,
    identity_provider,
    clock,
) -> None:
    headers = {**auth("operator_alpha"), "Idempotency-Key": "intake-stable"}
    first = client.post("/v1/investigations", headers=headers, json=CANONICAL_REQUEST)
    second = client.post("/v1/investigations", headers=headers, json=CANONICAL_REQUEST)
    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["run_id"] == second.json()["run_id"]
    assert second.json()["idempotent_replay"] is True
    assert _count("investigation_run") == 1
    assert _count("tool_invocation", "tool_name = 'reasoning'") == 1

    replacement = InvestigationService(
        Repository(Database(APP_DSN)),
        service.evidence_tools.__class__(
            Repository(Database(APP_DSN)), manifest_version="v1-2026-08-10"
        ),
        service.reasoning,
        identity_provider,
        clock=clock,
    )
    request = IntakeRequest.model_validate(CANONICAL_REQUEST)
    resumed, created = replacement.intake(
        PRINCIPALS["local-test-operator-alpha-NOT-A-SECRET"],
        request,
        idempotency_key="intake-stable",
    )
    assert created is False
    assert str(resumed.run_id) == first.json()["run_id"]
    assert _count("tool_invocation", "tool_name = 'reasoning'") == 1


@pytest.mark.integration
def test_intake_key_payload_conflict_is_audited_without_mutation(
    client: TestClient,
) -> None:
    headers = {**auth("operator_alpha"), "Idempotency-Key": "intake-conflict"}
    first = client.post("/v1/investigations", headers=headers, json=CANONICAL_REQUEST)
    changed = {**CANONICAL_REQUEST, "supplier_id": "SUPPLIER-CHANGED"}
    conflict = client.post("/v1/investigations", headers=headers, json=changed)
    assert first.status_code == 201
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"
    assert _count("investigation_run") == 1
    audit = client.get(
        f"/v1/investigations/{first.json()['run_id']}/audit",
        headers=auth("operator_alpha"),
    )
    assert any(event["event_type"] == "intake_rejected" for event in audit.json()["events"])


@pytest.mark.integration
def test_cross_tenant_access_returns_404_and_zero_leakage(client: TestClient) -> None:
    run = create_run(client, key="tenant-boundary")
    for suffix in ("", "/audit"):
        response = client.get(
            f"/v1/investigations/{run['run_id']}{suffix}",
            headers=auth("operator_beta"),
        )
        assert response.status_code == 404
        assert run["run_id"] not in response.text


@pytest.mark.integration
def test_t1_t2_t3_and_reasoning_are_complete_and_cited(client: TestClient) -> None:
    run = create_run(client, key="evidence-complete")
    assert run["state"] == "awaiting_human"
    assert len(run["evidence"]) == 3
    evidence_ids = {item["evidence_id"] for item in run["evidence"]}
    assert {item["tool"] for item in run["evidence"]} == {
        "T1_inventory",
        "T2_sales_demand",
        "T3_supplier",
    }
    citations = (
        run["draft"]["root_cause_hypothesis"]["citations"]
        + run["draft"]["recommendation_draft"]["citations"]
    )
    assert citations
    assert set(citations) <= evidence_ids


@pytest.mark.integration
def test_missing_and_stale_evidence_stop_before_reasoning(client: TestClient) -> None:
    missing = {
        **CANONICAL_REQUEST,
        "supplier_id": "SUPPLIER-MISSING",
    }
    missing_response = client.post(
        "/v1/investigations",
        headers={**auth("operator_alpha"), "Idempotency-Key": "missing-evidence"},
        json=missing,
    )
    assert missing_response.status_code == 201
    assert missing_response.json()["state"] == "escalated"
    missing_run = UUID(missing_response.json()["run_id"])
    assert _count("tool_invocation", "run_id = %s AND tool_name = 'reasoning'", (missing_run,)) == 0

    with psycopg.connect(ADMIN_DSN) as connection, connection.transaction():
        connection.execute(
            """
            UPDATE inventory_fixture
            SET updated_at = '2026-08-08T00:00:00Z'
            WHERE tenant_id = 't_alpha' AND sku_id = 'SKU-001' AND store_id = 'STORE-001'
            """
        )
    stale_response = client.post(
        "/v1/investigations",
        headers={**auth("operator_alpha"), "Idempotency-Key": "stale-evidence"},
        json=CANONICAL_REQUEST,
    )
    assert stale_response.status_code == 201
    assert stale_response.json()["state"] == "escalated"
    stale_run = UUID(stale_response.json()["run_id"])
    assert _count("tool_invocation", "run_id = %s AND tool_name = 'reasoning'", (stale_run,)) == 0


@pytest.mark.integration
def test_invalid_provenance_stops_before_reasoning(
    client: TestClient, service: InvestigationService, monkeypatch
) -> None:
    original = service.evidence_tools.inventory

    def invalid_inventory(*args, **kwargs):
        item = original(*args, **kwargs)
        item.content_hash = "0" * 64
        return item

    monkeypatch.setattr(service.evidence_tools, "inventory", invalid_inventory)
    response = client.post(
        "/v1/investigations",
        headers={**auth("operator_alpha"), "Idempotency-Key": "invalid-provenance"},
        json=CANONICAL_REQUEST,
    )
    assert response.status_code == 201
    assert response.json()["state"] == "escalated"
    assert (
        _count(
            "tool_invocation",
            "run_id = %s AND tool_name = 'reasoning'",
            (UUID(response.json()["run_id"]),),
        )
        == 0
    )


@pytest.mark.integration
def test_unknown_model_citation_is_audited_and_escalated_before_review(
    client: TestClient, service: InvestigationService
) -> None:
    class UnknownCitationAdapter:
        def reason(self, evidence):
            valid = DeterministicStubAdapter().reason(evidence)
            valid.result.root_cause_hypothesis.citations = ["ev_" + "0" * 64]
            return ReasoningOutcome(
                result=valid.result,
                model_id=valid.model_id,
                prompt_hash=valid.prompt_hash,
                input_hash=valid.input_hash,
                output_hash=canonical_hash(valid.result.model_dump(mode="json")),
                input_tokens=None,
                output_tokens=None,
                latency_ms=0,
                estimated_cost_usd=0,
            )

    service.reasoning = UnknownCitationAdapter()
    response = client.post(
        "/v1/investigations",
        headers={**auth("operator_alpha"), "Idempotency-Key": "unknown-citation"},
        json=CANONICAL_REQUEST,
    )
    assert response.status_code == 201
    assert response.json()["state"] == "escalated"
    assert (
        _count(
            "tool_invocation",
            "run_id = %s AND tool_name = 'reasoning' AND status = 'failed'",
            (UUID(response.json()["run_id"]),),
        )
        == 1
    )


@pytest.mark.integration
def test_invalid_transition_is_rejected_and_audited(
    service: InvestigationService,
) -> None:
    principal = PRINCIPALS["local-test-operator-alpha-NOT-A-SECRET"]
    request = IntakeRequest.model_validate(CANONICAL_REQUEST)
    run, _ = service.repository.begin_intake(
        principal,
        request,
        idempotency_key="invalid-transition",
        payload_hash="a" * 64,
        assigned_reviewer_id="reviewer-alpha-primary",
        now=service.clock(),
    )
    with pytest.raises(Exception, match="not allowed"):
        service.repository.transition(
            principal,
            run,
            RunState.REASONING,
            event_type="invalid",
            now=service.clock(),
        )
    assert service.repository.get_run(principal, run.run_id).state == RunState.CREATED
    assert service.repository.audit(principal, run.run_id)[-1]["payload"]["code"] == (
        "INVALID_TRANSITION"
    )


@pytest.mark.integration
def test_repository_tenant_choke_point_is_explicit() -> None:
    tenant_methods = [
        Repository.get_run,
        Repository.fetch_inventory_fixture,
        Repository.fetch_demand_fixture,
        Repository.fetch_supplier_fixture,
        Repository.audit,
        Repository.get_decision,
    ]
    for method in tenant_methods:
        assert next(iter(method.__annotations__)) == "principal"


@pytest.mark.integration
def test_append_only_events_reject_update_and_delete(
    client: TestClient,
) -> None:
    create_run(client, key="append-only")
    for statement in (
        "UPDATE workflow_event SET event_type = 'tampered'",
        "DELETE FROM workflow_event",
    ):
        with (
            psycopg.connect(APP_DSN, row_factory=dict_row) as connection,
            pytest.raises(psycopg.Error),
        ):
            connection.execute(statement)
        with (
            psycopg.connect(ADMIN_DSN, row_factory=dict_row) as connection,
            pytest.raises(psycopg.Error, match="append-only"),
        ):
            connection.execute(statement)


@pytest.mark.integration
def test_audit_replay_reconstructs_current_state(client: TestClient) -> None:
    run = create_run(client, key="audit-replay")
    response = client.get(
        f"/v1/investigations/{run['run_id']}/audit",
        headers=auth("operator_alpha"),
    )
    assert response.status_code == 200
    assert response.json()["current_state"] == response.json()["replayed_state"]
    assert response.json()["current_state"] == "awaiting_human"


@pytest.mark.integration
def test_audit_replay_ignores_stale_trailing_rejection_event(client: TestClient) -> None:
    """Deterministic regression for the post-merge main CI failure
    (current_state=awaiting_human, replayed_state=drafting_recommendation).

    Independently reproduced root cause: a control_rejected/intake_rejected/
    review_rejected event always has from_state == to_state (it never
    transitions anything - to_state is just a snapshot of whatever the run's
    state happened to be when that rejection's own read ran). Under real
    concurrency, one loser's rejection INSERT can commit - and so receive a
    later event_id - after a genuine later transition's INSERT already
    committed, even though the rejection's own state snapshot was read
    earlier. Audit replay treated the last event with any non-null to_state
    as authoritative, so that stale snapshot silently overwrote the correct
    final state.

    This test fabricates that exact pathological ordering directly (no
    threads, no timing dependence, no flakiness) so it deterministically
    exercises the fix every run: it appends a control_rejected event whose
    to_state is an earlier state than the run's true final state, as the
    last event by event_id, and asserts audit replay is not fooled by it.
    """
    run = create_run(client, key="audit-replay-stale-rejection")
    with psycopg.connect(ADMIN_DSN) as connection, connection.transaction():
        connection.execute(
            """
            INSERT INTO workflow_event (
                run_id, tenant_id, event_type, from_state, to_state,
                actor_id, payload, occurred_at
            ) VALUES (%s, %s, 'control_rejected', %s, %s, %s, %s, now())
            """,
            (
                run["run_id"],
                run["tenant_id"],
                "drafting_recommendation",
                "drafting_recommendation",
                "operator-alpha",
                Jsonb({"code": "STATE_VERSION_CONFLICT"}),
            ),
        )
    response = client.get(
        f"/v1/investigations/{run['run_id']}/audit",
        headers=auth("operator_alpha"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["current_state"] == "awaiting_human"
    assert body["replayed_state"] == "awaiting_human", body
    assert body["events"][-1]["event_type"] == "control_rejected"
    assert body["events"][-1]["to_state"] == "drafting_recommendation"


@pytest.mark.integration
def test_review_page_contains_cited_evidence_surface_and_four_actions(
    client: TestClient,
) -> None:
    response = client.get("/review")
    assert response.status_code == 200
    assert 'id="evidence"' in response.text
    for label in ("Approve", "Edit and Approve", "Reject", "Escalate"):
        assert label in response.text
    assert "localStorage" not in response.text
