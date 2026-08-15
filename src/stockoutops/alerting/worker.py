"""Leased alert-outbox delivery worker.

Every HTTP request happens strictly outside a database transaction. The worker
leases work, sends, then records the outcome in a separate transaction.

Delivery is durable at-least-once processing. A timeout is treated as an
*ambiguous* outcome: the receiver may have accepted the request. The worker
retries it under a stable `Idempotency-Key`, so suppressing the duplicate is the
receiver's documented responsibility (ADR-0009).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from stockoutops.alerting.delivery_settings import AlertDeliverySettings
from stockoutops.alerting.outbox import (
    DEFAULT_LEASE_SECONDS,
    AlertOutboxRepository,
    LeasedDelivery,
)
from stockoutops.alerting.webhook import (
    AMBIGUOUS_ERROR_CLASSES,
    RETRYABLE_ERROR_CLASSES,
    WebhookTransport,
    classify_transport_error,
)
from stockoutops.errors import ConflictError


@dataclass(frozen=True)
class WorkerRunResult:
    leased: int = 0
    delivered: int = 0
    retried: int = 0
    dead_lettered: int = 0
    lease_lost: int = 0

    def merged(self, other: WorkerRunResult) -> WorkerRunResult:
        return WorkerRunResult(
            leased=self.leased + other.leased,
            delivered=self.delivered + other.delivered,
            retried=self.retried + other.retried,
            dead_lettered=self.dead_lettered + other.dead_lettered,
            lease_lost=self.lease_lost + other.lease_lost,
        )


@dataclass(frozen=True)
class AttemptOutcomeDecision:
    outcome: str
    http_status: int | None
    error_class: str | None
    retryable: bool


def classify_response(status_code: int) -> AttemptOutcomeDecision:
    if 200 <= status_code < 300:
        return AttemptOutcomeDecision("DELIVERED", status_code, None, retryable=False)
    if status_code >= 500:
        return AttemptOutcomeDecision(
            "RETRYABLE_FAILURE", status_code, f"http_{status_code}", retryable=True
        )
    return AttemptOutcomeDecision(
        "PERMANENT_FAILURE", status_code, f"http_{status_code}", retryable=False
    )


def classify_exception(exc: BaseException) -> AttemptOutcomeDecision:
    error_class = classify_transport_error(exc)
    if error_class in AMBIGUOUS_ERROR_CLASSES:
        # The request may have reached the receiver. Never record this as a
        # failure that suppresses redelivery.
        return AttemptOutcomeDecision("AMBIGUOUS", None, error_class, retryable=True)
    if error_class in RETRYABLE_ERROR_CLASSES:
        return AttemptOutcomeDecision("RETRYABLE_FAILURE", None, error_class, retryable=True)
    return AttemptOutcomeDecision("PERMANENT_FAILURE", None, error_class, retryable=False)


class AlertOutboxWorker:
    def __init__(
        self,
        repository: AlertOutboxRepository,
        transport: WebhookTransport,
        *,
        worker_id: str,
        clock: Callable[[], datetime] | None = None,
        lease_seconds: float = DEFAULT_LEASE_SECONDS,
    ) -> None:
        if not worker_id:
            raise ValueError("worker_id is required")
        self.repository = repository
        self.transport = transport
        self.worker_id = worker_id
        self.clock = clock or (lambda: datetime.now(UTC))
        self.lease_seconds = lease_seconds

    def run_once(self, *, batch_size: int = 10) -> WorkerRunResult:
        leased = self.repository.lease(
            worker_id=self.worker_id,
            now=self.clock(),
            lease_seconds=self.lease_seconds,
            batch_size=batch_size,
        )
        result = WorkerRunResult(leased=len(leased))
        for item in leased:
            result = result.merged(self._process(item))
        return result

    def _process(self, leased: LeasedDelivery) -> WorkerRunResult:
        started_at = self.clock()
        # --- no transaction is open across this call ---
        try:
            status_code = self.transport.post(
                leased.payload, idempotency_key=leased.idempotency_key
            )
        except httpx.HTTPError as exc:
            decision = classify_exception(exc)
        except Exception as exc:
            decision = classify_exception(exc)
        else:
            decision = classify_response(status_code)
        completed_at = self.clock()

        try:
            if decision.outcome == "DELIVERED":
                assert decision.http_status is not None
                self.repository.record_delivered(
                    leased,
                    http_status=decision.http_status,
                    started_at=started_at,
                    completed_at=completed_at,
                )
                return WorkerRunResult(delivered=1)

            error_class = decision.error_class or "unknown_error"
            if decision.retryable and not leased.is_final_attempt:
                self.repository.record_retry(
                    leased,
                    outcome=decision.outcome,  # type: ignore[arg-type]
                    http_status=decision.http_status,
                    error_class=error_class,
                    started_at=started_at,
                    completed_at=completed_at,
                )
                return WorkerRunResult(retried=1)

            self.repository.record_dead_letter(
                leased,
                outcome=decision.outcome,  # type: ignore[arg-type]
                http_status=decision.http_status,
                error_class=error_class,
                started_at=started_at,
                completed_at=completed_at,
            )
            return WorkerRunResult(dead_lettered=1)
        except ConflictError as exc:
            if exc.code == "OUTBOX_LEASE_LOST":
                # Another worker took the expired lease. Leave its progress alone.
                return WorkerRunResult(lease_lost=1)
            raise


def build_worker(
    repository: AlertOutboxRepository,
    settings: AlertDeliverySettings,
    *,
    worker_id: str,
    clock: Callable[[], datetime] | None = None,
    lease_seconds: float = DEFAULT_LEASE_SECONDS,
    transport: httpx.BaseTransport | None = None,
) -> AlertOutboxWorker:
    if not settings.enabled:
        raise ValueError("Alert outbox worker requires enabled delivery settings")
    return AlertOutboxWorker(
        repository,
        WebhookTransport(settings, transport=transport),
        worker_id=worker_id,
        clock=clock,
        lease_seconds=lease_seconds,
    )
