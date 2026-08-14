"""Deterministic control service for alert evaluation; it never delivers alerts."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from stockoutops.alerting.contracts import AlertEvaluation, AlertMetricSnapshot
from stockoutops.alerting.policies import assess_policies
from stockoutops.alerting.repository import AlertRepository
from stockoutops.errors import AuthorizationError, ConflictError, NotFoundError
from stockoutops.identity import Principal


class AlertService:
    def __init__(
        self,
        repository: AlertRepository,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(UTC))

    def evaluate(
        self,
        principal: Principal,
        snapshot: AlertMetricSnapshot,
        *,
        idempotency_prefix: str,
    ) -> list[AlertEvaluation]:
        if not principal.has_role("operator"):
            raise AuthorizationError("Alert evaluation requires the operator role")
        if snapshot.correlation.tenant_id != principal.tenant_id:
            raise NotFoundError()

        results: list[AlertEvaluation] = []
        for assessment in assess_policies(snapshot):
            evaluation = self.repository.record(
                principal,
                snapshot,
                assessment,
                idempotency_key=f"{idempotency_prefix}:{assessment.policy_id}",
                evaluated_at=self.clock(),
            )
            results.append(evaluation)
            if (
                assessment.policy_id == "shadow-external-action-safety"
                and evaluation.state == "FIRING"
            ):
                raise ConflictError(
                    "SHADOW_EXTERNAL_ACTION_DETECTED",
                    "Shadow external_action_count exceeded zero; evaluation failed closed",
                )
        return results
