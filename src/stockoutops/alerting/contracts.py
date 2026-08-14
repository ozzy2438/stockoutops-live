"""Typed contracts for deterministic shadow alert-policy evaluation."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Severity = Literal["SEV1", "SEV2", "SEV3"]
AlertState = Literal["OK", "FIRING", "RESOLVED"]
MeasurementStatus = Literal["EVALUATED", "UNMEASURED"]
ThresholdClassification = Literal["TARGET", "ENGINEERING TEST THRESHOLD"]
EvidenceLabel = Literal["SIMULATED", "MEASURED"]
MetricName = Literal[
    "external_action_count",
    "escalation_disagreement_rate",
    "missing_required_evidence_count",
    "unsupported_claim_count",
    "shadow_processing_error_rate",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AlertCorrelation(StrictModel):
    tenant_id: str = Field(min_length=1, max_length=100)
    run_id: str | None = Field(default=None, min_length=1, max_length=100)
    case_id: str | None = Field(default=None, min_length=1, max_length=100)


class AlertMetricSnapshot(StrictModel):
    """One tenant-scoped, execute-false shadow report window."""

    correlation: AlertCorrelation
    window_id: str = Field(min_length=1, max_length=200)
    source_report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_report_label: Literal["M2 SHADOW FOUNDATION — SIMULATED ENGINEERING REHEARSAL"]
    evidence_label: EvidenceLabel
    execute: Literal[False]
    case_count: int = Field(ge=0)
    escalation_disagreement_count: int | None = Field(default=None, ge=0)
    missing_required_evidence_count: int | None = Field(default=None, ge=0)
    unsupported_claim_count: int | None = Field(default=None, ge=0)
    external_action_count: int | None = Field(default=None, ge=0)
    shadow_processing_failure_count: int | None = Field(default=None, ge=0)
    deterministic_provider_latency_ms: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_counts_and_label(self) -> AlertMetricSnapshot:
        for field_name in (
            "escalation_disagreement_count",
            "shadow_processing_failure_count",
        ):
            value = getattr(self, field_name)
            if value is not None and value > self.case_count:
                raise ValueError(f"{field_name} cannot exceed case_count")
        if self.evidence_label != "SIMULATED":
            raise ValueError(
                "The M2-04 local foundation accepts only SIMULATED shadow-report evidence"
            )
        return self


class PolicyAssessment(StrictModel):
    policy_id: str
    policy_version: str
    metric_name: MetricName
    severity: Severity
    measurement_status: MeasurementStatus
    threshold_classification: ThresholdClassification
    threshold_value: float
    comparator: Literal[">"] = ">"
    window: str
    observed_value: float | None
    breached: bool | None

    @model_validator(mode="after")
    def validate_measurement(self) -> PolicyAssessment:
        measured = self.observed_value is not None and self.breached is not None
        if (self.measurement_status == "EVALUATED") != measured:
            raise ValueError("EVALUATED requires an observed value and breach result")
        return self


class AlertEvaluation(StrictModel):
    evaluation_id: int = Field(ge=1)
    alert_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_id: str
    policy_version: str
    metric_name: MetricName
    tenant_id: str
    correlation: AlertCorrelation
    severity: Severity
    state: AlertState | None
    previous_state: AlertState | None
    transition: Literal[
        "INITIAL_OK",
        "FIRED",
        "STILL_FIRING",
        "RESOLVED",
        "STILL_OK",
        "UNMEASURED",
    ]
    measurement_status: MeasurementStatus
    threshold_classification: ThresholdClassification
    threshold_value: float
    comparator: Literal[">"]
    observed_value: float | None
    window: str
    window_id: str
    evidence_label: EvidenceLabel
    source_report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    payload_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str
    live_slo_evidence_eligible: Literal[False]
    execute: Literal[False]
    external_alert_delivery_count: Literal[0]
    actor_id: str
    evaluated_at: datetime
    idempotent_replay: bool = False


class UnwiredSignal(StrictModel):
    signal: str
    status: Literal["UNWIRED", "UNMEASURED", "FUTURE"]
    reason: str
