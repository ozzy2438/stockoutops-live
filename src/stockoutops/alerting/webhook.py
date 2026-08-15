"""Provider-neutral HTTPS webhook transport. Disabled-by-default; local/CI only.

The transport performs the HTTP request only. Durability, leasing, retry, and
evidence belong to the outbox worker, so no network call is ever made inside a
database transaction.
"""

from __future__ import annotations

from typing import Any

import httpx

from stockoutops.alerting.contracts import AlertEvaluation
from stockoutops.alerting.delivery_settings import AlertDeliverySettings

RETRYABLE_ERROR_CLASSES = frozenset({"timeout", "connection_error", "transport_error"})
AMBIGUOUS_ERROR_CLASSES = frozenset({"timeout"})


def webhook_payload(evaluation: AlertEvaluation) -> dict[str, Any]:
    return {
        "alert_fingerprint": evaluation.alert_fingerprint,
        "comparator": evaluation.comparator,
        "correlation": evaluation.correlation.model_dump(mode="json"),
        "evaluated_at": evaluation.evaluated_at.isoformat(),
        "evaluation_id": evaluation.evaluation_id,
        "evidence_label": evaluation.evidence_label,
        "execute": evaluation.execute,
        "idempotency_key": evaluation.idempotency_key,
        "live_slo_evidence_eligible": evaluation.live_slo_evidence_eligible,
        "measurement_status": evaluation.measurement_status,
        "metric_name": evaluation.metric_name,
        "observed_value": evaluation.observed_value,
        "payload_hash": evaluation.payload_hash,
        "policy_id": evaluation.policy_id,
        "policy_version": evaluation.policy_version,
        "previous_state": evaluation.previous_state,
        "severity": evaluation.severity,
        "state": evaluation.state,
        "tenant_id": evaluation.tenant_id,
        "threshold_classification": evaluation.threshold_classification,
        "threshold_value": evaluation.threshold_value,
        "transition": evaluation.transition,
        "window": evaluation.window,
        "window_id": evaluation.window_id,
    }


def classify_transport_error(exc: BaseException) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.ConnectError):
        return "connection_error"
    return "transport_error"


class WebhookTransport:
    """Single bounded HTTP POST. No retry, no persistence, no transaction."""

    def __init__(
        self,
        settings: AlertDeliverySettings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        settings.validate()
        if settings.webhook_url is None:
            raise ValueError("WebhookTransport requires a configured webhook URL")
        self.settings = settings
        self.transport = transport

    @property
    def webhook_url(self) -> str:
        assert self.settings.webhook_url is not None
        return self.settings.webhook_url

    def post(self, payload: dict[str, Any], *, idempotency_key: str) -> int:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Idempotency-Key": idempotency_key,
        }
        if self.settings.token:
            headers["Authorization"] = f"Bearer {self.settings.token}"
        with httpx.Client(
            timeout=self.settings.timeout_seconds,
            follow_redirects=False,
            transport=self.transport,
        ) as client:
            response = client.post(self.webhook_url, json=payload, headers=headers)
        return response.status_code
