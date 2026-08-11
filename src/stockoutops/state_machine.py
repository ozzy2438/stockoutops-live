"""Frozen M1 transition table owned by the deterministic control spine."""

from __future__ import annotations

from enum import StrEnum
from types import MappingProxyType


class RunState(StrEnum):
    CREATED = "created"
    VALIDATING = "validating"
    GATHERING_EVIDENCE = "gathering_evidence"
    QUALITY_CHECKS = "quality_checks"
    REASONING = "reasoning"
    DRAFTING_RECOMMENDATION = "drafting_recommendation"
    AWAITING_HUMAN = "awaiting_human"
    APPROVED = "approved"
    EDITED_AND_APPROVED = "edited_and_approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"
    CLOSED = "closed"
    FAILED_AUTHZ = "failed_authz"


_TRANSITIONS = {
    RunState.CREATED: frozenset({RunState.VALIDATING, RunState.FAILED_AUTHZ}),
    RunState.VALIDATING: frozenset(
        {RunState.GATHERING_EVIDENCE, RunState.ESCALATED, RunState.FAILED_AUTHZ}
    ),
    RunState.GATHERING_EVIDENCE: frozenset({RunState.QUALITY_CHECKS, RunState.ESCALATED}),
    RunState.QUALITY_CHECKS: frozenset({RunState.REASONING, RunState.ESCALATED}),
    RunState.REASONING: frozenset({RunState.DRAFTING_RECOMMENDATION, RunState.ESCALATED}),
    RunState.DRAFTING_RECOMMENDATION: frozenset({RunState.AWAITING_HUMAN, RunState.ESCALATED}),
    RunState.AWAITING_HUMAN: frozenset(
        {
            RunState.APPROVED,
            RunState.EDITED_AND_APPROVED,
            RunState.REJECTED,
            RunState.ESCALATED,
        }
    ),
    RunState.APPROVED: frozenset({RunState.CLOSED}),
    RunState.EDITED_AND_APPROVED: frozenset({RunState.CLOSED}),
    RunState.REJECTED: frozenset({RunState.CLOSED}),
    RunState.ESCALATED: frozenset({RunState.CLOSED}),
    RunState.CLOSED: frozenset(),
    RunState.FAILED_AUTHZ: frozenset(),
}

TRANSITIONS = MappingProxyType(_TRANSITIONS)
DECISION_STATES = frozenset(
    {
        RunState.APPROVED,
        RunState.EDITED_AND_APPROVED,
        RunState.REJECTED,
        RunState.ESCALATED,
    }
)


def can_transition(current: RunState, target: RunState) -> bool:
    return target in TRANSITIONS[current]
