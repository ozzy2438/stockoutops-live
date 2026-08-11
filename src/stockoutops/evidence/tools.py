"""Read-only T1-T3 tools over tenant-scoped PostgreSQL fixtures."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from stockoutops.evidence.contracts import (
    DemandEvidence,
    EvidenceFailure,
    InventoryEvidence,
    SupplierEvidence,
)
from stockoutops.evidence.provenance import provenance_fields
from stockoutops.identity import Principal


class FixtureReader(Protocol):
    def fetch_inventory_fixture(
        self, principal: Principal, sku_id: str, store_id: str
    ) -> dict[str, object] | None: ...

    def fetch_demand_fixture(
        self,
        principal: Principal,
        sku_id: str,
        store_id: str,
        window_start: datetime,
        window_end: datetime,
    ) -> dict[str, object] | None: ...

    def fetch_supplier_fixture(
        self, principal: Principal, sku_id: str, supplier_id: str
    ) -> dict[str, object] | None: ...


class EvidenceTools:
    def __init__(self, repository: FixtureReader, *, manifest_version: str) -> None:
        self.repository = repository
        self.manifest_version = manifest_version

    def inventory(
        self, principal: Principal, *, sku_id: str, store_id: str, as_of_ts: datetime
    ) -> InventoryEvidence:
        row = self.repository.fetch_inventory_fixture(principal, sku_id, store_id)
        if row is None:
            raise EvidenceFailure("EVIDENCE_MISSING", "T1 inventory evidence is missing")
        facts = {
            "sku_id": row["sku_id"],
            "store_id": row["store_id"],
            "on_hand": float(row["on_hand"]),
            "reserved": float(row["reserved"]),
            "on_order": float(row["on_order"]),
            "updated_at": row["updated_at"],
        }
        query = {"sku_id": sku_id, "store_id": store_id, "as_of_ts": as_of_ts}
        source_ref = f"inventory:{principal.tenant_id}:{sku_id}:{store_id}"
        return InventoryEvidence(
            tool_schema_version="v1",
            tool="T1_inventory",
            **facts,
            **provenance_fields(
                source_ref=source_ref,
                query=query,
                facts=facts,
                retrieved_at=as_of_ts,
                freshness_ts=row["updated_at"],
                fixture_manifest_version=self.manifest_version,
            ),
        )

    def demand(
        self,
        principal: Principal,
        *,
        sku_id: str,
        store_id: str,
        window_start: datetime,
        window_end: datetime,
        as_of_ts: datetime,
    ) -> DemandEvidence:
        row = self.repository.fetch_demand_fixture(
            principal, sku_id, store_id, window_start, window_end
        )
        if row is None:
            raise EvidenceFailure("EVIDENCE_MISSING", "T2 demand evidence is missing")
        facts = {
            "sku_id": row["sku_id"],
            "store_id": row["store_id"],
            "units_sold": float(row["units_sold"]),
            "average_daily_units": float(row["average_daily_units"]),
            "demand_signal": row["demand_signal"],
            "updated_at": row["updated_at"],
        }
        query = {
            "sku_id": sku_id,
            "store_id": store_id,
            "window_start": window_start,
            "window_end": window_end,
            "as_of_ts": as_of_ts,
        }
        source_ref = (
            f"demand:{principal.tenant_id}:{sku_id}:{store_id}:"
            f"{window_start.isoformat()}:{window_end.isoformat()}"
        )
        return DemandEvidence(
            tool_schema_version="v1",
            tool="T2_sales_demand",
            **facts,
            **provenance_fields(
                source_ref=source_ref,
                query=query,
                facts=facts,
                retrieved_at=as_of_ts,
                freshness_ts=row["updated_at"],
                fixture_manifest_version=self.manifest_version,
            ),
        )

    def supplier(
        self,
        principal: Principal,
        *,
        sku_id: str,
        supplier_id: str,
        as_of_ts: datetime,
    ) -> SupplierEvidence:
        row = self.repository.fetch_supplier_fixture(principal, sku_id, supplier_id)
        if row is None:
            raise EvidenceFailure("EVIDENCE_MISSING", "T3 supplier evidence is missing")
        facts = {
            "sku_id": row["sku_id"],
            "supplier_id": row["supplier_id"],
            "open_order_quantity": float(row["open_order_quantity"]),
            "expected_receipt_at": row["expected_receipt_at"],
            "historical_lead_time_days": float(row["historical_lead_time_days"]),
            "status": row["status"],
            "updated_at": row["updated_at"],
        }
        query = {"sku_id": sku_id, "supplier_id": supplier_id, "as_of_ts": as_of_ts}
        source_ref = f"supplier:{principal.tenant_id}:{sku_id}:{supplier_id}"
        return SupplierEvidence(
            tool_schema_version="v1",
            tool="T3_supplier",
            **facts,
            **provenance_fields(
                source_ref=source_ref,
                query=query,
                facts=facts,
                retrieved_at=as_of_ts,
                freshness_ts=row["updated_at"],
                fixture_manifest_version=self.manifest_version,
            ),
        )
