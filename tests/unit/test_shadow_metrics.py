from __future__ import annotations

from pathlib import Path

import pytest

from stockoutops.shadow.cases import load_case_pack
from stockoutops.shadow.diff import compare
from stockoutops.shadow.metrics import missing_required_evidence_count
from tests.unit.test_shadow import _matching_actual

CASES_DIR = Path("evaluation/shadow/cases/v1")


def test_canonical_missing_required_evidence_ignores_unused_tool_slots() -> None:
    assert missing_required_evidence_count(["T1_inventory"], ["T1_inventory"]) == 0
    assert missing_required_evidence_count(["T1_inventory"], ["T1_inventory", "T3_supplier"]) == 0


def test_canonical_missing_counts_only_absent_required_tools() -> None:
    required = ["T1_inventory", "T2_sales_demand", "T3_supplier"]
    assert missing_required_evidence_count(required, ["T1_inventory"]) == 2
    assert missing_required_evidence_count(required, required) == 0


def test_canonical_definition_rejects_empty_or_unknown_tools() -> None:
    with pytest.raises(ValueError, match="at least one"):
        missing_required_evidence_count([], ["T1_inventory"])
    with pytest.raises(ValueError, match="outside the T1-T3 boundary"):
        missing_required_evidence_count(["T9_unknown"], ["T1_inventory"])


def test_compare_uses_case_required_tools_not_three_slot_count() -> None:
    loaded = load_case_pack(CASES_DIR)
    case = next(item for item in loaded.pack.cases if item.case_id == "m2-missing-demand-008")
    actual = _matching_actual(case)
    actual = actual.model_copy(
        update={
            "evidence_tools": ["T1_inventory"],
            "missing_required_evidence_count": 99,
        }
    )
    comparison = compare(case, actual)
    assert set(case.minimum_evidence_citation_expectations.required_tools) == {"T1_inventory"}
    assert comparison.missing_required_evidence_count == 0
    three_slot_historical = max(0, 3 - len(set(actual.evidence_tools)))
    assert three_slot_historical == 2
    assert comparison.missing_required_evidence_count != three_slot_historical
