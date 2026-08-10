# 0002. Use OpenAI Responses API for the M1 reasoning boundary

- **Status:** Accepted for M1 (effective after this scope-lock PR merges)
- **Date:** 2026-08-10
- **Deciders:** Ozzy (owner), Honey (architecture), Orchestrator (scope)
- **Assurance:** Fizz review of the exact documentation PR head is required

## Context

M1 needs one bounded reasoning step after deterministic T1–T3 evidence collection. It drafts only a root-cause hypothesis and recommendation for human review. Provider choice must not give the model tool access or change the control-spine, evidence, tenancy, approval, or audit contracts.

Official OpenAI documentation lists `gpt-5-nano-2025-08-07` as a GPT-5 nano snapshot, supports the Responses API and Structured Outputs, and currently marks the snapshot deprecated. It lists standard text pricing at USD 0.05 per million input tokens, USD 0.005 per million cached-input tokens, and USD 0.40 per million output tokens. These catalogue facts do not prove project billing or model access.

Sources:

- [GPT-5 nano model catalogue](https://developers.openai.com/api/docs/models/gpt-5-nano)
- [Structured model outputs](https://developers.openai.com/api/docs/guides/structured-outputs)

## Decision

- Provider: OpenAI API.
- API: Responses API.
- Exact M1 model snapshot: `gpt-5-nano-2025-08-07`; no floating alias.
- Output: `text.format` JSON Schema with `type: json_schema` and `strict: true`.
- The schema permits only:
  - `root_cause_hypothesis`: statement (1–600 characters), `low|medium|high` confidence, and 1–3 citations;
  - `recommendation_draft`: `monitor|review_replenishment|review_transfer|escalate_manual_investigation` action type, rationale (1–1,000 characters), and 1–3 citations.
- Every object sets `additionalProperties: false`; every listed field is required, and each citation is an `evidence_id` string from the supplied bundle.
- The model receives the already-collected T1–T3 evidence bundle. It receives no tools, credentials, tenant authority, state-transition authority, or write capability.
- A normal run may make at most one model call. There is no automatic model retry in M1. Provider failure, timeout, budget exhaustion, refusal, invalid schema, unknown field, or invalid citation fails closed to human escalation.
- Deterministic post-response validation requires every cited `evidence_id` to exist in the pre-call bundle. Strict schema conformance is necessary but not sufficient.
- CI uses `DeterministicStubAdapter` only, with no network and no API key.
- One manual live smoke call is permitted during Bumble's implementation milestone, immediately before the first real model call. Before it, Bumble must verify credential presence without disclosure, API authentication, project billing/access, and exact snapshot access. No other agent session requests, inspects, or inherits `OPENAI_API_KEY`.
- Store by default: model ID, prompt hash, input/output hashes, token usage, latency, and estimated cost. Do not store raw prompt or response bodies by default.
- The smoke result is MEASURED at n=1 for interface/latency/cost only. It is not evidence of reasoning quality, production readiness, reliability, or business impact.

M1 request caps are `max_output_tokens: 1500`, a 12,000-token application-side input ceiling, and a 30-second wall-clock timeout. Input overflow is rejected before the API call; output exhaustion or timeout escalates.

## Consequences and limitations

- The snapshot is owner-pinned for reproducibility but is already marked deprecated in the current official catalogue. If pre-call access verification fails, Bumble must stop and return to Ozzy; no alias or replacement model may be substituted silently.
- Pricing is a current catalogue input to an estimate, not a guaranteed invoice rate. The implementation records the price version/date and measured token usage.
- Provider fallback, quality evaluation, 34-case regression, prompt-injection corpus, PII redaction pipeline, retention policy, and production data approval remain outside M1.
- The adapter boundary remains provider-neutral; OpenAI SDK types must not leak into evidence or workflow contracts.

## Threat-model delta

- Adds one outbound trust boundary from the control spine to the allow-listed OpenAI Responses endpoint.
- Only validated simulated T1–T3 fields cross that boundary in M1; no secrets, identity tokens, raw audit records, or arbitrary retrieved text are included.
- No model-callable tools removes tool-confusion and model-initiated side effects from this slice.
- Residual risks are provider availability, deprecation/access loss, data egress, output hallucination, latency, and cost. Timeout, strict schema, citation binding, hashing, metadata-only retention, and human review reduce but do not eliminate them.

## Recovery and rollback

Disable the live adapter and select the deterministic stub or human-only path. Persisted workflow state and evidence remain usable; no external write needs compensation. A model change requires a new ADR, fresh evaluation, Fizz review, and owner approval.

## Alternatives considered

- Floating OpenAI model alias: rejected because it weakens replay and version attribution.
- Self-hosted open weights: deferred; it adds hosting, security, serving, and operations work without proving the small slice.
- Deterministic stub only: retained for CI but insufficient for the separately permitted live interface smoke.

## Next gate

Fizz must `APPROVE` the exact scope-lock PR head and Ozzy must approve Bumble implementation. Bumble then performs the credential/billing/exact-access checks immediately before the sole live smoke call.
