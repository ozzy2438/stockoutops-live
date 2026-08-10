# 0002. Choose LLM provider & model family

- **Status:** Proposed (deferred stub — required before model-backed implementation)
- **Date:** TBD
- **Deciders:** Honey, Fizz, Osman

## Context

We need a hosted LLM with reliable function-calling and structured-output support to power the bounded reasoning step of the workflow. Constraints:

- Function-calling / tool-use with schema enforcement.
- Latency P95 ≤ 30 s for typical prompt sizes.
- Data-residency & retention terms compatible with our tenants.
- Portability: an adapter interface must allow provider swap without changing tool contracts.
- Cost caps compatible with `docs/10_observability_slo_cost.md`.

## Decision

TBD. M0 scaffold approval does not decide the provider. Complete and accept this ADR before model-backed implementation; non-model M1 planning must not assume a provider.

## Consequences

TBD.

## Alternatives considered

- Provider A — TBD.
- Provider B — TBD.
- Self-hosted open-weights — TBD (evaluated against our operational maturity).

## Follow-ups

- ADR update once decided.
- Threat-model diff (data flows to provider).
- Cost model recalibration.
