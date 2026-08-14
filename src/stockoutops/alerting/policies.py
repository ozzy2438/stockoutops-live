"""Frozen deterministic policies supported by current M2 shadow evidence."""

from __future__ import annotations

from dataclasses import dataclass

from stockoutops.alerting.contracts import (
    AlertMetricSnapshot,
    MetricName,
    PolicyAssessment,
    Severity,
    ThresholdClassification,
    UnwiredSignal,
)

POLICY_VERSION = "m2-alert-policy-v1"


@dataclass(frozen=True)
class AlertPolicy:
    policy_id: str
    metric_name: MetricName
    severity: Severity
    threshold_value: float
    threshold_classification: ThresholdClassification
    window: str

    def observe(self, snapshot: AlertMetricSnapshot) -> float | None:
        if self.metric_name == "external_action_count":
            value = snapshot.external_action_count
        elif self.metric_name == "escalation_disagreement_rate":
            if snapshot.case_count == 0 or snapshot.escalation_disagreement_count is None:
                return None
            value = snapshot.escalation_disagreement_count / snapshot.case_count
        elif self.metric_name == "missing_required_evidence_count":
            value = snapshot.missing_required_evidence_count
        elif self.metric_name == "unsupported_claim_count":
            value = snapshot.unsupported_claim_count
        elif self.metric_name == "shadow_processing_error_rate":
            if snapshot.case_count == 0 or snapshot.shadow_processing_failure_count is None:
                return None
            value = snapshot.shadow_processing_failure_count / snapshot.case_count
        else:  # pragma: no cover - MetricName and the frozen table make this unreachable.
            raise AssertionError(f"Unsupported alert metric: {self.metric_name}")
        return float(value) if value is not None else None

    def assess(self, snapshot: AlertMetricSnapshot) -> PolicyAssessment:
        observed = self.observe(snapshot)
        return PolicyAssessment(
            policy_id=self.policy_id,
            policy_version=POLICY_VERSION,
            metric_name=self.metric_name,
            severity=self.severity,
            measurement_status="EVALUATED" if observed is not None else "UNMEASURED",
            threshold_classification=self.threshold_classification,
            threshold_value=self.threshold_value,
            comparator=">",
            window=self.window,
            observed_value=observed,
            breached=observed > self.threshold_value if observed is not None else None,
        )


POLICIES: tuple[AlertPolicy, ...] = (
    AlertPolicy(
        policy_id="shadow-external-action-safety",
        metric_name="external_action_count",
        severity="SEV1",
        threshold_value=0,
        threshold_classification="TARGET",
        window="one tenant-scoped shadow report batch",
    ),
    AlertPolicy(
        policy_id="shadow-escalation-disagreement-rate",
        metric_name="escalation_disagreement_rate",
        severity="SEV2",
        threshold_value=0.20,
        threshold_classification="ENGINEERING TEST THRESHOLD",
        window="one tenant-scoped shadow report batch",
    ),
    AlertPolicy(
        policy_id="shadow-missing-required-evidence",
        metric_name="missing_required_evidence_count",
        severity="SEV3",
        threshold_value=0,
        threshold_classification="TARGET",
        window="one tenant-scoped shadow report batch",
    ),
    AlertPolicy(
        policy_id="shadow-unsupported-claim",
        metric_name="unsupported_claim_count",
        severity="SEV3",
        threshold_value=0,
        threshold_classification="TARGET",
        window="one tenant-scoped shadow report batch",
    ),
    AlertPolicy(
        policy_id="shadow-processing-error-rate",
        metric_name="shadow_processing_error_rate",
        severity="SEV3",
        threshold_value=0.05,
        threshold_classification="ENGINEERING TEST THRESHOLD",
        window="one tenant-scoped shadow report batch",
    ),
)

UNWIRED_SIGNALS: tuple[UnwiredSignal, ...] = (
    UnwiredSignal(
        signal="deterministic_provider_latency",
        status="UNMEASURED",
        reason="Current latency is SIMULATED deterministic-provider metadata, not a live SLI.",
    ),
    UnwiredSignal(
        signal="production_availability",
        status="FUTURE",
        reason="No production environment or availability measurement exists.",
    ),
    UnwiredSignal(
        signal="rls_leakage",
        status="UNWIRED",
        reason="The local application boundary is not production PostgreSQL RLS.",
    ),
    UnwiredSignal(
        signal="unauthorised_access",
        status="UNWIRED",
        reason="No production IdP or production access telemetry exists.",
    ),
    UnwiredSignal(
        signal="cost_per_investigation",
        status="UNMEASURED",
        reason="The accepted cost-allocation method and live AWS/model telemetry do not exist.",
    ),
    UnwiredSignal(
        signal="live_llm_provider_failure",
        status="FUTURE",
        reason="The deterministic CI provider makes no live model request.",
    ),
    UnwiredSignal(
        signal="external_alert_delivery",
        status="UNWIRED",
        reason="CloudWatch/SNS/email/chat/paging adapters are intentionally absent.",
    ),
)


def assess_policies(snapshot: AlertMetricSnapshot) -> list[PolicyAssessment]:
    return [policy.assess(snapshot) for policy in POLICIES]
