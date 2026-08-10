"""Strict v1 contracts for the three M1 evidence classes."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from stockoutops.evidence.provenance import canonical_hash, expected_evidence_id


class EvidenceBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_schema_version: Literal["v1"]
    evidence_id: str = Field(min_length=67, max_length=67, pattern=r"^ev_[0-9a-f]{64}$")
    source_type: Literal["postgres_fixture"]
    source_ref: str = Field(min_length=1, max_length=300)
    query_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    retrieved_at: datetime
    freshness_ts: datetime
    fixture_manifest_version: str = Field(min_length=1, max_length=80)


class InventoryEvidence(EvidenceBase):
    tool: Literal["T1_inventory"]
    sku_id: str = Field(min_length=1)
    store_id: str = Field(min_length=1)
    on_hand: float = Field(ge=0)
    reserved: float = Field(ge=0)
    on_order: float = Field(ge=0)
    updated_at: datetime


class DemandEvidence(EvidenceBase):
    tool: Literal["T2_sales_demand"]
    sku_id: str = Field(min_length=1)
    store_id: str = Field(min_length=1)
    units_sold: float = Field(ge=0)
    average_daily_units: float = Field(ge=0)
    demand_signal: str = Field(min_length=1, max_length=80)
    updated_at: datetime


class SupplierEvidence(EvidenceBase):
    tool: Literal["T3_supplier"]
    sku_id: str = Field(min_length=1)
    supplier_id: str = Field(min_length=1)
    open_order_quantity: float = Field(ge=0)
    expected_receipt_at: datetime
    historical_lead_time_days: float = Field(ge=0)
    status: str = Field(min_length=1, max_length=80)
    updated_at: datetime


Evidence = Annotated[
    InventoryEvidence | DemandEvidence | SupplierEvidence,
    Field(discriminator="tool"),
]
EVIDENCE_ADAPTER = TypeAdapter(Evidence)

FRESHNESS_LIMITS = {
    "T1_inventory": timedelta(hours=24),
    "T2_sales_demand": timedelta(hours=48),
    "T3_supplier": timedelta(hours=72),
}

_FACT_FIELDS = {
    "T1_inventory": (
        "sku_id",
        "store_id",
        "on_hand",
        "reserved",
        "on_order",
        "updated_at",
    ),
    "T2_sales_demand": (
        "sku_id",
        "store_id",
        "units_sold",
        "average_daily_units",
        "demand_signal",
        "updated_at",
    ),
    "T3_supplier": (
        "sku_id",
        "supplier_id",
        "open_order_quantity",
        "expected_receipt_at",
        "historical_lead_time_days",
        "status",
        "updated_at",
    ),
}


class EvidenceFailure(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def parse_evidence(payload: dict[str, object]) -> Evidence:
    return EVIDENCE_ADAPTER.validate_python(payload)


def validate_bundle(bundle: list[Evidence], *, as_of_ts: datetime) -> None:
    expected_tools = set(FRESHNESS_LIMITS)
    actual_tools = [item.tool for item in bundle]
    if len(actual_tools) != 3 or set(actual_tools) != expected_tools:
        raise EvidenceFailure("EVIDENCE_INCOMPLETE", "T1, T2 and T3 evidence are all required")
    if len(set(actual_tools)) != len(actual_tools):
        raise EvidenceFailure("EVIDENCE_DUPLICATE", "Evidence tools must be unique")

    for item in bundle:
        if item.retrieved_at.tzinfo is None or item.freshness_ts.tzinfo is None:
            raise EvidenceFailure("PROVENANCE_INVALID", "Provenance timestamps must be aware")
        facts = {field: getattr(item, field) for field in _FACT_FIELDS[item.tool]}
        if canonical_hash(facts) != item.content_hash:
            raise EvidenceFailure("PROVENANCE_INVALID", "Content hash does not match evidence")
        if expected_evidence_id(item.source_ref, item.content_hash) != item.evidence_id:
            raise EvidenceFailure("PROVENANCE_INVALID", "Evidence ID is not deterministic")
        age = as_of_ts - item.freshness_ts
        if age < timedelta(0) or age > FRESHNESS_LIMITS[item.tool]:
            raise EvidenceFailure("EVIDENCE_STALE", f"{item.tool} evidence is outside policy")
