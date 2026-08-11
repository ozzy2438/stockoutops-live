"""Real-PostgreSQL concurrency regressions for the F-1 idempotent-intake race.

Two generations of the same bug class:

1. `begin_intake`'s original SELECT ... FOR UPDATE only locked an *existing*
   idempotency_key row; a brand-new key had no row to lock, so two
   concurrent requests both reached INSERT and the loser raised an
   unhandled psycopg.errors.UniqueViolation (HTTP 500) instead of the
   documented same-payload replay / different-payload 409 contract.
2. Closing that race exposed a deeper one: concurrent duplicate callers
   each resume the same run, so a loser could time out a fixed poll for a
   peer's in-flight T1-3/reasoning call and falsely escalate a run whose
   one true attempt was still succeeding (or misreport a genuine failure
   as a generic retry-forbidden instead of the true provider error). Fixed
   by replacing the poll with a Postgres session advisory lock per
   (run_id, tool_name): a loser blocks for exactly as long as the true
   owner's call takes, with no fixed timeout to race against.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from stockoutops.reasoning.base import ReasoningFailure
from stockoutops.reasoning.deterministic_stub import DeterministicStubAdapter
from stockoutops.service import InvestigationService
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


def _audit_replay_matches(client: TestClient, run_id: str, expected_state: str) -> None:
    audit = client.get(f"/v1/investigations/{run_id}/audit", headers=auth("operator_alpha"))
    body = audit.json()
    assert body["current_state"] == body["replayed_state"] == expected_state, body


class DelayedSuccessAdapter:
    """Wraps the deterministic stub but sleeps first, standing in for a
    slow-but-successful live reasoning call within the accepted up-to-30s
    bound — long enough to outlast any fixed poll/timeout a naive
    duplicate-caller reconciliation might use."""

    model_id = DeterministicStubAdapter.model_id

    def __init__(self, delay_seconds: float) -> None:
        self._delay = delay_seconds
        self._inner = DeterministicStubAdapter()
        self._lock = threading.Lock()
        self.call_count = 0

    def reason(self, evidence):
        with self._lock:
            self.call_count += 1
        time.sleep(self._delay)
        return self._inner.reason(evidence)


class DelayedFailureAdapter:
    """Simulates a slow provider call that ultimately fails, standing in
    for a genuine upstream error (not a duplicate-caller artifact)."""

    def __init__(self, delay_seconds: float, *, code: str, message: str) -> None:
        self._delay = delay_seconds
        self._code = code
        self._message = message
        self._lock = threading.Lock()
        self.call_count = 0

    def reason(self, evidence):
        with self._lock:
            self.call_count += 1
        time.sleep(self._delay)
        raise ReasoningFailure(self._code, self._message)


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

    # Every response, not just the 201, must reflect the one true final
    # accepted state - a duplicate must never observe a corrupted view.
    states = {body["state"] for _, body in outcomes}
    assert states == {"awaiting_human"}, outcomes

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

    _audit_replay_matches(client, str(run_id), "awaiting_human")


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
    # The accepted run's own state must not be corrupted by the loser.
    assert accepted_body["state"] == "awaiting_human", accepted_body
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
    _audit_replay_matches(client, str(run_id), "awaiting_human")


@pytest.mark.integration
def test_concurrent_same_payload_survives_slow_reasoning_without_false_escalation(
    client: TestClient, service: InvestigationService
) -> None:
    """The exact case Fizz's re-review found: a duplicate caller must not
    time out waiting on a peer's in-flight reasoning call and falsely
    escalate a run whose one true attempt is still succeeding. The delay
    here (2s) is well beyond the old fixed ~1s poll budget, standing in for
    a live call within the accepted up-to-30s bound."""
    adapter = DelayedSuccessAdapter(2.0)
    service.reasoning = adapter
    key = "concurrent-slow-success"

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(_post, client, key=key, request=CANONICAL_REQUEST) for _ in range(3)]
        outcomes = [future.result() for future in futures]

    statuses = [status for status, _ in outcomes]
    assert statuses.count(500) == 0, statuses
    assert statuses.count(201) == 1, statuses
    assert statuses.count(200) == 2, statuses

    run_ids = {body["run_id"] for _, body in outcomes}
    assert len(run_ids) == 1, outcomes
    run_id = UUID(next(iter(run_ids)))

    states = {body["state"] for _, body in outcomes}
    assert states == {"awaiting_human"}, outcomes

    assert adapter.call_count == 1, "the true provider must be invoked exactly once, never retried"
    assert _count("investigation_run") == 1
    for tool_name in ("T1_inventory", "T2_sales_demand", "T3_supplier", "reasoning"):
        assert (
            _count("tool_invocation", "run_id = %s AND tool_name = %s", (run_id, tool_name)) == 1
        ), tool_name

    audit = client.get(f"/v1/investigations/{run_id}/audit", headers=auth("operator_alpha"))
    body = audit.json()
    assert body["current_state"] == body["replayed_state"] == "awaiting_human"
    assert not any(event["event_type"] == "run_escalated" for event in body["events"])


@pytest.mark.integration
def test_concurrent_duplicate_reflects_true_slow_provider_failure(
    client: TestClient, service: InvestigationService
) -> None:
    """A slow provider call that genuinely fails must still be attempted
    exactly once, and every duplicate caller's view of the outcome must
    carry the true originating failure code - never a duplicate-induced
    generic REASONING_RETRY_FORBIDDEN that misrepresents what happened."""
    adapter = DelayedFailureAdapter(
        1.0, code="PROVIDER_TIMEOUT", message="Simulated slow provider timeout"
    )
    service.reasoning = adapter
    key = "concurrent-slow-failure"

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(_post, client, key=key, request=CANONICAL_REQUEST) for _ in range(3)]
        outcomes = [future.result() for future in futures]

    statuses = [status for status, _ in outcomes]
    assert statuses.count(500) == 0, statuses
    assert statuses.count(201) == 1, statuses
    assert statuses.count(200) == 2, statuses

    run_ids = {body["run_id"] for _, body in outcomes}
    assert len(run_ids) == 1, outcomes
    run_id = UUID(next(iter(run_ids)))

    states = {body["state"] for _, body in outcomes}
    assert states == {"escalated"}, outcomes

    assert adapter.call_count == 1, "exactly one true provider attempt, zero retries"

    audit = client.get(f"/v1/investigations/{run_id}/audit", headers=auth("operator_alpha"))
    body = audit.json()
    assert body["current_state"] == body["replayed_state"] == "escalated"
    escalations = [event for event in body["events"] if event["event_type"] == "run_escalated"]
    assert len(escalations) == 1, escalations
    assert escalations[0]["payload"]["code"] == "PROVIDER_TIMEOUT", escalations

    assert _count("tool_invocation", "run_id = %s AND tool_name = 'reasoning'", (run_id,)) == 1
    assert (
        _count(
            "tool_invocation",
            "run_id = %s AND tool_name = 'reasoning' AND status = 'failed'",
            (run_id,),
        )
        == 1
    )
