"""Deterministic aggregate JSON and human-readable Markdown shadow reports."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from stockoutops.shadow.cases import LoadedCasePack
from stockoutops.shadow.contracts import ShadowResult

REPORT_TITLE = "M2 SHADOW FOUNDATION — SIMULATED ENGINEERING REHEARSAL"


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def aggregate_report(
    results: list[ShadowResult],
    loaded: LoadedCasePack,
    *,
    git_sha: str,
    generated_at: datetime,
    test_evidence: str,
) -> dict[str, object]:
    cases = {(case.case_id, case.case_version): case for case in loaded.pack.cases}
    disagreement_categories: Counter[str] = Counter()
    field_disagreements: Counter[str] = Counter()
    case_categories: Counter[str] = Counter()
    escalation_agreements = 0
    total_coverage = 0.0
    latencies: list[float] = []
    per_case: list[dict[str, object]] = []

    for result in results:
        case = cases[(result.case_id, result.case_version)]
        case_categories[case.category] += 1
        disagreement_categories.update(result.comparison.disagreement_categories)
        field_disagreements.update(
            entry.field_name for entry in result.comparison.entries if entry.agreement != "exact"
        )
        escalation_entry = next(
            entry for entry in result.comparison.entries if entry.field_name == "escalated"
        )
        escalation_agreements += escalation_entry.agreement == "exact"
        total_coverage += result.comparison.citation_coverage
        latencies.append(result.actual.latency_ms)
        per_case.append(
            {
                "category": case.category,
                "case_payload_sha256": hashlib.sha256(
                    json.dumps(
                        case.model_dump(mode="json"),
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest(),
                "result": result.model_dump(mode="json"),
            }
        )

    count = len(results)
    exact = sum(result.comparison.exact_agreement for result in results)
    partial = sum(
        not result.comparison.exact_agreement
        and any(entry.agreement == "exact" for entry in result.comparison.entries)
        for result in results
    )
    disagreements = count - exact
    external_actions = sum(result.actual.external_action_count for result in results)
    return {
        "title": REPORT_TITLE,
        "evidence_label": "SIMULATED",
        "claim_boundary": (
            "Controlled-synthetic deterministic engineering rehearsal only; not analyst "
            "agreement, model quality, UAT, production operation, or G1 exit evidence."
        ),
        "exact_git_sha": git_sha,
        "generated_at": generated_at.isoformat(),
        "case_pack": {
            "version": loaded.pack.case_pack_version,
            "cases_sha256": loaded.cases_sha256,
            "manifest_sha256": loaded.manifest_sha256,
            "case_count": count,
            "categories": dict(sorted(case_categories.items())),
            "baseline_source": "controlled_synthetic_reference",
            "provenance_label": "SIMULATED",
        },
        "controls": {
            "provider": "deterministic-stub-v1",
            "execute": False,
            "external_action_count": external_actions,
            "openai_calls": {
                "count": 0,
                "label": "CODE/CONFIGURATION EVIDENCE — not network telemetry",
            },
            "aws_resources_used": {
                "count": 0,
                "label": "TASK-SCOPE EVIDENCE — no AWS command or integration path",
            },
        },
        "metrics": {
            "case_count": count,
            "exact_agreements": exact,
            "partial_agreements": partial,
            "disagreements": disagreements,
            "escalation_agreements": escalation_agreements,
            "citation_coverage": total_coverage / count if count else 0.0,
            "unsupported_claim_count": sum(
                result.comparison.unsupported_citation_count for result in results
            ),
            "missing_required_evidence_count": sum(
                result.comparison.missing_required_evidence_count for result in results
            ),
            "latency_ms": {
                "minimum": min(latencies, default=0.0),
                "average": sum(latencies) / count if count else 0.0,
                "maximum": max(latencies, default=0.0),
                "label": "SIMULATED deterministic-provider metadata",
            },
            "disagreement_categories": dict(sorted(disagreement_categories.items())),
            "field_disagreements": dict(sorted(field_disagreements.items())),
        },
        "test_evidence": test_evidence,
        "limitations": [
            "All cases and reference outcomes are controlled synthetic fixtures.",
            "No genuine analyst decisions, UAT users, live stockout cases, or model call exist.",
            "Synthetic agreement cannot establish reasoning quality or operational reliability.",
            "missing_required_evidence_count uses each case's required_tools set; "
            "see evaluation/shadow/METRICS.md.",
            "M2-04 SLO alerts are pending; no SLO compliance is claimed.",
        ],
        "m2_status": {
            "M2-01": "merged engineering foundation (PR #18)",
            "M2-02": "merged engineering foundation (PR #18)",
            "M2-03": "PENDING — no users recruited",
            "M2-04": "PENDING — no SLO alerts",
            "M2-05": "PENDING — no first 100 genuine shadow cases",
            "M2-06": "PENDING — no G1 exit report or verdict",
        },
        "cases": per_case,
    }


def render_markdown(report: dict[str, object]) -> str:
    pack = report["case_pack"]
    controls = report["controls"]
    metrics = report["metrics"]
    status = report["m2_status"]
    limitations = report["limitations"]
    lines = [
        f"# {REPORT_TITLE}",
        "",
        f"Exact Git SHA: `{report['exact_git_sha']}`",
        "",
        f"Generated at: `{report['generated_at']}`",
        "",
        f"Evidence label: **{report['evidence_label']}**",
        "",
        str(report["claim_boundary"]),
        "",
        "## Case pack and controls",
        "",
        f"- Version: `{pack['version']}`",
        f"- Cases SHA-256: `{pack['cases_sha256']}`",
        f"- Manifest SHA-256: `{pack['manifest_sha256']}`",
        f"- Case count: `{pack['case_count']}`",
        f"- Baseline source: `{pack['baseline_source']}`",
        f"- Provider: `{controls['provider']}`",
        f"- Execute: `{str(controls['execute']).lower()}`",
        f"- External action count: `{controls['external_action_count']}`",
        f"- OpenAI calls: `{controls['openai_calls']['count']}` "
        f"({controls['openai_calls']['label']})",
        f"- AWS resources used: `{controls['aws_resources_used']['count']}` "
        f"({controls['aws_resources_used']['label']})",
        "",
        "## Deterministic diff metrics",
        "",
        f"- Exact agreements: `{metrics['exact_agreements']}`",
        f"- Partial agreements: `{metrics['partial_agreements']}`",
        f"- Disagreements: `{metrics['disagreements']}`",
        f"- Escalation agreements: `{metrics['escalation_agreements']}`",
        f"- Citation coverage: `{metrics['citation_coverage']:.3f}`",
        f"- Unsupported claim count: `{metrics['unsupported_claim_count']}`",
        f"- Missing required evidence count: `{metrics['missing_required_evidence_count']}`",
        "- Disagreement categories: "
        f"`{json.dumps(metrics['disagreement_categories'], sort_keys=True)}`",
        "",
        "## Test evidence",
        "",
        str(report["test_evidence"]),
        "",
        "## Limitations",
        "",
    ]
    lines.extend(f"- {item}" for item in limitations)
    lines.extend(["", "## M2 status", ""])
    lines.extend(f"- {key}: {value}" for key, value in status.items())
    lines.append("")
    return "\n".join(lines)


@dataclass(frozen=True)
class WrittenReports:
    aggregate_json: Path
    aggregate_markdown: Path
    per_case_directory: Path
    aggregate_json_sha256: str
    aggregate_markdown_sha256: str


def write_reports(report: dict[str, object], output_dir: Path) -> WrittenReports:
    output_dir.mkdir(parents=True, exist_ok=True)
    case_dir = output_dir / "m2-shadow-foundation-cases"
    case_dir.mkdir(parents=True, exist_ok=True)
    for item in report["cases"]:
        result = item["result"]
        path = case_dir / f"{result['case_id']}-{result['case_version']}.json"
        path.write_text(json.dumps(item, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    aggregate_json = output_dir / "m2-shadow-foundation-pilot.json"
    aggregate_markdown = output_dir / "m2-shadow-foundation-pilot.md"
    aggregate_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    aggregate_markdown.write_text(render_markdown(report), encoding="utf-8")
    return WrittenReports(
        aggregate_json=aggregate_json,
        aggregate_markdown=aggregate_markdown,
        per_case_directory=case_dir,
        aggregate_json_sha256=_hash(aggregate_json),
        aggregate_markdown_sha256=_hash(aggregate_markdown),
    )
