"""Canonical shadow measurement helpers derived from the case contract.

The case-specific ``required_tools`` set is the sole definition of missing
required evidence. Do not count unused T1/T2/T3 slots.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

BOUNDED_EVIDENCE_TOOLS = frozenset({"T1_inventory", "T2_sales_demand", "T3_supplier"})


def missing_required_evidence_count(
    required_tools: Sequence[str] | Iterable[str],
    actual_tools: Sequence[str] | Iterable[str],
) -> int:
    """Return how many contract-required tools are absent from actual evidence.

    Extra retrieved tools do not reduce or increase this count. Historical
    ``actual.missing_required_evidence_count`` values that used
    ``max(0, 3 - len(set(actual_tools)))`` are not this definition and must
    remain labelled historical.
    """

    required = list(required_tools)
    if not required:
        raise ValueError("required_tools must contain at least one bounded evidence tool")
    if len(required) != len(set(required)):
        raise ValueError("required_tools must be unique")
    unknown = set(required) - BOUNDED_EVIDENCE_TOOLS
    if unknown:
        raise ValueError(
            f"required_tools contains tools outside the T1-T3 boundary: {sorted(unknown)}"
        )
    return len(set(required) - set(actual_tools))
