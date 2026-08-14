"""Provider-neutral HTTPS webhook AlertSink. Disabled-by-default; local/CI only."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx

from stockoutops.alerting.contracts import AlertEvaluation
from stockoutops.alerting.delivery import AlertDeliveryRepository, should_notify
from stockoutops.alerting.delivery_settings import AlertDeliverySettings, destination_host
from stockoutops.evidence.provenance import canonical_hash
from stockoutops.identity import Principal

RETRYABLE_ERROR_CLASSES = frozenset({"timeout", "connection_error", "transport_error"})


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


def delivery_idempotency_key(evaluation: AlertEvaluation) -> str:
    return f"{evaluation.tenant_id}:{evaluation.evaluation_id}:{evaluation.transition}"


def classify_transport_error(exc: BaseException) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.ConnectError):
        return "connection_error"
    return "transport_error"


class HttpsWebhookSink:
    def __init__(
        self,
        repository: AlertDeliveryRepository,
        settings: AlertDeliverySettings,
        *,
        clock: Callable[[], datetime] | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not settings.enabled:
            raise ValueError("HttpsWebhookSink requires enabled delivery settings")
        settings.validate()
        self.repository = repository
        self.settings = settings
        self.clock = clock or (lambda: datetime.now(UTC))
        self.transport = transport

    def deliver(self, principal: Principal, evaluation: AlertEvaluation) -> None:
        if evaluation.tenant_id != principal.tenant_id:
            return
        if not should_notify(evaluation):
            return
        webhook_url = self.settings.webhook_url
        if webhook_url is None:
            return
        payload = webhook_payload(evaluation)
        claimed = self.repository.claim(
            principal,
            evaluation,
            destination_host=destination_host(webhook_url),
            payload_hash=canonical_hash(payload),
            claimed_at=self.clock(),
        )
        if not claimed:
            return
        http_status: int | None = None
        error_class: str | None = None
        attempt_count = 0
        delivered = False
        for attempt_count in range(1, self.settings.max_attempts + 1):
            try:
                http_status = self._post(webhook_url, evaluation, payload)
            except httpx.HTTPError as exc:
                http_status = None
                error_class = classify_transport_error(exc)
                if (
                    error_class not in RETRYABLE_ERROR_CLASSES
                    or attempt_count >= self.settings.max_attempts
                ):
                    break
                continue
            except Exception:
                http_status = None
                error_class = "transport_error"
                break
            if 200 <= http_status < 300:
                delivered = True
                error_class = None
                break
            error_class = f"http_{http_status}"
            if http_status < 500 or attempt_count >= self.settings.max_attempts:
                break
        self.repository.complete(
            principal,
            evaluation,
            status="DELIVERED" if delivered else "FAILED",
            attempt_count=attempt_count,
            http_status=http_status,
            error_class=error_class,
            completed_at=self.clock(),
        )

    def _post(self, webhook_url: str, evaluation: AlertEvaluation, payload: dict[str, Any]) -> int:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Idempotency-Key": delivery_idempotency_key(evaluation),
        }
        if self.settings.token:
            headers["Authorization"] = f"Bearer {self.settings.token}"
        with httpx.Client(
            timeout=self.settings.timeout_seconds,
            follow_redirects=False,
            transport=self.transport,
        ) as client:
            response = client.post(webhook_url, json=payload, headers=headers)
        return response.status_code
