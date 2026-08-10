"""Provider-neutral reasoning interface and metadata."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from stockoutops.evidence.contracts import Evidence
from stockoutops.reasoning.schemas import ReasoningResult


class ReasoningFailure(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ReasoningOutcome:
    result: ReasoningResult
    model_id: str
    prompt_hash: str
    input_hash: str
    output_hash: str
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: float
    estimated_cost_usd: float | None


class ReasoningAdapter(Protocol):
    def reason(self, evidence: Sequence[Evidence]) -> ReasoningOutcome: ...
