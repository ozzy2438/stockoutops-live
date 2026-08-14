"""Boundary for a future owner-authorised external alert sink.

No sink implementation is included in the M2-04 local engineering foundation.
"""

from __future__ import annotations

from typing import Protocol

from stockoutops.alerting.contracts import AlertEvaluation


class AlertSink(Protocol):
    def deliver(self, evaluation: AlertEvaluation) -> None: ...
