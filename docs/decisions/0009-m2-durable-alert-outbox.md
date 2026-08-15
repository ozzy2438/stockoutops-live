# 0009. Durable PostgreSQL alert-delivery outbox

- **Status:** Proposed
- **Date:** 2026-08-15
- **Deciders:** TBD pending Orchestrator/Scout/Fizz assurance and owner merge
- **Consulted:** Honey (design), Fizz (durability, egress, evidence labelling)
- **Informed:** Orchestrator, Scout
- **Driving issue:** #26; parent M2 issue: #17, which remains open
- **Amends:** ADR-0008 (the accepted at-most-once crash-gap trade-off only)

## Context

ADR-0008 accepted a claim-before-send delivery path and recorded this explicit
residual:

> "Claim-before-send is at-most-once. A crash after claim and before a
> successful POST can drop a notification; that is accepted for this
> engineering candidate."

The merged threat model repeats it: *"Crash after claim and before POST can drop
a notification (at-most-once)"* and *"there is no outbox replay worker."*

That trade-off is acceptable for a local engineering candidate and unacceptable
for anything production-oriented. A dropped `FIRED` notification is a silent
alerting failure — the exact class of fault an alerting path exists to prevent.
This decision removes it.

Nothing else about ADR-0008 changes. Provider neutrality, disabled-by-default
delivery, `SIMULATED` labelling, `execute=false`,
`live_slo_evidence_eligible=false`, `external_alert_delivery_count = 0` on
evaluation rows, and the loopback-only local proof all still hold.

## Decision

Replace synchronous claim-before-send with a durable PostgreSQL outbox and a
leased recovery worker.

1. **Transactional intent.** `alert_outbox` receives the delivery intent inside
   the same transaction that appends the `alert_evaluation_event` row. Evidence
   and intent commit together or not at all.
2. **No network I/O in a transaction.** Enqueue performs zero HTTP. The worker
   leases in one transaction, closes it, sends, then records the outcome in a
   separate transaction.
3. **Leasing.** `SELECT ... FOR UPDATE SKIP LOCKED` plus `lease_owner` and
   `lease_expires_at`. Competing workers claim disjoint rows. An expired lease
   is taken over by another worker; the previous owner's late write is rejected
   because every outcome update is conditional on still holding the lease.
4. **State machine.** `PENDING → IN_FLIGHT → DELIVERED`, with
   `IN_FLIGHT → PENDING` for bounded retry, `IN_FLIGHT → DEAD_LETTER` on
   exhaustion or permanent failure, and `DEAD_LETTER → PENDING` only through an
   explicit operator re-drive. `DELIVERED` is final. Database triggers reject
   every other transition.
5. **Deterministic idempotency.** The key is
   `{tenant_id}:{evaluation_id}:{transition}`, stable across replay, retry,
   lease takeover, and re-drive, and sent as the `Idempotency-Key` header.
6. **Bounded retry.** Deterministic exponential backoff (2s base, 300s cap) with
   an explicit `max_attempts` budget. Retry covers 5xx, connection errors, and
   timeouts. 4xx is permanent and dead-letters immediately.
7. **Append-only evidence.** `alert_delivery_attempt_event` records one
   immutable row per HTTP attempt. The 0007 `alert_delivery_attempt` ledger
   keeps its terminal role and every existing guard; the worker writes its
   CLAIMED and terminal rows inside one transaction with no network call
   between them.
8. **Tenant isolation.** Every tenant-scoped repository method takes `Principal`
   first. The worker's lease scan is the one deliberate cross-tenant read; each
   leased row carries its own `tenant_id`, and both the application and the
   database triggers constrain all subsequent writes to that value.

### Why PostgreSQL and not a queue platform

C-06 requires a demonstrated need before adopting a platform outside the
baseline. The bounded requirement is: durable intent, leasing, expiry recovery,
bounded retry, dead-letter, re-drive, and append-only evidence, at one alert
notification per tenant lifecycle transition.

