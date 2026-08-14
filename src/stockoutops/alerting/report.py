"""Load simulated shadow evidence and render deterministic alert-foundation reports."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from stockoutops.alerting.contracts import AlertCorrelation, AlertEvaluation, AlertMetricSnapshot
from stockoutops.alerting.policies import POLICIES, UNWIRED_SIGNALS

SHADOW_REPORT_TITLE = "M2 SHADOW FOUNDATION — SIMULATED ENGINEERING REHEARSAL"
ALERT_REPORT_TITLE = "M2-04 SLO ALERT WIRING FOUNDATION — SIMULATED ENGINEERING REHEARSAL"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _items(value: object, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be an array")
    return value


def _integer(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


@dataclass(frozen=True)
class LoadedAlertSource:
    source_report_sha256: str
    source_shadow_git_sha: str
    case_pack_version: str
    snapshots: list[AlertMetricSnapshot]


def load_shadow_alert_source(path: Path) -> LoadedAlertSource:
    """Convert the existing simulated report into tenant-scoped metric snapshots."""

    payload = _mapping(json.loads(path.read_text(encoding="utf-8")), "shadow report")
    if payload.get("title") != SHADOW_REPORT_TITLE or payload.get("evidence_label") != "SIMULATED":
        raise ValueError("Alert pilot accepts only the labelled simulated M2 shadow report")
    controls = _mapping(payload.get("controls"), "controls")
    if controls.get("execute") is not False:
        raise ValueError("Shadow alert source must be hard-locked to execute=false")
    if controls.get("provider") != "deterministic-stub-v1":
        raise ValueError("Alert pilot accepts only deterministic-stub shadow evidence")

    pack = _mapping(payload.get("case_pack"), "case_pack")
    pack_version = str(pack.get("version", ""))
    generated_at = str(payload.get("generated_at", ""))
    source_hash = _sha256(path)
    per_tenant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case_item in _items(payload.get("cases"), "cases"):
        case = _mapping(case_item, "case")
        result = _mapping(case.get("result"), "case.result")
        tenant_id = str(result.get("tenant_id", ""))
        if not tenant_id:
            raise ValueError("Every shadow result requires tenant_id")
        per_tenant[tenant_id].append(result)
    if not per_tenant:
        raise ValueError("Shadow alert source requires at least one case result")

    snapshots: list[AlertMetricSnapshot] = []
    observed_external_actions = 0
    for tenant_id, results in sorted(per_tenant.items()):
        escalation_disagreements = 0
        missing_evidence = 0
        unsupported_claims = 0
        external_actions = 0
        latencies: list[float] = []
        for result in results:
            actual = _mapping(result.get("actual"), "result.actual")
            comparison = _mapping(result.get("comparison"), "result.comparison")
            if actual.get("execute") is not False:
                raise ValueError("Every shadow case must have execute=false")
            external_actions += _integer(
                actual.get("external_action_count"), "actual.external_action_count"
            )
            missing_evidence += _integer(
                comparison.get("missing_required_evidence_count"),
                "comparison.missing_required_evidence_count",
            )
            unsupported_claims += _integer(
                comparison.get("unsupported_citation_count"),
                "comparison.unsupported_citation_count",
            )
            latency = actual.get("latency_ms")
            if not isinstance(latency, (int, float)) or isinstance(latency, bool) or latency < 0:
                raise ValueError("actual.latency_ms must be a non-negative number")
            latencies.append(float(latency))
            escalation = next(
                (
                    _mapping(entry, "comparison entry")
                    for entry in _items(comparison.get("entries"), "comparison.entries")
                    if isinstance(entry, dict) and entry.get("field_name") == "escalated"
                ),
                None,
            )
            if escalation is None:
                raise ValueError("Every comparison requires an escalated field")
            escalation_disagreements += escalation.get("agreement") != "exact"

        observed_external_actions += external_actions
        snapshots.append(
            AlertMetricSnapshot(
                correlation=AlertCorrelation(tenant_id=tenant_id),
                window_id=f"{pack_version}:{generated_at}",
                source_report_sha256=source_hash,
                source_report_label=SHADOW_REPORT_TITLE,
                evidence_label="SIMULATED",
                execute=False,
                case_count=len(results),
                escalation_disagreement_count=escalation_disagreements,
                missing_required_evidence_count=missing_evidence,
                unsupported_claim_count=unsupported_claims,
                external_action_count=external_actions,
                shadow_processing_failure_count=None,
                deterministic_provider_latency_ms=sum(latencies) / len(latencies),
            )
        )

    if _integer(controls.get("external_action_count"), "controls.external_action_count") != (
        observed_external_actions
    ):
        raise ValueError("Aggregate and per-case external action counts disagree")
    return LoadedAlertSource(
        source_report_sha256=source_hash,
        source_shadow_git_sha=str(payload.get("exact_git_sha", "")),
        case_pack_version=pack_version,
        snapshots=snapshots,
    )


def build_alert_report(
    source: LoadedAlertSource,
    evaluations: list[AlertEvaluation],
    *,
    git_sha: str,
    generated_at: datetime,
) -> dict[str, object]:
    state_counts = Counter(item.state or "UNMEASURED" for item in evaluations)
    status_counts = Counter(item.measurement_status for item in evaluations)
    firing_by_severity = Counter(item.severity for item in evaluations if item.state == "FIRING")
    external_actions = sum(
        int(item.observed_value or 0)
        for item in evaluations
        if item.metric_name == "external_action_count"
    )
    return {
        "title": ALERT_REPORT_TITLE,
        "evidence_label": "SIMULATED",
        "claim_boundary": (
            "Local/CI policy-wiring engineering evidence only. This is not live alert "
            "delivery, production SLO attainment, an error budget, or M2/G1 exit evidence."
        ),
        "exact_git_sha": git_sha,
        "generated_at": generated_at.isoformat(),
        "source": {
            "shadow_report_sha256": source.source_report_sha256,
            "shadow_report_git_sha": source.source_shadow_git_sha,
            "case_pack_version": source.case_pack_version,
            "tenant_window_count": len(source.snapshots),
        },
        "controls": {
            "execute": False,
            "external_action_count": external_actions,
            "external_alert_delivery_count": 0,
            "live_slo_evidence_eligible": False,
            "provider": "deterministic-policy-evaluator-v1",
            "aws_resources_used": 0,
            "openai_calls": 0,
        },
        "summary": {
            "evaluation_count": len(evaluations),
            "idempotent_replay_count": sum(item.idempotent_replay for item in evaluations),
            "state_counts": dict(sorted(state_counts.items())),
            "measurement_status_counts": dict(sorted(status_counts.items())),
            "firing_by_severity": dict(sorted(firing_by_severity.items())),
        },
        "policies": [
            {
                "policy_id": policy.policy_id,
                "policy_version": "m2-alert-policy-v1",
                "metric_name": policy.metric_name,
                "severity": policy.severity,
                "comparator": ">",
                "threshold_value": policy.threshold_value,
                "threshold_classification": policy.threshold_classification,
                "window": policy.window,
            }
            for policy in POLICIES
        ],
        "evaluations": [item.model_dump(mode="json") for item in evaluations],
        "unwired_unmeasured_future_signals": [
            item.model_dump(mode="json") for item in UNWIRED_SIGNALS
        ],
        "limitations": [
            "The source is the 12-case controlled-synthetic deterministic rehearsal.",
            "Synthetic inputs are permanently ineligible as live SLO evidence in this schema.",
            "Shadow processing failures are UNMEASURED because the current successful report "
            "does not export an attempt/failure denominator.",
            "Deterministic-provider latency remains SIMULATED metadata without an alert rule.",
            "A local HTTPS webhook adapter exists but is disabled by default and "
            "is not a live/staging delivery proof.",
            "M2-04 PENDING — no external/staging alert delivery has yet been proven.",
            "M2-03, M2-05, and M2-06 remain pending.",
        ],
        "m2_status": {
            "M2-01": "DONE — merged engineering foundation",
            "M2-02": "DONE — merged engineering foundation",
            "M2-03": "PENDING — no genuine UAT users/consent",
            "M2-04": (
                "PENDING — local webhook adapter candidate only; "
                "no external/staging alert delivery has yet been proven"
            ),
            "M2-05": "PENDING — official genuine eligible count remains zero",
            "M2-06": "PENDING — no G1 exit report or Fizz verdict",
        },
    }


def render_alert_markdown(report: dict[str, object]) -> str:
    controls = report["controls"]
    summary = report["summary"]
    source = report["source"]
    lines = [
        f"# {report['title']}",
        "",
        f"Exact Git SHA: `{report['exact_git_sha']}`",
        "",
        f"Generated at: `{report['generated_at']}`",
        "",
        f"Evidence label: **{report['evidence_label']}**",
        "",
        str(report["claim_boundary"]),
        "",
        "## Source and controls",
        "",
        f"- Shadow report SHA-256: `{source['shadow_report_sha256']}`",
        f"- Case pack: `{source['case_pack_version']}`",
        f"- Execute: `{str(controls['execute']).lower()}`",
        f"- External action count: `{controls['external_action_count']}`",
        f"- External alert delivery count: `{controls['external_alert_delivery_count']}`",
        f"- Live SLO evidence eligible: `{str(controls['live_slo_evidence_eligible']).lower()}`",
        "",
        "## Evaluation summary",
        "",
        f"- Evaluation count: `{summary['evaluation_count']}`",
        f"- Idempotent replays: `{summary['idempotent_replay_count']}`",
        f"- States: `{json.dumps(summary['state_counts'], sort_keys=True)}`",
        f"- Measurement statuses: "
        f"`{json.dumps(summary['measurement_status_counts'], sort_keys=True)}`",
        f"- Firing by severity: `{json.dumps(summary['firing_by_severity'], sort_keys=True)}`",
        "",
        "## Policies",
        "",
    ]
    lines.extend(
        "- "
        f"`{item['policy_id']}`: {item['severity']}, {item['metric_name']} "
        f"> {item['threshold_value']} — **{item['threshold_classification']}**"
        for item in report["policies"]
    )
    lines.extend(["", "## Unwired / unmeasured / future signals", ""])
    lines.extend(
        f"- `{item['signal']}` — **{item['status']}**: {item['reason']}"
        for item in report["unwired_unmeasured_future_signals"]
    )
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in report["limitations"])
    lines.extend(["", "## M2 status", ""])
    lines.extend(f"- {key}: {value}" for key, value in report["m2_status"].items())
    lines.append("")
    return "\n".join(lines)


@dataclass(frozen=True)
class WrittenAlertReports:
    json_path: Path
    markdown_path: Path
    json_sha256: str
    markdown_sha256: str


def write_alert_reports(report: dict[str, object], output_dir: Path) -> WrittenAlertReports:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "m2-slo-alert-foundation.json"
    markdown_path = output_dir / "m2-slo-alert-foundation.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_alert_markdown(report), encoding="utf-8")
    return WrittenAlertReports(
        json_path=json_path,
        markdown_path=markdown_path,
        json_sha256=_sha256(json_path),
        markdown_sha256=_sha256(markdown_path),
    )
