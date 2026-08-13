from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from stockoutops.shadow.cases import load_case_pack
from stockoutops.shadow.contracts import ShadowCase, ShadowIntakeDocument
from stockoutops.shadow.intake import case_payload_hash, load_intake_document
from tests.shadow_fixtures import genuine_uat_schema_fixture, genuine_uat_schema_fixture_payload

CASES_DIR = Path("evaluation/shadow/cases/v1")


def test_existing_synthetic_pack_still_validates_under_extended_contract() -> None:
    loaded = load_case_pack(CASES_DIR)
    assert all(case.provenance_label == "SIMULATED" for case in loaded.pack.cases)
    assert all(
        case.case_contract_version == "m2-shadow-case-contract-v2" for case in loaded.pack.cases
    )
    assert all(
        case.deidentification_status == "not_applicable_controlled_synthetic"
        for case in loaded.pack.cases
    )
    assert all(case.consent_data_use_reference is None for case in loaded.pack.cases)


def test_genuine_schema_requires_consent_deidentification_and_analyst_reference() -> None:
    case = genuine_uat_schema_fixture()
    assert case.provenance_label == "GENUINE_UAT_ANALYST_LABELLED"
    assert case.baseline_source == "analyst_reference"
    assert case.consent_data_use_reference == "OFFLINE-CONSENT-TEST-FIXTURE-0001"
    assert case.deidentification_status == "deidentified_owner_attested"
    assert case.execute is False


def test_invalid_provenance_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ShadowCase.model_validate(
            genuine_uat_schema_fixture_payload(provenance_label="LIVE_PRODUCTION")
        )
    with pytest.raises(ValidationError, match="controlled_synthetic_reference"):
        ShadowCase.model_validate(
            genuine_uat_schema_fixture_payload(
                provenance_label="SIMULATED",
                baseline_source="controlled_synthetic_reference",
                deidentification_status="not_applicable_controlled_synthetic",
                consent_data_use_status="not_applicable_controlled_synthetic",
                consent_data_use_reference=None,
            )
            | {"baseline_source": "analyst_reference"}
        )


def test_genuine_case_missing_consent_reference_is_rejected() -> None:
    payload = genuine_uat_schema_fixture_payload(consent_data_use_reference=None)
    with pytest.raises(ValidationError, match="consent/data-use reference"):
        ShadowCase.model_validate(payload)


def test_deidentification_status_is_required_for_genuine_cases() -> None:
    with pytest.raises(ValidationError, match="de-identification"):
        ShadowCase.model_validate(
            genuine_uat_schema_fixture_payload(
                deidentification_status="not_applicable_controlled_synthetic"
            )
        )


def test_execute_true_remains_forbidden_on_genuine_schema() -> None:
    with pytest.raises(ValidationError):
        ShadowCase.model_validate(genuine_uat_schema_fixture_payload(execute=True))


def test_intake_document_rejects_simulated_cases() -> None:
    synthetic = load_case_pack(CASES_DIR).pack.cases[0]
    with pytest.raises(ValidationError, match="rejects SIMULATED"):
        ShadowIntakeDocument.model_validate(
            {
                "intake_document_version": "m2-uat-intake-v1",
                "execute": False,
                "cases": [synthetic.model_dump(mode="json")],
            }
        )


def test_intake_document_rejects_unknown_version() -> None:
    with pytest.raises(ValidationError):
        ShadowIntakeDocument.model_validate(
            {
                "intake_document_version": "m2-uat-intake-v9",
                "execute": False,
                "cases": [genuine_uat_schema_fixture_payload()],
            }
        )


def test_intake_json_loader_and_payload_hash_are_deterministic(tmp_path: Path) -> None:
    document = {
        "intake_document_version": "m2-uat-intake-v1",
        "execute": False,
        "cases": [genuine_uat_schema_fixture_payload()],
    }
    path = tmp_path / "intake.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    loaded = load_intake_document(path)
    first = case_payload_hash(loaded.cases[0])
    second = case_payload_hash(genuine_uat_schema_fixture())
    assert first == second
    assert len(first) == 64
