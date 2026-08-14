"""Execute-false processor built on the existing bounded M1 analysis path."""

from __future__ import annotations

from uuid import UUID

from pydantic import ValidationError as PydanticValidationError

from stockoutops.errors import AuthorizationError, NotFoundError, ValidationError
from stockoutops.evidence.provenance import canonical_hash
from stockoutops.identity import Principal
from stockoutops.reasoning.schemas import ReasoningResult, validate_citations
from stockoutops.service import Clock, InvestigationService, utc_now
from stockoutops.shadow.contracts import (
    ShadowActualOutcome,
    ShadowCase,
    ShadowComparison,
    ShadowResult,
)
from stockoutops.shadow.diff import compare
from stockoutops.shadow.metrics import missing_required_evidence_count
from stockoutops.shadow.repository import ShadowRepository, ShadowRunRecord
from stockoutops.state_machine import RunState

PROCESSOR_VERSION = "m2-shadow-processor-v1.1"
PROMPT_VERSION = "m1-bounded-reasoning-v1"
TOOL_SCHEMA_VERSION = "v1"


class ShadowService:
    def __init__(
        self,
        repository: ShadowRepository,
        investigation_service: InvestigationService,
        *,
        clock: Clock = utc_now,
    ) -> None:
        self.repository = repository
        self.investigation_service = investigation_service
        self.clock = clock

    @staticmethod
    def _result_from_record(run: ShadowRunRecord, *, replay: bool) -> ShadowResult:
        if (
            run.investigation_run_id is None
            or run.output_json is None
            or run.diff_json is None
            or run.output_hash is None
            or run.diff_hash is None
        ):
            raise RuntimeError("Completed shadow record is missing its persisted result")
        return ShadowResult(
            shadow_run_id=run.shadow_run_id,
            investigation_run_id=run.investigation_run_id,
            case_id=run.case_id,
            case_version=run.case_version,
            case_pack_version=run.case_pack_version,
            tenant_id=run.tenant_id,
            processor_version=run.processor_version,
            prompt_version=run.prompt_version,
            tool_schema_version="v1",
            provenance_label=run.provenance_label,
            baseline_source=run.baseline_source,
            output_hash=run.output_hash,
            diff_hash=run.diff_hash,
            actual=ShadowActualOutcome.model_validate(run.output_json),
            comparison=ShadowComparison.model_validate(run.diff_json),
            idempotent_replay=replay,
        )

    def process(
        self,
        principal: Principal,
        case: ShadowCase,
        *,
        case_pack_version: str,
        idempotency_key: str,
        execute: bool = False,
    ) -> ShadowResult:
        if execute is not False:
            raise ValidationError(
                "SHADOW_EXECUTION_FORBIDDEN",
                "M2 shadow processing is permanently hard-locked to execute=false",
            )
        if principal.tenant_id != case.tenant_id:
            raise NotFoundError()
        if not principal.has_role("operator"):
            raise AuthorizationError("Shadow processing requires the simulated operator role")
        if not idempotency_key or len(idempotency_key) > 200:
            raise ValidationError(
                "INVALID_IDEMPOTENCY_KEY", "Idempotency key must contain 1-200 characters"
            )
        if self.investigation_service.evidence_tools.manifest_version != case_pack_version:
            raise ValidationError(
                "SHADOW_CASE_PACK_MISMATCH",
                "Runtime evidence provenance must use the verified shadow case-pack version",
            )

        payload_hash = canonical_hash(
            {
                "case": case.model_dump(mode="json"),
                "case_pack_version": case_pack_version,
                "processor_version": PROCESSOR_VERSION,
                "prompt_version": PROMPT_VERSION,
                "tool_schema_version": TOOL_SCHEMA_VERSION,
                "execute": False,
            }
        )
        run, claim, _created = self.repository.begin_or_observe(
            principal,
            idempotency_key=idempotency_key,
            payload_hash=payload_hash,
            case_id=case.case_id,
            case_version=case.case_version,
            case_pack_version=case_pack_version,
            processor_version=PROCESSOR_VERSION,
            prompt_version=PROMPT_VERSION,
            provenance_label=case.provenance_label,
            baseline_source=case.baseline_source,
            now=self.clock(),
        )
        if claim is None:
            return self._result_from_record(run, replay=True)

        with claim:
            investigation, _ = self.investigation_service.intake(
                principal,
                case.input,
                idempotency_key=f"shadow:{run.shadow_run_id}",
                run_mode="shadow",
            )
            actual = self._actual(principal, investigation.run_id, case=case)
            comparison = compare(case, actual)
            if actual.missing_required_evidence_count != comparison.missing_required_evidence_count:
                raise RuntimeError(
                    "Canonical missing-required-evidence counts diverged between "
                    "actual and comparison"
                )
            output_hash = canonical_hash(actual.model_dump(mode="json"))
            diff_hash = canonical_hash(comparison.model_dump(mode="json"))
            completed = self.repository.complete(
                principal,
                run,
                investigation_run_id=investigation.run_id,
                actual=actual,
                comparison=comparison,
                output_hash=output_hash,
                diff_hash=diff_hash,
                completed_at=self.clock(),
            )
        return self._result_from_record(completed, replay=False)

    def _actual(
        self,
        principal: Principal,
        investigation_run_id: UUID,
        *,
        case: ShadowCase,
    ) -> ShadowActualOutcome:
        detail = self.investigation_service.detail(principal, investigation_run_id)
        audit = self.investigation_service.audit(principal, investigation_run_id)
        evidence = detail["evidence"]
        evidence_ids = [item["evidence_id"] for item in evidence]
        evidence_tools = [item["tool"] for item in evidence]
        evidence_id_set = set(evidence_ids)
        draft = detail["draft"]
        schema_valid = True
        citation_ids: list[str] = []
        root_statement = None
        action_type = None
        confidence = None
        if draft is not None:
            try:
                reasoning = ReasoningResult.model_validate(draft)
                validate_citations(reasoning, evidence_id_set)
                root_statement = reasoning.root_cause_hypothesis.statement
                confidence = reasoning.root_cause_hypothesis.confidence
                action_type = reasoning.recommendation_draft.action_type
                citation_ids = (
                    reasoning.root_cause_hypothesis.citations
                    + reasoning.recommendation_draft.citations
                )
            except (PydanticValidationError, ValueError):
                schema_valid = False

        unsupported = len(set(citation_ids) - evidence_id_set)
        reasoning_invocation = self.investigation_service.repository.get_tool(
            principal, investigation_run_id, "reasoning"
        )
        reasoning_invoked = reasoning_invocation is not None
        metadata = reasoning_invocation["metadata_json"] if reasoning_invocation else {}
        provider_label = metadata.get("model_id", "not-invoked")
        latency_ms = float(metadata.get("latency_ms", 0.0))
        estimated_cost = metadata.get("estimated_cost_usd")
        cost_label = "SIMULATED" if reasoning_invoked else "UNMEASURED"
        escalated = detail["state"] == RunState.ESCALATED.value
        escalation_code = None
        if escalated:
            escalation_events = [
                event for event in audit["events"] if event["event_type"] == "run_escalated"
            ]
            if escalation_events:
                escalation_code = escalation_events[-1]["payload"].get("code")

        return ShadowActualOutcome(
            state=detail["state"],
            escalated=escalated,
            escalation_code=escalation_code,
            root_cause_statement=root_statement,
            recommendation_action_type=action_type,
            confidence=confidence,
            evidence_tools=evidence_tools,
            evidence_ids=evidence_ids,
            citation_ids=citation_ids,
            unsupported_citation_count=unsupported,
            missing_required_evidence_count=missing_required_evidence_count(
                case.minimum_evidence_citation_expectations.required_tools,
                evidence_tools,
            ),
            citation_coverage=(
                len(set(citation_ids) & evidence_id_set) / len(evidence_id_set)
                if evidence_id_set
                else 0.0
            ),
            schema_valid=schema_valid,
            reasoning_invoked=reasoning_invoked,
            provider_label=provider_label,
            latency_ms=latency_ms,
            estimated_cost_usd=(float(estimated_cost) if estimated_cost is not None else None),
            cost_evidence_label=cost_label,
            execute=False,
            external_action_count=0,
        )
