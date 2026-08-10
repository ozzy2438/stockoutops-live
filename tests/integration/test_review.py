from __future__ import annotations

from datetime import timedelta
from uuid import UUID

import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.integration.conftest import ADMIN_DSN, auth, create_run


def _review(
    client: TestClient,
    run: dict[str, object],
    *,
    action: str,
    key: str,
    token_name: str = "reviewer_alpha",
    reason: str | None = None,
    edited_payload: dict[str, object] | None = None,
):
    payload = {"action": action, "draft_hash": run["draft_hash"]}
    if reason is not None:
        payload["reason"] = reason
    if edited_payload is not None:
        payload["edited_payload"] = edited_payload
    return client.post(
        f"/v1/investigations/{run['run_id']}/review",
        headers={**auth(token_name), "Idempotency-Key": key},
        json=payload,
    )


def _decision(run_id: str) -> dict[str, object]:
    with psycopg.connect(ADMIN_DSN) as connection:
        row = connection.execute(
            "SELECT * FROM review_decision WHERE run_id = %s", (UUID(run_id),)
        ).fetchone()
    assert row is not None
    columns = (
        "decision_id",
        "run_id",
        "tenant_id",
        "idempotency_key",
        "action",
        "reviewer_id",
        "original_draft",
        "original_draft_hash",
        "edited_payload",
        "edited_payload_hash",
        "reason",
        "decided_at",
    )
    return dict(zip(columns, row, strict=True))


def _decision_count(run_id: str) -> int:
    with psycopg.connect(ADMIN_DSN) as connection:
        return connection.execute(
            "SELECT count(*) FROM review_decision WHERE run_id = %s", (UUID(run_id),)
        ).fetchone()[0]


@pytest.mark.integration
def test_approve_persists_and_duplicate_review_creates_no_decision(
    client: TestClient,
) -> None:
    run = create_run(client, key="approve-run")
    approved = _review(client, run, action="approve", key="approve-once")
    assert approved.status_code == 200
    assert approved.json()["state"] == "closed"
    decision = _decision(run["run_id"])
    assert decision["action"] == "approve"
    assert decision["reviewer_id"] == "reviewer-alpha-primary"
    assert decision["tenant_id"] == "t_alpha"
    assert decision["original_draft_hash"] == run["draft_hash"]

    duplicate = _review(client, run, action="approve", key="approve-once")
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "RUN_ALREADY_DECIDED"
    assert _decision_count(run["run_id"]) == 1


@pytest.mark.integration
def test_edit_and_approve_persists_original_and_edited_payload(
    client: TestClient,
) -> None:
    run = create_run(client, key="edit-run")
    edited = run["draft"].copy()
    edited["recommendation_draft"] = {
        **edited["recommendation_draft"],
        "rationale": "Human-edited simulated recommendation rationale.",
    }
    response = _review(
        client,
        run,
        action="edit_approve",
        key="edit-once",
        edited_payload=edited,
    )
    assert response.status_code == 200
    decision = _decision(run["run_id"])
    assert decision["action"] == "edit_approve"
    assert decision["original_draft"] == run["draft"]
    assert decision["edited_payload"] == edited
    assert decision["edited_payload_hash"] != decision["original_draft_hash"]


@pytest.mark.integration
@pytest.mark.parametrize("action", ["reject", "escalate"])
def test_reject_and_escalate_require_and_persist_reason(client: TestClient, action: str) -> None:
    run = create_run(client, key=f"{action}-run")
    missing = _review(client, run, action=action, key=f"{action}-missing")
    assert missing.status_code == 422
    response = _review(
        client,
        run,
        action=action,
        key=f"{action}-once",
        reason=f"Simulated {action} reason",
    )
    assert response.status_code == 200
    decision = _decision(run["run_id"])
    assert decision["action"] == action
    assert decision["reason"] == f"Simulated {action} reason"


@pytest.mark.integration
def test_wrong_reviewer_is_rejected_and_audited(client: TestClient) -> None:
    run = create_run(client, key="wrong-reviewer-run")
    response = _review(
        client,
        run,
        action="approve",
        key="wrong-reviewer",
        token_name="reviewer_alpha_wrong",
    )
    assert response.status_code == 403
    assert _decision_count(run["run_id"]) == 0
    audit = client.get(
        f"/v1/investigations/{run['run_id']}/audit",
        headers=auth("reviewer_alpha"),
    )
    assert audit.json()["events"][-1]["payload"]["code"] == "WRONG_REVIEWER"


@pytest.mark.integration
def test_stale_payload_hash_is_rejected(client: TestClient) -> None:
    run = create_run(client, key="stale-hash-run")
    run["draft_hash"] = "0" * 64
    response = _review(client, run, action="approve", key="stale-hash")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "STALE_APPROVAL_TARGET"
    assert _decision_count(run["run_id"]) == 0


@pytest.mark.integration
def test_expired_review_is_rejected(
    client: TestClient,
    clock,
) -> None:
    run = create_run(client, key="expired-run")
    clock.value += timedelta(hours=25)
    response = _review(client, run, action="approve", key="expired-review")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "REVIEW_EXPIRED"
    assert _decision_count(run["run_id"]) == 0


@pytest.mark.integration
def test_operator_cannot_review(client: TestClient) -> None:
    run = create_run(client, key="operator-review-run")
    response = _review(
        client,
        run,
        action="approve",
        key="operator-review",
        token_name="operator_alpha",
    )
    assert response.status_code == 403
    assert _decision_count(run["run_id"]) == 0
