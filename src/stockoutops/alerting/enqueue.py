"""Transactional bridge from an alert evaluation to a durable outbox intent."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from psycopg import Connection

from stockoutops.alerting.contracts import AlertEvaluation
from stockoutops.alerting.delivery import should_notify
from stockoutops.alerting.delivery_settings import AlertDeliverySettings, destination_host
from stockoutops.alerting.outbox import DEFAULT_MAX_ATTEMPTS, AlertOutboxRepository
from stockoutops.alerting.webhook import webhook_payload
from stockoutops.evidence.provenance import canonical_hash


class DeliveryEnqueuer(Protocol):
    def enqueue(
        self,
        connection: Connection[dict[str, Any]],
        evaluation: AlertEvaluation,
        *,
        enqueued_at: datetime,
    ) -> int | None: ...


class WebhookOutboxEnqueuer:
    """Enqueue FIRED/RESOLVED lifecycle notifications for durable delivery.

    Runs inside the caller's alert-evaluation transaction so the intent is as
    durable as the evidence. Performs no network I/O.
    """

    def __init__(
        self,
        settings: AlertDeliverySettings,
        *,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> None:
        settings.validate()
        if not settings.enabled or settings.webhook_url is None:
            raise ValueError("WebhookOutboxEnqueuer requires enabled delivery settings")
        self.settings = settings
        self.destination_host = destination_host(settings.webhook_url)
        self.max_attempts = max_attempts

    def enqueue(
        self,
        connection: Connection[dict[str, Any]],
        evaluation: AlertEvaluation,
        *,
        enqueued_at: datetime,
    ) -> int | None:
        if not should_notify(evaluation):
            return None
        payload = webhook_payload(evaluation)
        return AlertOutboxRepository.enqueue_in_transaction(
            connection,
            tenant_id=evaluation.tenant_id,
            evaluation_id=evaluation.evaluation_id,
            alert_fingerprint=evaluation.alert_fingerprint,
            transition=evaluation.transition,
            destination_host=self.destination_host,
            payload=payload,
            payload_hash=canonical_hash(payload),
            enqueued_at=enqueued_at,
            max_attempts=self.max_attempts,
        )


def build_delivery_enqueuer(
    settings: AlertDeliverySettings,
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> DeliveryEnqueuer | None:
    """Return None when delivery is disabled (the default)."""

    if not settings.enabled:
        return None
    return WebhookOutboxEnqueuer(settings, max_attempts=max_attempts)
