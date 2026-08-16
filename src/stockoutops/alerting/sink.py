"""Outbound alert sink boundary.

Delivery no longer happens on the evaluation call path. A durable outbox intent
is enqueued inside the evaluation transaction (`alerting.enqueue`) and a leased
worker (`alerting.worker`) performs HTTP outside any transaction, so a crash
between claim and send cannot drop a notification.

The sink boundary is retained for non-delivery observers and is a no-op by
default. It must never perform network I/O on the evaluation path.
"""

from __future__ import annotations

from typing import Protocol

from stockoutops.alerting.contracts import AlertEvaluation
from stockoutops.identity import Principal


class AlertSink(Protocol):
    def deliver(self, principal: Principal, evaluation: AlertEvaluation) -> None: ...


class DisabledAlertSink:
    """Explicit no-op sink. The default on every path."""

    def deliver(self, principal: Principal, evaluation: AlertEvaluation) -> None:
        return


def build_alert_sink() -> AlertSink:
    """Always the no-op sink; outbound delivery is the outbox worker's job."""

    return DisabledAlertSink()
