from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from stockoutops.shadow.cases import load_case_pack
from stockoutops.shadow.collection import (
    aggregate_collection,
    official_m2_05_contribution_from_synthetic_pack,
    official_m2_05_records,
    reject_synthetic_m2_05_candidate,
    write_collection_reports,
)
from stockoutops.shadow.intake import ShadowIntakeRecord
from tests.shadow_fixtures import genuine_uat_schema_fixture, synthetic_intake_record_shape

CASES_DIR = Path("evaluation/shadow/cases/v1")


def _intake_record(**overrides) -> ShadowIntakeRecord:
    payload = synthetic_intake_record_shape()
    genuine = genuine_uat_schema_fixture()
    payload.update(
        {
            "case_id": genuine.case_id,
            "provenance_label": genuine.provenance_label,
            "baseline_source": genuine.baseline_source,
            "deidentification_status": genuine.deidentification_status,
            "consent_data_use_status": genuine.consent_data_use_status,
            "consent_data_use_reference": genuine.consent_data_use_reference,
            "category": genuine.category,
            "case_json": genuine.model_dump(mode="json"),
        }
    )
    payload.update(overrides)
    return ShadowIntakeRecord(**payload)


def test_synthetic_pack_cannot_count_toward_genuine_100() -> None:
    loaded = load_case_pack(CASES_DIR)
    assert official_m2_05_contribution_from_synthetic_pack(len(loaded.pack.cases)) == 0
    with pytest.raises(RuntimeError, match="cannot count"):
        reject_synthetic_m2_05_candidate(
            provenance_label="SIMULATED",
            baseline_source="controlled_synthetic_reference",
        )


def test_synthetic_intake_shape_is_excluded_even_if_marked_accepted() -> None:
    synthetic = ShadowIntakeRecord(**synthetic_intake_record_shape())
    eligible = official_m2_05_records(
        [synthetic],
        accepted_ids={synthetic.intake_id},
        excluded_ids=set(),
    )
    assert eligible == []


def test_collection_report_is_deterministic_and_keeps_synthetic_out_of_m2_05(
    tmp_path: Path,
) -> None:
    loaded = load_case_pack(CASES_DIR)
    first = aggregate_collection(
        loaded,
        git_sha="d" * 40,
        generated_at=datetime(2026, 8, 13, tzinfo=UTC),
    )
    second = aggregate_collection(
        loaded,
        git_sha="d" * 40,
        generated_at=datetime(2026, 8, 13, tzinfo=UTC),
    )
    assert first == second
    assert first["official_m2_05"]["eligible_count"] == 0
    assert first["official_m2_05"]["synthetic_contribution"] == 0
    assert first["simulated"]["case_count"] == 12
    assert first["genuine_intake"]["case_count"] == 0
    assert first["m2_status"]["M2-03"].startswith("PENDING")
    written = write_collection_reports(first, tmp_path)
    assert Path(written["aggregate_json"]).exists()
    markdown = Path(written["aggregate_markdown"]).read_text(encoding="utf-8")
    assert "SIMULATED" in markdown
    assert "Official M2-05 eligible count: `0`" in markdown


def test_accepted_genuine_fixture_counts_but_synthetic_pack_does_not() -> None:
    loaded = load_case_pack(CASES_DIR)
    record = _intake_record(intake_id=UUID(int=21))
    report = aggregate_collection(
        loaded,
        git_sha="e" * 40,
        generated_at=datetime(2026, 8, 13, tzinfo=UTC),
        intake_records=[record],
        accepted_ids={record.intake_id},
    )
    assert report["genuine_intake"]["case_count"] == 1
    assert report["official_m2_05"]["eligible_count"] == 1
    assert report["official_m2_05"]["synthetic_contribution"] == 0
    assert report["simulated"]["official_m2_05_eligible_count"] == 0
    assert report["genuine_intake"]["manifest_sha256"]
    assert len(report["genuine_intake"]["manifest_sha256"]) == 64
