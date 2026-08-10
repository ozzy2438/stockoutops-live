from datetime import UTC, datetime, timedelta

import pytest

from stockoutops.evidence.contracts import EvidenceFailure, validate_bundle
from stockoutops.evidence.tools import EvidenceTools
from stockoutops.identity import Principal

AS_OF = datetime(2026, 8, 10, 12, tzinfo=UTC)


class FakeFixtureRepository:
    def fetch_inventory_fixture(self, principal, sku_id, store_id):
        return {
            "sku_id": sku_id,
            "store_id": store_id,
            "on_hand": 2,
            "reserved": 1,
            "on_order": 0,
            "updated_at": AS_OF - timedelta(hours=4),
        }

    def fetch_demand_fixture(self, principal, sku_id, store_id, window_start, window_end):
        return {
            "sku_id": sku_id,
            "store_id": store_id,
            "units_sold": 56,
            "average_daily_units": 8,
            "demand_signal": "above_available_stock",
            "updated_at": AS_OF - timedelta(hours=24),
        }

    def fetch_supplier_fixture(self, principal, sku_id, supplier_id):
        return {
            "sku_id": sku_id,
            "supplier_id": supplier_id,
            "open_order_quantity": 0,
            "expected_receipt_at": AS_OF + timedelta(days=4),
            "historical_lead_time_days": 4,
            "status": "delayed",
            "updated_at": AS_OF - timedelta(hours=42),
        }


def _bundle():
    principal = Principal("operator-a", "t_alpha", frozenset({"operator"}))
    tools = EvidenceTools(FakeFixtureRepository(), manifest_version="test-v1")
    return [
        tools.inventory(principal, sku_id="SKU-001", store_id="STORE-001", as_of_ts=AS_OF),
        tools.demand(
            principal,
            sku_id="SKU-001",
            store_id="STORE-001",
            window_start=AS_OF - timedelta(days=7),
            window_end=AS_OF,
            as_of_ts=AS_OF,
        ),
        tools.supplier(principal, sku_id="SKU-001", supplier_id="SUPPLIER-001", as_of_ts=AS_OF),
    ]


def test_t1_t2_t3_evidence_is_valid_and_ids_are_deterministic() -> None:
    first = _bundle()
    second = _bundle()
    validate_bundle(first, as_of_ts=AS_OF)
    assert [item.evidence_id for item in first] == [item.evidence_id for item in second]
    assert {item.tool for item in first} == {
        "T1_inventory",
        "T2_sales_demand",
        "T3_supplier",
    }


def test_missing_stale_and_invalid_provenance_fail_closed() -> None:
    bundle = _bundle()
    with pytest.raises(EvidenceFailure, match="all required"):
        validate_bundle(bundle[:2], as_of_ts=AS_OF)
    bundle = _bundle()
    bundle[0].freshness_ts = AS_OF - timedelta(hours=25)
    with pytest.raises(EvidenceFailure, match="outside policy"):
        validate_bundle(bundle, as_of_ts=AS_OF)
    bundle = _bundle()
    bundle[0].content_hash = "0" * 64
    with pytest.raises(EvidenceFailure, match="Content hash"):
        validate_bundle(bundle, as_of_ts=AS_OF)
