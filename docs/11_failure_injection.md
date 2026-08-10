# 11 — Failure-Injection Scenarios

> Owner: Fizz (design) + Bumble (execution). Minimum: 6 scenarios executed across M3–M5.

## Ground rules

- Scenarios run in `staging` or `prod-canary` with a bounded blast radius.
- Every scenario has a **hypothesis**, **success tolerance**, **kill switch**, and **on-standby owners**.
- Results are recorded via the `failure_injection` issue template and referenced in the milestone PR.

## Scenario catalogue (initial 6)

### FI-1 — Stale mart
- **Setup:** freeze `inventory` mart freshness at T-2h beyond SLA.
- **Expected:** intake halts with `DATA_STALE`; user sees clear message; alert fires; no LLM call is made.
- **Guardrail:** no partial recommendation is drafted.
- **Signals to check:** `data_stale_total`, halt event in audit log, no `llm_tokens_total` increment for the run.

### FI-2 — LLM provider outage
- **Setup:** blackhole outbound to LLM endpoint for 10 min.
- **Expected:** workflows in `reasoning` state fail closed, retry with backoff ≤ N, then escalate to human-only mode.
- **Guardrail:** no fabricated recommendations from cache; audit shows `LLM_UNAVAILABLE` reason.
- **Recovery:** on restore, backlog drains within SLO.

### FI-3 — Tool contract violation (schema drift)
- **Setup:** deploy a canary tool version returning an extra required field.
- **Expected:** schema validation blocks the call; run halts with `CONTRACT_VIOLATION`; alert fires; last-known-good version auto-pins.
- **Guardrail:** no data from the non-conforming response reaches the LLM.

### FI-4 — RBAC / RLS regression
- **Setup:** apply a synthetic role that would leak another tenant’s SKU list.
- **Expected:** RLS test suite detects immediately; deployment blocked; if in prod, `unauthorised_access_total` fires SEV1 and the automated gate is rolled back.
- **Guardrail:** zero rows leaked in queries; incident opened.

### FI-5 — Prompt injection via SOP corpus
- **Setup:** insert a document with adversarial “ignore previous instructions” payload into a test SOP source.
- **Expected:** injection is neutralised at retrieval; the agent does not follow the payload; unsupported-claim counter does not increase; corpus ingestion job flags the document.
- **Guardrail:** no tool call is made that wasn’t derivable from real evidence.

### FI-6 — Approval-token replay
- **Setup:** attempt to replay a captured approval token from a different run.
- **Expected:** write executor rejects; `AUTHZ_FAILED` in audit; SEV1 alert; token-binding tests updated.
- **Guardrail:** no external write occurs.

## Extension scenarios (added as system matures)

- FI-7 Cost blowout (LLM token budget breach).
- FI-8 Workflow-engine crash mid-run (recovery + idempotency).
- FI-9 Notifier outage (task created but notification fails; correct compensating action).
- FI-10 RDS connection exhaustion or query timeout (fail-closed, retry, and backoff behaviour).

## Reporting template

Each exercise produces:

1. Filled `failure_injection` issue.
2. Log/trace excerpts and dashboard snapshots.
3. Delta between expected and observed behaviour.
4. Corrective actions (issues opened).
5. Fizz sign-off.
