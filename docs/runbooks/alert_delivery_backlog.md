# Alert delivery backlog and dead letters

> Local/CI engineering runbook for the durable alert-delivery outbox (ADR-0009).
> No environment currently runs this worker, so nothing here is a proven
> operational procedure. **M2-04 PENDING — no external/staging alert delivery
> has yet been proven.**

## Applies to

The `alert_outbox` delivery path when
`STOCKOUTOPS_ALERT_WEBHOOK_ENABLED` is explicitly set. When delivery is
disabled — the default — no intent is enqueued and this runbook is inert.

## Detection

No alarm is wired yet. Inspect directly:

```sql
-- backlog that is due but unprocessed
SELECT tenant_id, count(*) FROM alert_outbox
WHERE state = 'PENDING' AND next_attempt_at <= now() GROUP BY tenant_id;

-- stalled or crashed worker: lease expired while IN_FLIGHT
SELECT outbox_id, tenant_id, lease_owner, lease_expires_at FROM alert_outbox
WHERE state = 'IN_FLIGHT' AND lease_expires_at <= now();

-- delivery gave up
SELECT outbox_id, tenant_id, attempt_count, last_error_class, last_http_status
FROM alert_outbox WHERE state = 'DEAD_LETTER' ORDER BY outbox_id;

-- ambiguous outcomes (may have reached the receiver and been redelivered)
SELECT outbox_id, attempt_number, error_class FROM alert_delivery_attempt_event
WHERE outcome = 'AMBIGUOUS' ORDER BY outbox_id, attempt_number;
```

## Immediate actions

1. Confirm whether a worker is running at all. A growing `PENDING` backlog with
   `attempt_count = 0` means nothing is draining the outbox — that is the most
   likely cause, not a delivery fault.
2. Run one bounded drain and read its counters:
   `make alert-outbox-worker`.
3. If `lease_lost` is non-zero, more than one worker is active and leases are
   expiring mid-flight. Raise `--lease-seconds` above the slowest expected
   request, or reduce worker count.

## Diagnosis

- `RETRYABLE_FAILURE` with `http_5xx` — receiver-side fault. Backoff is already
  bounded; wait or fix the receiver.
- `PERMANENT_FAILURE` with `http_4xx` — the request is being rejected. Payload
  or auth contract mismatch. Retrying will not help; fix the cause first.
- `connection_error` — the destination is unreachable from this host.
- `AMBIGUOUS` (`timeout`) — the receiver may have accepted the request. The
  outbox redelivers under the same `Idempotency-Key`. If the receiver does not
  honour that header, it will have observed a duplicate. Confirm against
  receiver-side records before assuming a missed notification.

## Mitigation

Set `STOCKOUTOPS_ALERT_WEBHOOK_ENABLED=false` to stop all delivery. Evaluation
evidence continues to persist; only outbound delivery stops. Intents already
enqueued remain durable and will drain when re-enabled.

## Recovery

Re-drive is explicit, tenant-scoped, and never automatic:

```python
from stockoutops.alerting.outbox import AlertOutboxRepository

repository = AlertOutboxRepository(database)
repository.redrive(principal, outbox_id, now=utcnow(), additional_attempts=5)
```

Re-drive returns the row to `PENDING`, increments `redrive_count`, and raises
the attempt ceiling. It refuses any row that is not `DEAD_LETTER` and any row
belonging to another tenant. Fix the underlying cause first: re-driving into a
receiver that is still returning 4xx only burns the new budget.

## Post-mortem trigger

Any dead letter for a SEV1 policy, or any backlog that outlives its alerting
purpose. Owner: whoever holds alerting. **No such incident has occurred; no
environment runs this path.**
