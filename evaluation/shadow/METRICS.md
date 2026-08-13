# Shadow metric definitions

> Methodology note for the M2 UAT / real-shadow readiness bridge.
> Historical reports generated before this definition remain historical.

## Missing required evidence

**Canonical definition:** the number of tools listed in the case contract
field `minimum_evidence_citation_expectations.required_tools` that are absent
from the actual retrieved evidence-tool set.

- The case-specific `required_tools` set is authoritative.
- Unused T1/T2/T3 slots are not counted as missing.
- Extra retrieved tools are not treated as missing.
- `actual.missing_required_evidence_count` and
  `comparison.missing_required_evidence_count` MUST use this same function.
- The aggregate gate metric is the sum of the comparison values.

### Historical residual (do not reuse)

The merged M2-01/M2-02 processor stored `actual.missing_required_evidence_count`
as `max(0, 3 - len(set(actual_tools)))`. That three-tool-slot formula disagreed
with the aggregate/comparison metric on cases whose `required_tools` set was a
strict subset of T1–T3 (controlled-synthetic cases 007 and 008 in pack
`m2-shadow-cases-v1-2026-08-13`).

Those historical `actual.*` values must not be rewritten. New runs use the
canonical contract-derived count.

## Official M2-05 genuine-100 count

A case counts toward the official M2-05 genuine 100-case requirement only when
all of the following are true:

- `provenance_label = GENUINE_UAT_ANALYST_LABELLED`
- `baseline_source = analyst_reference`
- an append-only `accepted_for_m2_05` intake event exists
- the case was not excluded

`SIMULATED` / `controlled_synthetic_reference` cases, including the versioned
12-case pack, **never** count toward M2-05.
