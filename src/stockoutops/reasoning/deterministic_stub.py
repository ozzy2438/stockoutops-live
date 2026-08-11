"""Reproducible CI/local reasoning adapter with no network access."""

from __future__ import annotations

from collections.abc import Sequence

from stockoutops.evidence.contracts import Evidence
from stockoutops.evidence.provenance import canonical_hash
from stockoutops.reasoning.base import ReasoningOutcome
from stockoutops.reasoning.schemas import (
    ReasoningResult,
    validate_citations,
)


class DeterministicStubAdapter:
    model_id = "deterministic-stub-v1"

    def reason(self, evidence: Sequence[Evidence]) -> ReasoningOutcome:
        ordered = sorted(evidence, key=lambda item: item.tool)
        evidence_ids = [item.evidence_id for item in ordered]
        result = ReasoningResult.model_validate(
            {
                "root_cause_hypothesis": {
                    "statement": (
                        "Simulated inventory availability is below recent demand while "
                        "supplier evidence indicates replenishment timing risk."
                    ),
                    "confidence": "medium",
                    "citations": evidence_ids[:2],
                },
                "recommendation_draft": {
                    "action_type": "review_replenishment",
                    "rationale": (
                        "A human reviewer should inspect the simulated replenishment plan "
                        "against the cited inventory, demand, and supplier evidence."
                    ),
                    "citations": evidence_ids,
                },
            }
        )
        validate_citations(result, set(evidence_ids))
        input_payload = [item.model_dump(mode="json") for item in ordered]
        input_hash = canonical_hash(input_payload)
        output_hash = canonical_hash(result.model_dump(mode="json"))
        return ReasoningOutcome(
            result=result,
            model_id=self.model_id,
            prompt_hash=canonical_hash("deterministic-stub-v1"),
            input_hash=input_hash,
            output_hash=output_hash,
            input_tokens=None,
            output_tokens=None,
            latency_ms=0.0,
            estimated_cost_usd=0.0,
        )
