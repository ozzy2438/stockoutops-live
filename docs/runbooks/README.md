# Runbooks

> Living operational runbooks. Every SEV1/SEV2 incident either follows an existing runbook or creates one during the post-mortem.

## Index (created as capabilities land)

- `on_call.md` — rotation, paging, severity definitions (M1).
- `intake_halt.md` — what to do when intake refuses all requests (M1).
- `data_stale.md` — handling `DATA_STALE` events per mart (M1).
- `llm_outage.md` — provider outage: failover to human-only mode (M1).
- `rls_leakage.md` — SEV1 response for any RLS invariant breach (M1).
- `cost_blowout.md` — investigating and mitigating cost spikes (M2).
- `rollback.md` — gate-level rollback procedures (M2–M4).
- `postmortems/` — index of incident post-mortems (starts empty).

## Runbook template

```markdown
# <Runbook title>

## Applies to
<severity, component, symptom>

## Detection
<alert names, dashboards, symptoms>

## Immediate actions
1.
2.
3.

## Diagnosis
<queries, log filters, trace filters>

## Mitigation
<feature flag, rollback command, escalation>

## Recovery
<verify SLO, drain backlog, notify users>

## Post-mortem trigger
<criteria; owner; deadline>
```
