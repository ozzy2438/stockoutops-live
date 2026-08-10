# 0003. Use an explicit Python state machine and minimal review surface in M1

- **Status:** Accepted for M1 (effective after this scope-lock PR merges)
- **Date:** 2026-08-10
- **Deciders:** Ozzy (owner), Honey (architecture), Orchestrator (scope)
- **Assurance:** Fizz review of the exact documentation PR head is required

## Context

The M1 slice needs durable, reviewable transitions but no scheduler, distributed worker, or external write. A workflow platform would add a broker, worker lifecycle, recovery surface, and new technology before the vertical slice proves value.

## Decision

- Implement a frozen explicit Python transition table; do not add Temporal, Prefect, Celery, Redis, or another workflow engine.
- M1 states are:
  `created -> validating -> gathering_evidence -> quality_checks -> reasoning -> drafting_recommendation -> awaiting_human -> (approved | edited_and_approved | rejected | escalated) -> closed`, plus terminal `failed_authz`.
- `executing_write` and `recording_outcome` from the broader M0 proposal are not implemented because M1 has no external write.
- The deterministic control spine alone performs identity/tenant checks, evidence retrieval, freshness/contract checks, state transitions, audit append, citation validation, approval validation, idempotency, and budget enforcement.
- The model has no tools and can draft only the two fields accepted in ADR-0002.
- Expose the minimum review surface through FastAPI: intake, run read, review submit, and audit export, plus one same-origin server-rendered Jinja page. No frontend framework, Node build, broker, or background worker.
- The page displays the cited evidence, structured draft, and Approve / Edit / Reject / Escalate actions. Reject and Escalate require a reason. Edit persists both original and edited payloads.
- A review binds tenant, authorised reviewer, `run_id`, state, draft payload hash, decision timestamp, and an explicit fixture-policy expiry of `PT24H` (24 hours).

## Rationale

This is the smallest design that proves visible human control, deterministic transitions, and an inspectable audit trail. It preserves a replaceable workflow boundary without paying the operational cost of a workflow platform.

## Consequences and limitations

- Single application instance and single-writer operation only are claimed for M1.
- There is no crash sweeper, lease/heartbeat, distributed scheduling, rich edit diff, accessibility review, internationalisation, task assignment, reviewer notification, or escalation routing.
- `PT24H` is a deterministic simulated-fixture review policy, not a production risk policy or service-level agreement.
- The page proves function through a human smoke checklist; it does not prove usability, adoption, or production authentication.

## Security, privacy, and failure behaviour

- Invalid transitions and stale approval targets fail closed and append audit events.
- Escalate is a persisted terminal human decision in M1; it sends no message and creates no task.
- Raw model prompt/response bodies are not displayed or persisted by default.
- Identity transport and local-only restrictions are defined in ADR-0005.

## Recovery and rollback

Restart the local app and resume from persisted state using the same intake idempotency key. Disable the reasoning adapter for human-only handling. Roll back the documentation decision by a superseding ADR; do not rewrite the audit history.

## Alternatives considered

- API-only review: rejected because M1 requires a human-operable screen artefact.
- React or another frontend framework: rejected as unnecessary build/runtime scope.
- Workflow platform: deferred until measured concurrency, scheduling, or recovery needs justify it.

## Next gate

Implement only after Fizz `APPROVE` on the exact scope-lock head and Ozzy approval. Any workflow platform or external write requires a later ADR.
