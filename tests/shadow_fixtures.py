from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from stockoutops.shadow.contracts import ShadowCase


def genuine_uat_schema_fixture_payload(**overrides: Any) -> dict[str, Any]:
    """In-memory schema/intake fixture. Not a genuine UAT or analyst record."""
    payload: dict[str, Any] = {
        "case_id": "uat-schema-fixture-001",
        "case_version": "v1",
        "case_contract_version": "m2-shadow-case-contract-v2",
        "category": "schema_fixture_not_genuine_uat",
        "tenant_id": "t_alpha",
        "as_of_timestamp": "2026-08-10T12:00:00Z",
        "execute": False,
        "input": {
            "sku_id": "UAT-FIXTURE-SKU-001",
            "store_id": "UAT-FIXTURE-STORE-001",
            "supplier_id": "UAT-FIXTURE-SUPPLIER-001",
            "as_of_ts": "2026-08-10T12:00:00Z",
            "window_start": "2026-08-03T12:00:00Z",
            "window_end": "2026-08-10T12:00:00Z",
        },
        "baseline_source": "analyst_reference",
        "reference_outcome": {
            "expected_state": "awaiting_human",
            "root_cause_statement": "Schema-fixture reference statement; not an analyst decision.",
            "recommendation_action_type": "monitor",
            "confidence": "low",
        },
        "reference_escalation_expectation": {"expected": False, "code": None},
        "minimum_evidence_citation_expectations": {
            "required_tools": ["T1_inventory", "T2_sales_demand"],
            "minimum_unique_citations": 2,
        },
        "provenance_label": "GENUINE_UAT_ANALYST_LABELLED",
        "deidentification_status": "deidentified_owner_attested",
        "consent_data_use_status": "owner_attested_consent_held_offline",
        "consent_data_use_reference": "OFFLINE-CONSENT-TEST-FIXTURE-0001",
        "fixture_setup": {
            "inventory": {
                "on_hand": 3,
                "reserved": 0,
                "on_order": 1,
                "updated_at": "2026-08-10T08:00:00Z",
            },
            "demand": {
                "units_sold": 21,
                "average_daily_units": 3,
                "demand_signal": "stable",
                "updated_at": "2026-08-09T12:00:00Z",
            },
            "supplier": None,
        },
        "notes": "SCHEMA/INTAKE FIXTURE — NOT GENUINE UAT AND NOT AN ANALYST DECISION.",
        "limitations": [
            "Constructed only to validate the future genuine-case contract and intake path."
        ],
    }
    payload.update(overrides)
    return payload


def genuine_uat_schema_fixture(**overrides: Any) -> ShadowCase:
    return ShadowCase.model_validate(genuine_uat_schema_fixture_payload(**overrides))


def synthetic_intake_record_shape(*, intake_id: UUID | None = None) -> dict[str, Any]:
    return {
        "intake_id": intake_id or UUID(int=7),
        "tenant_id": "t_alpha",
        "case_id": "m2-supplier-delay-001",
        "case_version": "v1",
        "case_contract_version": "m2-shadow-case-contract-v2",
        "payload_hash": "a" * 64,
        "provenance_label": "SIMULATED",
        "baseline_source": "controlled_synthetic_reference",
        "deidentification_status": "not_applicable_controlled_synthetic",
        "consent_data_use_status": "not_applicable_controlled_synthetic",
        "consent_data_use_reference": "OFFLINE-CONSENT-INVALID",
        "category": "supplier_delay",
        "execute": False,
        "external_action_count": 0,
        "case_json": {},
        "created_by": "test",
        "created_at": datetime(2026, 8, 13, tzinfo=UTC),
    }
