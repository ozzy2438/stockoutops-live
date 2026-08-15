from __future__ import annotations

import pytest
from pydantic import ValidationError

from stockoutops.alerting.contracts import AlertCorrelation, AlertMetricSnapshot
from stockoutops.alerting.policies import POLICIES, UNWIRED_SIGNALS
from stockoutops.alerting.repository import alert_fingerprint


def _snapshot(**overrides) -> AlertMetricSnapshot:
    payload = {
        "correlation": AlertCorrelation(tenant_id="t_alpha"),
        "window_id": "window-001",
        "source_report_sha256": "a" * 64,
        "source_report_label": ("M2 SHADOW FOUNDATION — SIMULATED ENGINEERING REHEARSAL"),
        "evidence_label": "SIMULATED",
        "execute": False,
        "case_count": 10,
        "escalation_disagreement_count": 1,
        "missing_required_evidence_count": 0,
        "unsupported_claim_count": 0,
        "external_action_count": 0,
        "shadow_processing_failure_count": 0,
        "deterministic_provider_latency_ms": 4.0,
    }
    payload.update(overrides)
    return AlertMetricSnapshot(**payload)


def _policy(policy_id: str):
    return next(item for item in POLICIES if item.policy_id == policy_id)


@pytest.mark.parametrize(
    ("count", "breached"),
    [(1, False), (2, False), (3, True)],
)
def test_threshold_boundary_is_strictly_above(count: int, breached: bool) -> None:
    assessment = _policy("shadow-escalation-disagreement-rate").assess(
        _snapshot(escalation_disagreement_count=count)
    )
    assert assessment.observed_value == count / 10
    assert assessment.breached is breached
    assert assessment.threshold_value == 0.20
    assert assessment.threshold_classification == "ENGINEERING TEST THRESHOLD"


def test_policy_severity_and_threshold_classification_are_frozen() -> None:
    assert [
        (item.policy_id, item.severity, item.threshold_classification) for item in POLICIES
    ] == [
        ("shadow-external-action-safety", "SEV1", "TARGET"),
        (
            "shadow-escalation-disagreement-rate",
            "SEV2",
            "ENGINEERING TEST THRESHOLD",
        ),
        ("shadow-missing-required-evidence", "SEV3", "TARGET"),
        ("shadow-unsupported-claim", "SEV3", "TARGET"),
        ("shadow-processing-error-rate", "SEV3", "ENGINEERING TEST THRESHOLD"),
    ]


def test_fingerprint_is_stable_across_windows_but_tenant_scoped() -> None:
    policy = _policy("shadow-unsupported-claim").assess(_snapshot())
    first = alert_fingerprint(_snapshot(), policy)
    later = _snapshot(window_id="window-002", source_report_sha256="b" * 64)
    assert alert_fingerprint(later, policy) == first
    beta = _snapshot(correlation=AlertCorrelation(tenant_id="t_beta"))
    assert alert_fingerprint(beta, policy) != first


def test_missing_metric_is_unmeasured_not_a_silent_pass() -> None:
    assessment = _policy("shadow-processing-error-rate").assess(
        _snapshot(shadow_processing_failure_count=None)
    )
    assert assessment.measurement_status == "UNMEASURED"
    assert assessment.observed_value is None
    assert assessment.breached is None


def test_simulated_contract_cannot_be_relabelled_as_live_slo_evidence() -> None:
    with pytest.raises(ValidationError, match="accepts only SIMULATED"):
        _snapshot(evidence_label="MEASURED")
    statuses = {item.signal: item.status for item in UNWIRED_SIGNALS}
    assert statuses["external_alert_delivery"] == "UNWIRED"
    assert "disabled by default" in next(
        item.reason for item in UNWIRED_SIGNALS if item.signal == "external_alert_delivery"
    )
    assert statuses["production_availability"] == "FUTURE"
    assert statuses["deterministic_provider_latency"] == "UNMEASURED"
