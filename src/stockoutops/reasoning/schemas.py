"""Strict model-independent reasoning output contract."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictReasoningModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RootCauseHypothesis(StrictReasoningModel):
    statement: str = Field(min_length=1, max_length=600)
    confidence: Literal["low", "medium", "high"]
    citations: list[str] = Field(min_length=1, max_length=3)


class RecommendationDraft(StrictReasoningModel):
    action_type: Literal[
        "monitor",
        "review_replenishment",
        "review_transfer",
        "escalate_manual_investigation",
    ]
    rationale: str = Field(min_length=1, max_length=1000)
    citations: list[str] = Field(min_length=1, max_length=3)


class ReasoningResult(StrictReasoningModel):
    root_cause_hypothesis: RootCauseHypothesis
    recommendation_draft: RecommendationDraft


REASONING_JSON_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["root_cause_hypothesis", "recommendation_draft"],
    "properties": {
        "root_cause_hypothesis": {
            "type": "object",
            "additionalProperties": False,
            "required": ["statement", "confidence", "citations"],
            "properties": {
                "statement": {"type": "string", "minLength": 1, "maxLength": 600},
                "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                "citations": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 3,
                    "items": {"type": "string"},
                },
            },
        },
        "recommendation_draft": {
            "type": "object",
            "additionalProperties": False,
            "required": ["action_type", "rationale", "citations"],
            "properties": {
                "action_type": {
                    "type": "string",
                    "enum": [
                        "monitor",
                        "review_replenishment",
                        "review_transfer",
                        "escalate_manual_investigation",
                    ],
                },
                "rationale": {"type": "string", "minLength": 1, "maxLength": 1000},
                "citations": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 3,
                    "items": {"type": "string"},
                },
            },
        },
    },
}


def validate_citations(result: ReasoningResult, evidence_ids: set[str]) -> None:
    citations = result.root_cause_hypothesis.citations + result.recommendation_draft.citations
    if any(citation not in evidence_ids for citation in citations):
        raise ValueError("Reasoning output contains an unknown evidence citation")
