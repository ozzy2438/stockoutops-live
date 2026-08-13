"""Deterministic M1 control spine; the model owns no control decisions."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from pydantic import ValidationError as PydanticValidationError

from stockoutops.errors import (
    AuthorizationError,
    ConflictError,
    StockoutOpsError,
    ValidationError,
)
from stockoutops.evidence.contracts import (
    Evidence,
    EvidenceFailure,
    parse_evidence,
    validate_bundle,
)
from stockoutops.evidence.provenance import canonical_hash
from stockoutops.evidence.tools import EvidenceTools
from stockoutops.identity import IdentityProvider, Principal
from stockoutops.reasoning.base import ReasoningAdapter, ReasoningFailure, ReasoningOutcome
from stockoutops.reasoning.schemas import ReasoningResult, validate_citations
from stockoutops.repository import Repository, RunRecord
from stockoutops.schemas import IntakeRequest, ReviewRequest
from stockoutops.state_machine import RunState

Clock = Callable[[], datetime]
REVIEW_POLICY = timedelta(hours=24)


def utc_now() -> datetime:
    return datetime.now(UTC)


class InvestigationService:
    def __init__(
        self,
        repository: Repository,
        evidence_tools: EvidenceTools,
        reasoning: ReasoningAdapter,
        identity_provider: IdentityProvider,
        *,
        clock: Clock = utc_now,
    ) -> None:
        self.repository = repository
        self.evidence_tools = evidence_tools
        self.reasoning = reasoning
        self.identity_provider = identity_provider
        self.clock = clock

    def intake(
        self,
        principal: Principal,
        request: IntakeRequest,
        *,
        idempotency_key: str,
        run_mode: Literal["human_review", "shadow"] = "human_review",
    ) -> tuple[RunRecord, bool]:
        if not principal.has_role("operator"):
            raise AuthorizationError("Operator role is required for intake")
        if not idempotency_key or len(idempotency_key) > 200:
            raise ValidationError(
                "INVALID_IDEMPOTENCY_KEY", "Idempotency-Key must contain 1-200 characters"
            )
        payload_hash = canonical_hash(request.model_dump(mode="json"))
        run, created = self.repository.begin_intake(
            principal,
            request,
            idempotency_key=idempotency_key,
            payload_hash=payload_hash,
            assigned_reviewer_id=self.identity_provider.assigned_reviewer(principal.tenant_id),
            now=self.clock(),
            run_mode=run_mode,
        )
        return self._resume(principal, run), created

    def _resume(self, principal: Principal, run: RunRecord) -> RunRecord:
        while True:
            try:
                return self._resume_step(principal, run)
            except ConflictError as exc:
                if exc.code != "STATE_VERSION_CONFLICT":
                    raise
                # A concurrent idempotent-replay caller already applied this
                # exact transition; converge on the current row instead of
                # surfacing an error for what is, from the caller's
                # perspective, a duplicate of the same accepted request.
                run = self.repository.get_run(principal, run.run_id)

    def _resume_step(self, principal: Principal, run: RunRecord) -> RunRecord:
        while True:
            if run.state == RunState.CREATED:
                run = self.repository.transition(
                    principal,
                    run,
                    RunState.VALIDATING,
                    event_type="validation_started",
                    now=self.clock(),
                )
            elif run.state == RunState.VALIDATING:
                run = self.repository.transition(
                    principal,
                    run,
                    RunState.GATHERING_EVIDENCE,
                    event_type="evidence_gathering_started",
                    now=self.clock(),
                )
            elif run.state == RunState.GATHERING_EVIDENCE:
                try:
                    self._gather_evidence(principal, run)
                except EvidenceFailure as exc:
                    return self._escalate(principal, run, exc.code)
                run = self.repository.transition(
                    principal,
                    run,
                    RunState.QUALITY_CHECKS,
                    event_type="evidence_gathered",
                    now=self.clock(),
                )
            elif run.state == RunState.QUALITY_CHECKS:
                try:
                    validate_bundle(
                        self.repository.list_evidence(principal, run.run_id),
                        as_of_ts=run.as_of_ts,
                    )
                except (EvidenceFailure, PydanticValidationError) as exc:
                    code = getattr(exc, "code", "EVIDENCE_SCHEMA_INVALID")
                    return self._escalate(principal, run, code)
                run = self.repository.transition(
                    principal,
                    run,
                    RunState.REASONING,
                    event_type="quality_checks_passed",
                    now=self.clock(),
                )
            elif run.state == RunState.REASONING:
                try:
                    self._reason_once(principal, run)
                except ReasoningFailure as exc:
                    return self._escalate(principal, run, exc.code)
                run = self.repository.transition(
                    principal,
                    run,
                    RunState.DRAFTING_RECOMMENDATION,
                    event_type="reasoning_completed",
                    now=self.clock(),
                )
            elif run.state == RunState.DRAFTING_RECOMMENDATION:
                invocation = self.repository.get_tool(principal, run.run_id, "reasoning")
                if not invocation or invocation["status"] != "completed":
                    return self._escalate(principal, run, "REASONING_RESULT_UNAVAILABLE")
                try:
                    result = ReasoningResult.model_validate(invocation["result_json"])
                    evidence = self.repository.list_evidence(principal, run.run_id)
                    validate_citations(result, {item.evidence_id for item in evidence})
                except (PydanticValidationError, ValueError):
                    return self._escalate(principal, run, "INVALID_REASONING_OUTPUT")
                draft = result.model_dump(mode="json")
                draft_hash = canonical_hash(draft)
                now = self.clock()
                run = self.repository.set_draft_and_transition(
                    principal,
                    run,
                    draft=draft,
                    draft_hash=draft_hash,
                    now=now,
                    expires_at=now + REVIEW_POLICY,
                )
            else:
                return run

    @staticmethod
    def _forbidden_retry_code(existing: dict[str, object], default: str) -> str:
        """Read back the true originating failure code from an already-
        failed tool_invocation, instead of a generic *_RETRY_FORBIDDEN, so a
        duplicate caller's escalation reflects what actually went wrong
        rather than misreporting it as a retry-policy rejection. Falls back
        to `default` for a row that never reached 'failed' (e.g. an
        abandoned 'started' row from a crashed attempt)."""
        if existing["status"] == "failed":
            metadata = existing.get("metadata_json") or {}
            return metadata.get("error_code", default)
        return default

    def _gather_evidence(self, principal: Principal, run: RunRecord) -> list[Evidence]:
        specs = (
            (
                "T1_inventory",
                {
                    "sku_id": run.sku_id,
                    "store_id": run.store_id,
                    "as_of_ts": run.as_of_ts,
                },
                lambda: self.evidence_tools.inventory(
                    principal,
                    sku_id=run.sku_id,
                    store_id=run.store_id,
                    as_of_ts=run.as_of_ts,
                ),
            ),
            (
                "T2_sales_demand",
                {
                    "sku_id": run.sku_id,
                    "store_id": run.store_id,
                    "window_start": run.window_start,
                    "window_end": run.window_end,
                    "as_of_ts": run.as_of_ts,
                },
                lambda: self.evidence_tools.demand(
                    principal,
                    sku_id=run.sku_id,
                    store_id=run.store_id,
                    window_start=run.window_start,
                    window_end=run.window_end,
                    as_of_ts=run.as_of_ts,
                ),
            ),
            (
                "T3_supplier",
                {
                    "sku_id": run.sku_id,
                    "supplier_id": run.supplier_id,
                    "as_of_ts": run.as_of_ts,
                },
                lambda: self.evidence_tools.supplier(
                    principal,
                    sku_id=run.sku_id,
                    supplier_id=run.supplier_id,
                    as_of_ts=run.as_of_ts,
                ),
            ),
        )
        evidence: list[Evidence] = []
        for tool_name, query, invoke in specs:
            existing, claim = self.repository.claim_or_observe_tool(
                principal,
                run.run_id,
                tool_name=tool_name,
                request_hash=canonical_hash(query),
                now=self.clock(),
            )
            if claim is None:
                if existing["status"] == "completed" and existing["result_json"] is not None:
                    evidence.append(parse_evidence(existing["result_json"]))
                    continue
                raise EvidenceFailure(
                    self._forbidden_retry_code(existing, "EVIDENCE_RETRY_FORBIDDEN"),
                    f"{tool_name} was already attempted and will not be retried",
                )
            with claim:
                try:
                    item = invoke()
                except EvidenceFailure as exc:
                    self.repository.complete_tool(
                        principal,
                        run.run_id,
                        tool_name=tool_name,
                        result=None,
                        metadata={"error_code": exc.code},
                        status="failed",
                        now=self.clock(),
                    )
                    raise
                self.repository.complete_tool(
                    principal,
                    run.run_id,
                    tool_name=tool_name,
                    result=item.model_dump(mode="json"),
                    metadata={"evidence_id": item.evidence_id},
                    status="completed",
                    now=self.clock(),
                )
                evidence.append(item)
        return evidence

    def _reason_outcome_from_row(self, row: dict[str, object]) -> ReasoningOutcome:
        result = ReasoningResult.model_validate(row["result_json"])
        metadata = row["metadata_json"]
        return ReasoningOutcome(
            result=result,
            model_id=metadata["model_id"],
            prompt_hash=metadata["prompt_hash"],
            input_hash=metadata["input_hash"],
            output_hash=metadata["output_hash"],
            input_tokens=metadata.get("input_tokens"),
            output_tokens=metadata.get("output_tokens"),
            latency_ms=metadata["latency_ms"],
            estimated_cost_usd=metadata.get("estimated_cost_usd"),
        )

    def _reason_once(self, principal: Principal, run: RunRecord) -> ReasoningOutcome:
        evidence = self.repository.list_evidence(principal, run.run_id)
        request_hash = canonical_hash([item.model_dump(mode="json") for item in evidence])
        existing, claim = self.repository.claim_or_observe_tool(
            principal,
            run.run_id,
            tool_name="reasoning",
            request_hash=request_hash,
            now=self.clock(),
        )
        if claim is None:
            if existing["status"] == "completed" and existing["result_json"]:
                return self._reason_outcome_from_row(existing)
            raise ReasoningFailure(
                self._forbidden_retry_code(existing, "REASONING_RETRY_FORBIDDEN"),
                "A reasoning invocation already exists and will not be retried",
            )
        with claim:
            try:
                outcome = self.reasoning.reason(evidence)
                validate_citations(outcome.result, {item.evidence_id for item in evidence})
            except (ReasoningFailure, ValueError) as exc:
                code = getattr(exc, "code", "INVALID_REASONING_OUTPUT")
                self.repository.complete_tool(
                    principal,
                    run.run_id,
                    tool_name="reasoning",
                    result=None,
                    metadata={"error_code": code},
                    status="failed",
                    now=self.clock(),
                )
                if isinstance(exc, ReasoningFailure):
                    raise
                raise ReasoningFailure(code, "Reasoning citation validation failed") from exc
            metadata = {
                "model_id": outcome.model_id,
                "prompt_hash": outcome.prompt_hash,
                "input_hash": outcome.input_hash,
                "output_hash": outcome.output_hash,
                "input_tokens": outcome.input_tokens,
                "output_tokens": outcome.output_tokens,
                "latency_ms": outcome.latency_ms,
                "estimated_cost_usd": outcome.estimated_cost_usd,
            }
            self.repository.complete_tool(
                principal,
                run.run_id,
                tool_name="reasoning",
                result=outcome.result.model_dump(mode="json"),
                metadata=metadata,
                status="completed",
                now=self.clock(),
            )
            return outcome

    def _escalate(self, principal: Principal, run: RunRecord, code: str) -> RunRecord:
        return self.repository.transition(
            principal,
            run,
            RunState.ESCALATED,
            event_type="run_escalated",
            now=self.clock(),
            payload={"code": code},
        )

    def review(
        self,
        principal: Principal,
        run_id: UUID | str,
        request: ReviewRequest,
        *,
        idempotency_key: str,
    ) -> RunRecord:
        if not principal.has_role("reviewer"):
            with suppress(StockoutOpsError):
                self.repository.append_rejected_control(
                    principal, run_id, code="REVIEWER_ROLE_REQUIRED", now=self.clock()
                )
            raise AuthorizationError("Reviewer role is required")
        if not idempotency_key or len(idempotency_key) > 200:
            raise ValidationError(
                "INVALID_IDEMPOTENCY_KEY", "Idempotency-Key must contain 1-200 characters"
            )
        edited_payload = None
        edited_hash = None
        if request.edited_payload is not None:
            try:
                edited = ReasoningResult.model_validate(request.edited_payload)
                evidence = self.repository.list_evidence(principal, UUID(str(run_id)))
                validate_citations(edited, {item.evidence_id for item in evidence})
            except (PydanticValidationError, ValueError) as exc:
                self.repository.append_rejected_control(
                    principal, run_id, code="INVALID_EDITED_PAYLOAD", now=self.clock()
                )
                raise ValidationError(
                    "INVALID_EDITED_PAYLOAD",
                    "Edited payload failed strict schema or citation validation",
                ) from exc
            edited_payload = edited.model_dump(mode="json")
            edited_hash = canonical_hash(edited_payload)
        return self.repository.record_review(
            principal,
            run_id,
            idempotency_key=idempotency_key,
            action=request.action,
            submitted_draft_hash=request.draft_hash,
            edited_payload=edited_payload,
            edited_payload_hash=edited_hash,
            reason=request.reason,
            now=self.clock(),
        )

    def detail(self, principal: Principal, run_id: UUID | str) -> dict[str, object]:
        run = self.repository.get_run(principal, run_id)
        evidence = self.repository.list_evidence(principal, run.run_id)
        decision = self.repository.get_decision(principal, run.run_id)
        return {
            "run_id": str(run.run_id),
            "tenant_id": run.tenant_id,
            "state": run.state.value,
            "state_version": run.state_version,
            "run_mode": run.run_mode,
            "sku_id": run.sku_id,
            "store_id": run.store_id,
            "supplier_id": run.supplier_id,
            "as_of_ts": run.as_of_ts,
            "assigned_reviewer_id": run.assigned_reviewer_id,
            "evidence": [item.model_dump(mode="json") for item in evidence],
            "draft": run.draft_json,
            "draft_hash": run.draft_hash,
            "review_expires_at": run.review_expires_at,
            "decision": decision,
        }

    def audit(self, principal: Principal, run_id: UUID | str) -> dict[str, object]:
        events = self.repository.audit(principal, run_id)
        replayed = None
        for event in events:
            # control_rejected/intake_rejected/review_rejected are recorded
            # with to_state set to whatever the run's state happened to be
            # at that rejection's own read (from_state == to_state: no
            # transition occurred). Under concurrency, a rejection's INSERT
            # can commit — and so get a later event_id — after a genuine
            # later transition's INSERT, even though its own state snapshot
            # was taken earlier. Treating every non-null to_state as the
            # latest replayed state therefore lets a stale rejection
            # overwrite the correct final state. Only a genuine transition
            # (to_state present and different from from_state) may update
            # the replayed state.
            if event["to_state"] is not None and event["to_state"] != event["from_state"]:
                replayed = event["to_state"]
        current = self.repository.get_run(principal, run_id)
        return {
            "run_id": str(current.run_id),
            "current_state": current.state.value,
            "replayed_state": replayed,
            "events": events,
        }
