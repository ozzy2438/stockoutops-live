"""Deterministic, field-level shadow comparisons with no model-as-judge."""

from __future__ import annotations

from stockoutops.shadow.contracts import (
    Agreement,
    ShadowActualOutcome,
    ShadowCase,
    ShadowComparison,
    ShadowDiffEntry,
)
from stockoutops.shadow.metrics import missing_required_evidence_count


def _entry(
    field_name: str,
    expected: object,
    actual: object,
    *,
    category: str,
    agreement: Agreement | None = None,
) -> ShadowDiffEntry:
    return ShadowDiffEntry(
        field_name=field_name,
        agreement=agreement or ("exact" if expected == actual else "disagree"),
        expected=expected,
        actual=actual,
        category=category,
    )


def compare(case: ShadowCase, actual: ShadowActualOutcome) -> ShadowComparison:
    reference = case.reference_outcome
    escalation = case.reference_escalation_expectation
    expected_tools = set(case.minimum_evidence_citation_expectations.required_tools)
    actual_tools = set(actual.evidence_tools)
    covered_tools = expected_tools & actual_tools
    missing_count = missing_required_evidence_count(
        case.minimum_evidence_citation_expectations.required_tools,
        actual.evidence_tools,
    )
    missing_tools = expected_tools - actual_tools
    coverage = len(covered_tools) / len(expected_tools) if expected_tools else 1.0
    minimum_citations = case.minimum_evidence_citation_expectations.minimum_unique_citations
    unique_citations = len(set(actual.citation_ids))

    evidence_agreement: Agreement
    if not missing_tools:
        evidence_agreement = "exact"
    elif covered_tools:
        evidence_agreement = "partial"
    else:
        evidence_agreement = "disagree"

    citation_agreement: Agreement
    if unique_citations >= minimum_citations:
        citation_agreement = "exact"
    elif unique_citations:
        citation_agreement = "partial"
    else:
        citation_agreement = "disagree"

    entries = [
        _entry(
            "state",
            reference.expected_state,
            actual.state,
            category="outcome_state",
        ),
        _entry(
            "escalated",
            escalation.expected,
            actual.escalated,
            category="escalation",
        ),
        _entry(
            "escalation_code",
            escalation.code,
            actual.escalation_code,
            category="escalation",
        ),
        _entry(
            "root_cause_statement",
            reference.root_cause_statement,
            actual.root_cause_statement,
            category="root_cause",
        ),
        _entry(
            "recommendation_action_type",
            reference.recommendation_action_type,
            actual.recommendation_action_type,
            category="recommendation",
        ),
        _entry(
            "confidence",
            reference.confidence,
            actual.confidence,
            category="confidence",
        ),
        _entry(
            "schema_valid",
            True,
            actual.schema_valid,
            category="schema",
        ),
        _entry(
            "required_evidence_tools",
            sorted(expected_tools),
            sorted(actual_tools),
            category="evidence_coverage",
            agreement=evidence_agreement,
        ),
        _entry(
            "minimum_unique_citations",
            minimum_citations,
            unique_citations,
            category="citation_coverage",
            agreement=citation_agreement,
        ),
        _entry(
            "unsupported_citation_count",
            0,
            actual.unsupported_citation_count,
            category="unsupported_claim",
        ),
        _entry(
            "external_action_count",
            0,
            actual.external_action_count,
            category="execute_false_control",
        ),
    ]
    disagreements = sorted({entry.category for entry in entries if entry.agreement != "exact"})
    return ShadowComparison(
        exact_agreement=not disagreements,
        entries=entries,
        disagreement_categories=disagreements,
        unsupported_citation_count=actual.unsupported_citation_count,
        missing_required_evidence_count=missing_count,
        citation_coverage=coverage,
    )
