# 0002. Use OpenAI Responses API for the M1 reasoning boundary

- **Status:** Accepted for M1 (owner model correction recorded 2026-08-11)
- **Date:** 2026-08-10; amended 2026-08-11
- **Deciders:** Ozzy (owner), Honey (architecture), Orchestrator (scope)
- **Assurance:** Fizz review of the exact documentation PR head is required

## Context

M1 needs one bounded reasoning step after deterministic T1–T3 evidence collection. It drafts only a root-cause hypothesis and recommendation for human review. Provider choice must not give the model tool access or change the control-spine, evidence, tenancy, approval, or audit contracts.

Official OpenAI documentation lists `gpt-4.1-mini-2025-04-14` as a GPT-4.1 mini snapshot and confirms support for the Responses API and Structured Outputs. It lists standard text pricing at USD 0.40 per million input tokens, USD 0.10 per million cached-input tokens, and USD 1.60 per million output tokens. These catalogue facts do not prove project billing or model access.

Sources:

- [GPT-4.1 mini model catalogue](https://developers.openai.com/api/docs/models/gpt-4.1-mini)
- [Structured model outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [OpenAI API data controls and endpoint retention](https://developers.openai.com/api/docs/guides/your-data#default-usage-policies-by-endpoint)

## Decision

- Provider: OpenAI API.
- API: Responses API.
- Exact M1 model snapshot: `gpt-4.1-mini-2025-04-14`; no floating alias.
- Output: `text.format` JSON Schema with `type: json_schema` and `strict: true`.
- The schema permits only:
  - `root_cause_hypothesis`: statement (1–600 characters), `low|medium|high` confidence, and 1–3 citations;
  - `recommendation_draft`: `monitor|review_replenishment|review_transfer|escalate_manual_investigation` action type, rationale (1–1,000 characters), and 1–3 citations.
- Every object sets `additionalProperties: false`; every listed field is required, and each citation is an `evidence_id` string from the supplied bundle.
- The model receives the already-collected T1–T3 evidence bundle. It receives no tools, credentials, tenant authority, state-transition authority, or write capability.
- A normal run may make at most one model call. There is no automatic model retry in M1. Provider failure, timeout, budget exhaustion, refusal, invalid schema, unknown field, or invalid citation fails closed to human escalation.
- Deterministic post-response validation requires every cited `evidence_id` to exist in the pre-call bundle. Strict schema conformance is necessary but not sufficient.
- CI uses `DeterministicStubAdapter` only, with no network and no API key.
- One manual live smoke call is permitted during owner-authorised M1 implementation, immediately before the first real model call. Before it, the implementer must verify credential presence without disclosure, API authentication, project billing/access, and exact snapshot access. No other agent session requests, inspects, or inherits `OPENAI_API_KEY`.
- Every M1 Responses request must set `store: false`. Background mode is forbidden; the sole smoke is synchronous and bounded.
- Store in StockoutOps by default: model ID, prompt hash, input/output hashes, token usage, latency, and estimated cost. Do not store raw prompt or response bodies.
- The smoke result is MEASURED at n=1 for interface/latency/cost only. It is not evidence of reasoning quality, production readiness, reliability, or business impact.

M1 request caps are `max_output_tokens: 1500`, a 12,000-token application-side input ceiling, and a 30-second wall-clock timeout. Input overflow is rejected before the API call; output exhaustion or timeout escalates.

## Consequences and limitations

- The snapshot is owner-pinned for reproducibility. If pre-call access verification fails, implementation must stop and return to Ozzy; no alias or replacement model may be substituted silently.
- Pricing is a current catalogue input to an estimate, not a guaranteed invoice rate. This amendment records the catalogue verification date; the implementation records measured token usage and the resulting estimate.
- `store: false` disables Responses application-state storage for this request; it is not by itself Zero Data Retention. Unless the project has separately approved Zero Data Retention or Modified Abuse Monitoring, provider abuse-monitoring logs may contain customer content and are retained for up to 30 days by default. M1 therefore permits only simulated payloads. Real, personal, client, or tenant data is forbidden until data classification, retention, and owner approval are recorded.
- Provider fallback, quality evaluation, 34-case regression, prompt-injection corpus, PII redaction pipeline, retention policy, and production data approval remain outside M1.
- The adapter boundary remains provider-neutral; OpenAI SDK types must not leak into evidence or workflow contracts.

## Threat-model delta

- Adds one outbound trust boundary from the control spine to the allow-listed OpenAI Responses endpoint.
- Only validated simulated T1–T3 fields cross that boundary in M1; no secrets, identity tokens, raw audit records, or arbitrary retrieved text are included.
- No model-callable tools removes tool-confusion and model-initiated side effects from this slice.
- Residual risks are provider availability, deprecation/access loss, data egress, provider abuse-monitoring retention, output hallucination, latency, and cost. `store: false`, the background-mode prohibition, simulated-only payloads, timeout, strict schema, citation binding, hashing, StockoutOps metadata-only retention, and human review reduce but do not eliminate them.

## Recovery and rollback

Disable the live adapter and select the deterministic stub or human-only path. Persisted workflow state and evidence remain usable; no external write needs compensation. A future model change requires an owner-approved ADR amendment, fresh contract/regression evidence, Fizz review, and owner approval.

## Alternatives considered

- Floating OpenAI model alias: rejected because it weakens replay and version attribution.
- Self-hosted open weights: deferred; it adds hosting, security, serving, and operations work without proving the small slice.
- Deterministic stub only: retained for CI but insufficient for the separately permitted live interface smoke.

## Next gate

The implementation PR must pass exact-head CI before any sole live smoke call. The implementer then performs the credential/billing/exact-access checks immediately before that call; independent evidence, Fizz assurance, and owner merge approval remain separate gates.
