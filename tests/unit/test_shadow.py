from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from stockoutops.shadow.cases import load_case_pack
from stockoutops.shadow.contracts import ShadowActualOutcome, ShadowResult
from stockoutops.shadow.diff import compare
from stockoutops.shadow.report import REPORT_TITLE, aggregate_report, write_reports

CASES_DIR = Path("evaluation/shadow/cases/v1")


def _matching_actual(case) -> ShadowActualOutcome:
    expected = case.reference_outcome
    escalated = case.reference_escalation_expectation
    tools = case.minimum_evidence_citation_expectations.required_tools
    evidence_ids = [f"ev_{index:064x}" for index in range(1, len(tools) + 1)]
    citation_ids = evidence_ids[
        : case.minimum_evidence_citation_expectations.minimum_unique_citations
    ]
    return ShadowActualOutcome(
        state=expected.expected_state,
        escalated=escalated.expected,
        escalation_code=escalated.code,
        root_cause_statement=expected.root_cause_statement,
        recommendation_action_type=expected.recommendation_action_type,
        confidence=expected.confidence,
        evidence_tools=tools,
        evidence_ids=evidence_ids,
        citation_ids=citation_ids,
        unsupported_citation_count=0,
        missing_required_evidence_count=0,
        citation_coverage=1.0 if evidence_ids else 0.0,
        schema_valid=True,
        reasoning_invoked=not escalated.expected,
        provider_label="deterministic-stub-v1" if not escalated.expected else "not-invoked",
        latency_ms=0.0,
        estimated_cost_usd=0.0 if not escalated.expected else None,
        cost_evidence_label="SIMULATED" if not escalated.expected else "UNMEASURED",
        execute=False,
        external_action_count=0,
    )


def test_case_pack_is_versioned_manifest_verified_and_honestly_labelled() -> None:
    loaded = load_case_pack(CASES_DIR)
    assert loaded.pack.case_pack_version == "m2-shadow-cases-v1-2026-08-13"
    assert len(loaded.pack.cases) == 12
    assert len({case.category for case in loaded.pack.cases}) >= 4
    assert {case.baseline_source for case in loaded.pack.cases} == {
        "controlled_synthetic_reference"
    }
    assert {case.provenance_label for case in loaded.pack.cases} == {"SIMULATED"}
    assert all(case.execute is False for case in loaded.pack.cases)


def test_case_schema_rejects_execute_true_and_version_drift() -> None:
    case = load_case_pack(CASES_DIR).pack.cases[0]
    with pytest.raises(ValidationError):
        case.model_copy(update={"execute": True}, deep=True).__class__.model_validate(
            {**case.model_dump(mode="json"), "execute": True}
        )
    with pytest.raises(ValidationError):
        case.__class__.model_validate({**case.model_dump(mode="json"), "case_version": "latest"})


def test_diff_is_deterministic_and_accounts_for_missing_and_unsupported_citations() -> None:
    case = load_case_pack(CASES_DIR).pack.cases[0]
    actual = _matching_actual(case)
    first = compare(case, actual)
    second = compare(case, actual)
    assert first == second
    assert first.exact_agreement is True

    degraded = actual.model_copy(
        update={
            "evidence_tools": ["T1_inventory"],
            "citation_ids": ["ev_" + "f" * 64],
            "unsupported_citation_count": 1,
            "missing_required_evidence_count": 2,
            "citation_coverage": 0.0,
        }
    )
    comparison = compare(case, degraded)
    assert comparison.exact_agreement is False
    assert comparison.unsupported_citation_count == 1
    assert comparison.missing_required_evidence_count == 2
    assert "unsupported_claim" in comparison.disagreement_categories
    evidence = next(
        entry for entry in comparison.entries if entry.field_name == "required_evidence_tools"
    )
    assert evidence.agreement == "partial"


def test_report_generation_is_structured_and_explicitly_simulated(tmp_path: Path) -> None:
    loaded = load_case_pack(CASES_DIR)
    case = loaded.pack.cases[0]
    actual = _matching_actual(case)
    comparison = compare(case, actual)
    result = ShadowResult(
        shadow_run_id=UUID(int=1),
        investigation_run_id=UUID(int=2),
        case_id=case.case_id,
        case_version=case.case_version,
        case_pack_version=loaded.pack.case_pack_version,
        tenant_id=case.tenant_id,
        processor_version="m2-shadow-processor-v1",
        prompt_version="m1-bounded-reasoning-v1",
        tool_schema_version="v1",
        provenance_label="SIMULATED",
        baseline_source="controlled_synthetic_reference",
        output_hash="a" * 64,
        diff_hash="b" * 64,
        actual=actual,
        comparison=comparison,
        idempotent_replay=False,
    )
    report = aggregate_report(
        [result],
        loaded,
        git_sha="c" * 40,
        generated_at=datetime(2026, 8, 13, tzinfo=UTC),
        test_evidence="MEASURED — unit fixture only.",
    )
    written = write_reports(report, tmp_path)
    assert report["title"] == REPORT_TITLE
    assert report["controls"]["execute"] is False
    assert report["controls"]["external_action_count"] == 0
    assert report["m2_status"]["M2-03"].startswith("PENDING")
    assert written.aggregate_json.exists()
    assert written.aggregate_markdown.exists()
    assert list(written.per_case_directory.glob("*.json"))
    markdown = written.aggregate_markdown.read_text(encoding="utf-8")
    assert REPORT_TITLE in markdown
    assert "no G1 exit report" in markdown
