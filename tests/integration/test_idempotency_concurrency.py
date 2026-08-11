"""Real-PostgreSQL concurrency regression for the F-1 idempotent-intake race.

Reproduces the scenario Fizz's preliminary assurance flagged: two concurrent
POST /v1/investigations calls sharing a tenant + idempotency key used to
collide on the (tenant_id, idempotency_key) primary key with no lock held
over the "does this key exist yet" gap, surfacing an unhandled
psycopg.errors.UniqueViolation (HTTP 500) to the loser instead of the
documented same-payload replay / different-payload 409 contract.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from tests.integration.conftest import CANONICAL_REQUEST, auth
from tests.integration.test_api_flow import _count

CONCURRENCY = 6


def _post(client: TestClient, *, key: str, request: dict[str, object]) -> tuple[int, dict]:
    response = client.post(
        "/v1/investigations",
        headers={**auth("operator_alpha"), "Idempotency-Key": key},
        json=request,
    )
    return response.status_code, response.json()


@pytest.mark.integration
def test_concurrent_same_key_same_payload_is_single_run(client: TestClient) -> None:
    key = "concurrent-same-payload"
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        futures = [
            pool.submit(_post, client, key=key, request=CANONICAL_REQUEST)
            for _ in range(CONCURRENCY)
        ]
        outcomes = [future.result() for future in futures]

    statuses = [status for status, _ in outcomes]
    run_ids = {body["run_id"] for _, body in outcomes}

    assert statuses.count(500) == 0, statuses
    assert statuses.count(201) == 1, statuses
    assert statuses.count(200) == CONCURRENCY - 1, statuses
    assert len(run_ids) == 1, run_ids

    run_id = UUID(next(iter(run_ids)))
    assert _count("investigation_run") == 1
    assert _count("investigation_run", "run_id = %s", (run_id,)) == 1
    for tool_name in ("T1_inventory", "T2_sales_demand", "T3_supplier", "reasoning"):
        assert (
            _count(
                "tool_invocation",
                "run_id = %s AND tool_name = %s",
                (run_id, tool_name),
            )
            == 1
        ), tool_name


@pytest.mark.integration
def test_concurrent_same_key_different_payload_conflicts_without_duplication(
    client: TestClient,
) -> None:
    key = "concurrent-different-payload"
    payload_a = CANONICAL_REQUEST
    # A different but still fixture-valid as_of_ts: this changes the payload
    # hash (and hence which side is treated as the "different payload")
    # without either side failing evidence freshness checks, so whichever
    # request wins the race is guaranteed to reach reasoning.
    payload_b = {**CANONICAL_REQUEST, "as_of_ts": "2026-08-10T12:01:00Z"}

    with ThreadPoolExecutor(max_workers=2) as pool:
        future_a = pool.submit(_post, client, key=key, request=payload_a)
        future_b = pool.submit(_post, client, key=key, request=payload_b)
        outcomes = [future_a.result(), future_b.result()]

    statuses = [status for status, _ in outcomes]
    assert statuses.count(500) == 0, statuses
    assert statuses.count(201) == 1, statuses
    assert statuses.count(409) == 1, statuses

    conflict_body = next(body for status, body in outcomes if status == 409)
    assert conflict_body["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"

    accepted_body = next(body for status, body in outcomes if status == 201)
    run_id = UUID(accepted_body["run_id"])

    assert _count("investigation_run") == 1
    assert _count("tool_invocation", "run_id = %s AND tool_name = 'reasoning'", (run_id,)) == 1

    audit = client.get(
        f"/v1/investigations/{run_id}/audit",
        headers=auth("operator_alpha"),
    )
    assert any(
        event["event_type"] == "intake_rejected"
        and event["payload"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"
        for event in audit.json()["events"]
    )
