"""Strict contracts for M2 shadow cases, including future genuine UAT intake."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from stockoutops.schemas import IntakeRequest

ToolName = Literal["T1_inventory", "T2_sales_demand", "T3_supplier"]
ExpectedState = Literal["awaiting_human", "escalated"]
Agreement = Literal["exact", "partial", "disagree"]
ProvenanceLabel = Literal["SIMULATED", "GENUINE_UAT_ANALYST_LABELLED"]
BaselineSource = Literal["controlled_synthetic_reference", "analyst_reference"]
DeidentificationStatus = Literal[
    "not_applicable_controlled_synthetic",
    "deidentified_owner_attested",
]
ConsentDataUseStatus = Literal[
    "not_applicable_controlled_synthetic",
    "owner_attested_consent_held_offline",
]
CaseContractVersion = Literal["m2-shadow-case-contract-v2"]
CONSENT_REFERENCE_PATTERN = r"^OFFLINE-CONSENT-[A-Z0-9-]{8,64}$"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InventoryFixture(StrictModel):
    on_hand: float = Field(ge=0)
    reserved: float = Field(ge=0)
    on_order: float = Field(ge=0)
    updated_at: datetime


class DemandFixture(StrictModel):
    units_sold: float = Field(ge=0)
    average_daily_units: float = Field(ge=0)
    demand_signal: str = Field(min_length=1, max_length=80)
    updated_at: datetime


class SupplierFixture(StrictModel):
    open_order_quantity: float = Field(ge=0)
    expected_receipt_at: datetime
    historical_lead_time_days: float = Field(ge=0)
    status: str = Field(min_length=1, max_length=80)
    updated_at: datetime


class FixtureSetup(StrictModel):
    inventory: InventoryFixture | None
    demand: DemandFixture | None
    supplier: SupplierFixture | None


class ReferenceOutcome(StrictModel):
    expected_state: ExpectedState
    root_cause_statement: str | None
    recommendation_action_type: (
        Literal[
            "monitor",
            "review_replenishment",
            "review_transfer",
            "escalate_manual_investigation",
        ]
        | None
    )
    confidence: Literal["low", "medium", "high"] | None


class ReferenceEscalation(StrictModel):
    expected: bool
    code: str | None

    @model_validator(mode="after")
    def validate_code(self) -> ReferenceEscalation:
        if self.expected and not self.code:
            raise ValueError("Expected escalation requires a reference code")
        if not self.expected and self.code is not None:
            raise ValueError("Non-escalation reference cannot include a code")
        return self


class MinimumEvidenceExpectation(StrictModel):
    required_tools: list[ToolName] = Field(min_length=1)
    minimum_unique_citations: int = Field(ge=0, le=3)

    @model_validator(mode="after")
    def validate_tools(self) -> MinimumEvidenceExpectation:
        if len(self.required_tools) != len(set(self.required_tools)):
            raise ValueError("Required evidence tools must be unique")
        return self


class ShadowCase(StrictModel):
    case_id: str = Field(min_length=1, max_length=100)
    case_version: str = Field(pattern=r"^v[1-9][0-9]*$")
    case_contract_version: CaseContractVersion = "m2-shadow-case-contract-v2"
    category: str = Field(min_length=1, max_length=80)
    tenant_id: Literal["t_alpha", "t_beta"]
    as_of_timestamp: datetime
    execute: Literal[False]
    input: IntakeRequest
    baseline_source: BaselineSource = "controlled_synthetic_reference"
    reference_outcome: ReferenceOutcome
    reference_escalation_expectation: ReferenceEscalation
    minimum_evidence_citation_expectations: MinimumEvidenceExpectation
    provenance_label: ProvenanceLabel = "SIMULATED"
    deidentification_status: DeidentificationStatus = "not_applicable_controlled_synthetic"
    consent_data_use_status: ConsentDataUseStatus = "not_applicable_controlled_synthetic"
    consent_data_use_reference: str | None = Field(default=None, pattern=CONSENT_REFERENCE_PATTERN)
    fixture_setup: FixtureSetup
    notes: str = Field(min_length=1, max_length=1000)
    limitations: list[str] = Field(min_length=1)

    @field_validator("consent_data_use_reference", mode="before")
    @classmethod
    def empty_consent_reference_is_none(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @model_validator(mode="after")
    def validate_case(self) -> ShadowCase:
        if self.as_of_timestamp.tzinfo is None:
            raise ValueError("as_of_timestamp must include a timezone")
        if self.as_of_timestamp != self.input.as_of_ts:
            raise ValueError("as_of_timestamp must equal input.as_of_ts")
        if self.reference_escalation_expectation.expected != (
            self.reference_outcome.expected_state == "escalated"
        ):
            raise ValueError("Reference state and escalation expectation disagree")
        if self.reference_outcome.expected_state == "escalated" and any(
            value is not None
            for value in (
                self.reference_outcome.root_cause_statement,
                self.reference_outcome.recommendation_action_type,
                self.reference_outcome.confidence,
            )
        ):
            raise ValueError("Escalated references cannot include a recommendation draft")
        synthetic = self.provenance_label == "SIMULATED"
        if synthetic:
            if self.baseline_source != "controlled_synthetic_reference":
                raise ValueError("SIMULATED cases require controlled_synthetic_reference")
            if self.deidentification_status != "not_applicable_controlled_synthetic":
                raise ValueError("SIMULATED cases cannot carry a genuine de-identification status")
            if self.consent_data_use_status != "not_applicable_controlled_synthetic":
                raise ValueError("SIMULATED cases cannot carry a genuine consent status")
            if self.consent_data_use_reference is not None:
                raise ValueError("SIMULATED cases cannot carry a consent/data-use reference")
        else:
            if self.baseline_source != "analyst_reference":
                raise ValueError("Genuine UAT cases require baseline_source=analyst_reference")
            if self.deidentification_status != "deidentified_owner_attested":
                raise ValueError("Genuine UAT cases require owner-attested de-identification")
            if self.consent_data_use_status != "owner_attested_consent_held_offline":
                raise ValueError("Genuine UAT cases require offline owner-attested consent status")
            if self.consent_data_use_reference is None:
                raise ValueError(
                    "Genuine UAT cases require an opaque offline consent/data-use reference"
                )
        return self


class ShadowCasePack(StrictModel):
    case_pack_version: str = Field(
        pattern=r"^m2-shadow-cases-v[1-9][0-9]*-[0-9]{4}-[0-9]{2}-[0-9]{2}$"
    )
    evidence_label: Literal["M2 SHADOW FOUNDATION — SIMULATED ENGINEERING REHEARSAL"]
    cases: list[ShadowCase] = Field(min_length=12)

    @model_validator(mode="after")
    def validate_unique_cases(self) -> ShadowCasePack:
        identities = [(case.case_id, case.case_version) for case in self.cases]
        if len(identities) != len(set(identities)):
            raise ValueError("Case IDs and versions must be unique within a pack")
        if len({case.category for case in self.cases}) < 4:
            raise ValueError("The controlled-synthetic pack requires at least four categories")
        if any(case.provenance_label != "SIMULATED" for case in self.cases):
            raise ValueError("The controlled-synthetic pack cannot contain genuine UAT cases")
        if any(case.baseline_source != "controlled_synthetic_reference" for case in self.cases):
            raise ValueError(
                "The controlled-synthetic pack cannot contain analyst_reference baselines"
            )
        return self


class ShadowActualOutcome(StrictModel):
    state: str
    escalated: bool
    escalation_code: str | None
    root_cause_statement: str | None
    recommendation_action_type: str | None
    confidence: str | None
    evidence_tools: list[str]
    evidence_ids: list[str]
    citation_ids: list[str]
    unsupported_citation_count: int = Field(ge=0)
    missing_required_evidence_count: int = Field(ge=0)
    citation_coverage: float = Field(ge=0, le=1)
    schema_valid: bool
    reasoning_invoked: bool
    provider_label: str
    latency_ms: float = Field(ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0)
    cost_evidence_label: Literal["SIMULATED", "UNMEASURED"]
    execute: Literal[False]
    external_action_count: Literal[0]


class ShadowDiffEntry(StrictModel):
    field_name: str
    agreement: Agreement
    expected: object
    actual: object
    category: str


class ShadowComparison(StrictModel):
    exact_agreement: bool
    entries: list[ShadowDiffEntry]
    disagreement_categories: list[str]
    unsupported_citation_count: int = Field(ge=0)
    missing_required_evidence_count: int = Field(ge=0)
    citation_coverage: float = Field(ge=0, le=1)


class ShadowResult(StrictModel):
    shadow_run_id: UUID
    investigation_run_id: UUID
    case_id: str
    case_version: str
    case_pack_version: str
    tenant_id: str
    processor_version: str
    prompt_version: str
    tool_schema_version: Literal["v1"]
    provenance_label: ProvenanceLabel
    baseline_source: BaselineSource
    output_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    diff_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    actual: ShadowActualOutcome
    comparison: ShadowComparison
    idempotent_replay: bool


class ShadowIntakeDocument(StrictModel):
    intake_document_version: Literal["m2-uat-intake-v1"]
    execute: Literal[False]
    cases: list[ShadowCase] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_genuine_intake(self) -> ShadowIntakeDocument:
        identities = [(case.case_id, case.case_version, case.tenant_id) for case in self.cases]
        if len(identities) != len(set(identities)):
            raise ValueError("Intake document contains duplicate case identities")
        for case in self.cases:
            if case.provenance_label != "GENUINE_UAT_ANALYST_LABELLED":
                raise ValueError("Genuine UAT intake rejects SIMULATED cases")
            if case.baseline_source != "analyst_reference":
                raise ValueError("Genuine UAT intake requires analyst_reference baselines")
            if case.execute is not False:
                raise ValueError("Genuine UAT intake is hard-locked to execute=false")
        return self