`FOR UPDATE SKIP LOCKED` provides competing-consumer semantics; lease columns
provide expiry recovery; a `CHECK`-constrained state column plus triggers
provide the state machine; `UNIQUE (tenant_id, evaluation_id)` provides dedup.
The delivery intent must also commit atomically with the evaluation evidence,
which a separate broker cannot do without introducing a second consistency
problem — the very problem an outbox exists to solve.

Redis, Kafka, and Celery were therefore rejected: they add an operational
component, a second failure domain, and a dual-write gap, and buy nothing this
requirement needs. This is not a general finding about queue platforms; it is
scoped to this bounded requirement and should be revisited if throughput or
fan-out requirements ever justify it.

## Delivery-semantics honesty

These three are deliberately distinct and must not be conflated in any report:

| Term | What this system provides |
|---|---|
| **Durable at-least-once processing** | **Provided.** A committed intent is retried until delivered, dead-lettered, or the attempt budget is spent. A crash cannot lose it. |
| **Effective receiver idempotency** | **Delegated, not provided.** Duplicate suppression depends on the receiver honouring the stable `Idempotency-Key`. A non-conforming receiver will observe duplicates. |
| **Ambiguous network outcome** | **Explicitly modelled.** A timeout is recorded as `AMBIGUOUS`, never as a failure, because the receiver may have accepted the request. It is retried. |

**This is not exactly-once network delivery, and no such claim is made.**
Exactly-once delivery across an unreliable network is not achievable; the
honest construction is at-least-once transport plus receiver-side idempotency,
which is what this decision implements.

**M2-04 PENDING — no external/staging alert delivery has yet been proven.**

## Consequences

### Positive

- The documented crash gap is removed. A crash before send, after send, or
  mid-timeout no longer drops a notification.
- Evaluation is faster and cannot be blocked by a slow or hanging receiver.
- Retry, dead-letter, and re-drive are explicit, bounded, and auditable.
- Per-attempt evidence is append-only and tenant-scoped.

### Negative / trade-offs

- Delivery is now asynchronous: a worker must run. If no worker runs, intents
  accumulate as `PENDING` backlog. Backlog monitoring is required before any
  environment claim.
- Duplicate suppression depends on the receiver. A receiver that ignores
  `Idempotency-Key` can observe a duplicate after an ambiguous timeout.
- The synchronous `HttpsWebhookSink` is removed; its HTTP mechanics survive as
  `WebhookTransport`. Behavioural tests that drove the sink now drive the
  worker. Every ADR-0008 security and integrity guard is retained unchanged.
- `alert_delivery_attempt.attempt_count` bounds widen from 2 to 100 to fit the
  outbox retry budget. All other 0007 guards are byte-for-byte preserved.

### Neutral

- CloudWatch, SNS, email, Slack, and PagerDuty remain absent.
- OD-08 remains open. Issue #17 remains open.
- No AWS, no OpenAI, no real external endpoint. Local proofs use a loopback
  receiver only.

## Alternatives considered

- **Keep claim-before-send and accept the gap** — rejected; this ADR exists to
  close it.
- **Deliver inside the evaluation transaction** — rejected; holds a transaction
  open across a network call and makes delivery failure discard alert evidence.
- **Adopt Redis/Kafka/Celery** — rejected; see "Why PostgreSQL" above.
- **Retry in-process without persistence** — rejected; process death still
  loses the notification, which is the defect under repair.
- **Treat a timeout as a failure** — rejected; the receiver may have accepted
  it. Recording it as failure would suppress a required redelivery.

## Recovery and rollback

Leave `STOCKOUTOPS_ALERT_WEBHOOK_ENABLED` unset or `false`: no enqueuer is
built, no intent is written, and no worker work exists. Migration `0008` is
additive apart from two widened `CHECK` bounds; retain any outbox rows rather
than using a destructive rollback. Dead-lettered rows are recoverable through
the explicit re-drive path. No live external compensation is required because
this candidate still does not prove staging or production delivery.

## Follow-ups

- Driving issue: #26. Parent M2 issue: #17, remains open.
- Destination allow-list, DNS/SSRF and egress hardening remain Phase 2 and are
  explicitly **not** delivered here.
- Backlog/age observability thresholds must be defined before any environment
  claim.
- M2-04 stays pending until a separately authorised environment delivers and
  proves alerts.
