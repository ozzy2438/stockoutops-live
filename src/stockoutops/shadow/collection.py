"""First-100 genuine shadow collection readiness. Synthetic cases never count."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from stockoutops.database import Database
from stockoutops.evidence.provenance import canonical_hash
from stockoutops.shadow.cases import LoadedCasePack, load_case_pack
from stockoutops.shadow.contracts import ShadowResult
from stockoutops.shadow.intake import ShadowIntakeRecord, ShadowIntakeRepository
from stockoutops.shadow.report import _hash

COLLECTION_TITLE = "M2 FIRST-100 READINESS — SIMULATED TOOLING REHEARSAL"
OFFICIAL_M2_05_REQUIREMENT = 100
GENUINE_PROVENANCE = "GENUINE_UAT_ANALYST_LABELLED"
SIMULATED_PROVENANCE = "SIMULATED"


def official_m2_05_contribution_from_synthetic_pack(case_count: int) -> int:
    """Synthetic packs contribute zero to the official M2-05 genuine-100 total."""
    if case_count < 0:
        raise ValueError("Synthetic case count cannot be negative")
    return 0


def reject_synthetic_m2_05_candidate(*, provenance_label: str, baseline_source: str) -> None:
    if (
        provenance_label == SIMULATED_PROVENANCE
        or baseline_source == "controlled_synthetic_reference"
    ):
        raise RuntimeError("Synthetic cases cannot count toward the official M2-05 total")


def _load_optional_results(path: Path | None) -> list[ShadowResult]:
    if path is None or not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases", [])
    results: list[ShadowResult] = []
    for item in cases:
        results.append(ShadowResult.model_validate(item.get("result", item)))
    return results


def _agreement_stats(results: list[ShadowResult]) -> dict[str, object]:
    if not results:
        return {
            "case_count": 0,
            "exact_agreements": 0,
            "partial_agreements": 0,
            "disagreements": 0,
            "escalation_agreements": 0,
            "unsupported_claim_count": 0,
            "missing_required_evidence_count": 0,
            "disagreement_categories": {},
            "status": "UNMEASURED",
        }
    exact = sum(result.comparison.exact_agreement for result in results)
    partial = sum(
        not result.comparison.exact_agreement
        and any(entry.agreement == "exact" for entry in result.comparison.entries)
        for result in results
    )
    escalation = 0
    categories: Counter[str] = Counter()
    for result in results:
        categories.update(result.comparison.disagreement_categories)
        escalation_entry = next(
            entry for entry in result.comparison.entries if entry.field_name == "escalated"
        )
        escalation += escalation_entry.agreement == "exact"
    return {
        "case_count": len(results),
        "exact_agreements": exact,
        "partial_agreements": partial,
        "disagreements": len(results) - exact,
        "escalation_agreements": escalation,
        "unsupported_claim_count": sum(
            result.comparison.unsupported_citation_count for result in results
        ),
        "missing_required_evidence_count": sum(
            result.comparison.missing_required_evidence_count for result in results
        ),
        "disagreement_categories": dict(sorted(categories.items())),
        "status": "SIMULATED" if results else "UNMEASURED",
    }


def official_m2_05_records(
    records: list[ShadowIntakeRecord],
    *,
    accepted_ids: set[UUID],
    excluded_ids: set[UUID],
) -> list[ShadowIntakeRecord]:
    eligible: list[ShadowIntakeRecord] = []
    for record in records:
        if record.provenance_label == SIMULATED_PROVENANCE:
            continue
        if record.baseline_source == "controlled_synthetic_reference":
            continue
        if record.intake_id not in accepted_ids:
            continue
        if record.intake_id in excluded_ids:
            continue
        if record.provenance_label != GENUINE_PROVENANCE:
            continue
        if record.baseline_source != "analyst_reference":
            continue
        eligible.append(record)
    for record in eligible:
        reject_synthetic_m2_05_candidate(
            provenance_label=record.provenance_label,
            baseline_source=record.baseline_source,
        )
    return eligible


def genuine_intake_manifest(records: list[ShadowIntakeRecord]) -> dict[str, object]:
    entries = [
        {
            "tenant_id": record.tenant_id,
            "case_id": record.case_id,
            "case_version": record.case_version,
            "payload_sha256": record.payload_hash,
            "provenance_label": record.provenance_label,
            "baseline_source": record.baseline_source,
            "category": record.category,
        }
        for record in sorted(
            records, key=lambda item: (item.tenant_id, item.case_id, item.case_version)
        )
    ]
    document = {
        "document": "m2-genuine-intake-manifest-v1",
        "case_count": len(entries),
        "cases": entries,
    }
    return {
        **document,
        "manifest_sha256": canonical_hash(document),
    }


def aggregate_collection(
    loaded: LoadedCasePack,
    *,
    git_sha: str,
    generated_at: datetime,
    intake_records: list[ShadowIntakeRecord] | None = None,
    accepted_ids: set[UUID] | None = None,
    excluded: dict[UUID, str] | None = None,
    simulated_results: list[ShadowResult] | None = None,
    genuine_results: list[ShadowResult] | None = None,
) -> dict[str, object]:
    intake_records = list(intake_records or [])
    accepted_ids = set(accepted_ids or set())
    excluded = dict(excluded or {})
    simulated_results = list(simulated_results or [])
    genuine_results = list(genuine_results or [])

    for case in loaded.pack.cases:
        if case.provenance_label != SIMULATED_PROVENANCE:
            raise RuntimeError("Controlled-synthetic pack contained a non-SIMULATED case")

    official = official_m2_05_records(
        intake_records,
        accepted_ids=accepted_ids,
        excluded_ids=set(excluded),
    )
    if (
        any(case.provenance_label == SIMULATED_PROVENANCE for case in loaded.pack.cases)
        and official
    ):
        synthetic_ids = {(case.case_id, case.case_version) for case in loaded.pack.cases}
        overlap = [
            record for record in official if (record.case_id, record.case_version) in synthetic_ids
        ]
        if overlap:
            raise RuntimeError("Synthetic pack identities cannot count toward official M2-05")

    provenance_counts = Counter(record.provenance_label for record in intake_records)
    provenance_counts[SIMULATED_PROVENANCE] += len(loaded.pack.cases)
    category_distribution = Counter(case.category for case in loaded.pack.cases)
    category_distribution.update(record.category for record in intake_records)
    analyst_reference_coverage = sum(
        1 for record in intake_records if record.baseline_source == "analyst_reference"
    )
    invalid_case_count = 0
    exclusion_reasons = Counter(excluded.values())

    per_case_audit = [
        {
            "collection_class": "SIMULATED",
            "case_id": case.case_id,
            "case_version": case.case_version,
            "tenant_id": case.tenant_id,
            "provenance_label": case.provenance_label,
            "baseline_source": case.baseline_source,
            "source": "controlled_synthetic_pack",
            "official_m2_05_eligible": False,
        }
        for case in loaded.pack.cases
    ]
    per_case_audit.extend(
        {
            "collection_class": "GENUINE_UAT_ANALYST_LABELLED",
            "case_id": record.case_id,
            "case_version": record.case_version,
            "tenant_id": record.tenant_id,
            "intake_id": str(record.intake_id),
            "payload_sha256": record.payload_hash,
            "provenance_label": record.provenance_label,
            "baseline_source": record.baseline_source,
            "source": "owner_approved_uat_import",
            "official_m2_05_eligible": record.intake_id in {item.intake_id for item in official},
        }
        for record in intake_records
    )

    simulated_agreement = _agreement_stats(simulated_results)
    simulated_agreement["evidence_label"] = "SIMULATED"
    genuine_agreement = _agreement_stats(genuine_results)
    genuine_agreement["evidence_label"] = (
        "GENUINE_UAT_ANALYST_LABELLED" if genuine_results else "UNMEASURED"
    )
    if genuine_results:
        for result in genuine_results:
            if result.provenance_label == SIMULATED_PROVENANCE:
                raise RuntimeError(
                    "SIMULATED results cannot enter genuine disagreement aggregation"
                )

    official_count = len(official)
    report = {
        "title": COLLECTION_TITLE,
        "evidence_label": "SIMULATED TOOLING REHEARSAL",
        "claim_boundary": (
            "Collection/readiness tooling only. Synthetic cases are excluded from the official "
            "M2-05 genuine 100-case requirement. No users were recruited and no genuine UAT "
            "cases exist in this repository."
        ),
        "exact_git_sha": git_sha,
        "generated_at": generated_at.isoformat(),
        "simulated": {
            "case_count": len(loaded.pack.cases),
            "pack_version": loaded.pack.case_pack_version,
            "cases_sha256": loaded.cases_sha256,
            "manifest_sha256": loaded.manifest_sha256,
            "provenance_label": SIMULATED_PROVENANCE,
            "baseline_source": "controlled_synthetic_reference",
            "official_m2_05_eligible_count": 0,
        },
        "genuine_intake": genuine_intake_manifest(intake_records),
        "cumulative": {
            "simulated_case_count": len(loaded.pack.cases),
            "genuine_imported_count": len(intake_records),
            "analyst_reference_coverage": analyst_reference_coverage,
            "accepted_for_m2_05_count": official_count,
            "excluded_count": len(excluded),
            "invalid_case_count": invalid_case_count,
            "provenance_counts": dict(sorted(provenance_counts.items())),
            "category_distribution": dict(sorted(category_distribution.items())),
            "exclusion_reasons": dict(sorted(exclusion_reasons.items())),
        },
        "agreement": {
            "simulated": simulated_agreement,
            "genuine_uat_analyst_labelled": genuine_agreement,
        },
        "official_m2_05": {
            "eligible_count": official_count,
            "requirement": OFFICIAL_M2_05_REQUIREMENT,
            "remaining": max(0, OFFICIAL_M2_05_REQUIREMENT - official_count),
            "status": "PENDING — no first 100 genuine shadow cases",
            "synthetic_cases_excluded": len(loaded.pack.cases),
            "synthetic_contribution": official_m2_05_contribution_from_synthetic_pack(
                len(loaded.pack.cases)
            ),
        },
        "controls": {
            "execute": False,
            "external_action_count": 0,
            "openai_calls": 0,
            "aws_resources_used": 0,
        },
        "m2_status": {
            "M2-01": "merged engineering foundation (PR #18)",
            "M2-02": "merged engineering foundation (PR #18)",
            "M2-03": "PENDING — no users recruited",
            "M2-04": "PENDING — no SLO alerts",
            "M2-05": "PENDING — no first 100 genuine shadow cases",
            "M2-06": "PENDING — no G1 exit report or verdict",
        },
        "per_case_audit": per_case_audit,
        "limitations": [
            "The 12-case pack remains controlled synthetic and cannot satisfy M2-05.",
            "No genuine participant, consent record, or analyst-labelled case is stored in git.",
            "M2-04 SLO alerts remain unimplemented; this report is not an alert backend.",
        ],
    }
    if report["simulated"]["official_m2_05_eligible_count"] != 0:
        raise RuntimeError("Synthetic cases cannot count toward the official M2-05 total")
    if report["official_m2_05"]["synthetic_contribution"] != 0:
        raise RuntimeError("Synthetic cases cannot count toward the official M2-05 total")
    if official_count != len(
        [item for item in per_case_audit if item["official_m2_05_eligible"] is True]
    ):
        raise RuntimeError("Official M2-05 audit rows diverged from the eligible count")
    report["report_sha256"] = canonical_hash(
        {key: value for key, value in report.items() if key != "report_sha256"}
    )
    return report


def render_collection_markdown(report: dict[str, object]) -> str:
    official = report["official_m2_05"]
    simulated = report["simulated"]
    genuine = report["genuine_intake"]
    cumulative = report["cumulative"]
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
        "## Simulated versus genuine",
        "",
        f"- Simulated pack cases: `{simulated['case_count']}`",
        f"- Simulated pack SHA-256: `{simulated['cases_sha256']}`",
        f"- Genuine imported cases: `{genuine['case_count']}`",
        f"- Genuine intake manifest SHA-256: `{genuine['manifest_sha256']}`",
        f"- Official M2-05 eligible count: `{official['eligible_count']}`"
        f" / `{official['requirement']}`",
        f"- Official status: {official['status']}",
        "",
        "## Cumulative tracking",
        "",
        f"- Provenance counts: `{json.dumps(cumulative['provenance_counts'], sort_keys=True)}`",
        f"- Category distribution: "
        f"`{json.dumps(cumulative['category_distribution'], sort_keys=True)}`",
        f"- Analyst/reference coverage: `{cumulative['analyst_reference_coverage']}`",
        f"- Exclusion reasons: `{json.dumps(cumulative['exclusion_reasons'], sort_keys=True)}`",
        f"- Invalid-case count: `{cumulative['invalid_case_count']}`",
        "",
        "## M2 status",
        "",
    ]
    lines.extend(f"- {key}: {value}" for key, value in report["m2_status"].items())
    lines.append("")
    return "\n".join(lines)


def write_collection_reports(report: dict[str, object], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "m2-first-100-readiness.json"
    markdown_path = output_dir / "m2-first-100-readiness.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_collection_markdown(report), encoding="utf-8")
    return {
        "aggregate_json": str(json_path),
        "aggregate_json_sha256": _hash(json_path),
        "aggregate_markdown": str(markdown_path),
        "aggregate_markdown_sha256": _hash(markdown_path),
        "manifest_sha256": report["genuine_intake"]["manifest_sha256"],
        "report_sha256": report["report_sha256"],
    }


def _git_sha() -> str:
    import subprocess

    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the M2 first-100 readiness report")
    parser.add_argument("--cases", default="evaluation/shadow/cases/v1")
    parser.add_argument("--output-dir", default="evaluation/reports")
    parser.add_argument("--git-sha", default=None)
    parser.add_argument(
        "--shadow-results", default="evaluation/reports/m2-shadow-foundation-pilot.json"
    )
    parser.add_argument("--include-intake", action="store_true", default=True)
    args = parser.parse_args()
    loaded = load_case_pack(Path(args.cases))
    intake_records: list[ShadowIntakeRecord] = []
    accepted_ids: set[UUID] = set()
    excluded: dict[UUID, str] = {}
    if args.include_intake and os.getenv("DATABASE_URL"):
        repository = ShadowIntakeRepository(Database(os.environ["DATABASE_URL"]))
        intake_records = repository.list_all()
        accepted_ids = repository.accepted_intake_ids()
        excluded = repository.excluded_intake_ids()
    report = aggregate_collection(
        loaded,
        git_sha=args.git_sha or _git_sha(),
        generated_at=datetime.now(UTC),
        intake_records=intake_records,
        accepted_ids=accepted_ids,
        excluded=excluded,
        simulated_results=_load_optional_results(Path(args.shadow_results)),
        genuine_results=[],
    )
    written = write_collection_reports(report, Path(args.output_dir))
    print(
        json.dumps(
            {
                **written,
                "official_m2_05_eligible_count": report["official_m2_05"]["eligible_count"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
