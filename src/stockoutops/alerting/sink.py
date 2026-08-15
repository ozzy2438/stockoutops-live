"""Outbound alert sink boundary.

Default implementation is disabled and performs no network I/O. An optional
HTTPS webhook adapter may be injected when explicitly enabled; that adapter is
a local/CI engineering candidate and is not a live/staging delivery proof.
"""

from __future__ import annotations

from typing import Protocol

from stockoutops.alerting.contracts import AlertEvaluation
from stockoutops.alerting.delivery_settings import AlertDeliverySettings
from stockoutops.database import Database
from stockoutops.identity import Principal


class AlertSink(Protocol):
    def deliver(self, principal: Principal, evaluation: AlertEvaluation) -> None: ...


class DisabledAlertSink:
    """Explicit no-op sink used when delivery is disabled (the default)."""

    def deliver(self, principal: Principal, evaluation: AlertEvaluation) -> None:
        return


def build_alert_sink(database: Database, settings: AlertDeliverySettings) -> AlertSink:
    if not settings.enabled:
        return DisabledAlertSink()
    from stockoutops.alerting.delivery import AlertDeliveryRepository
    from stockoutops.alerting.webhook import HttpsWebhookSink

    return HttpsWebhookSink(AlertDeliveryRepository(database), settings)
