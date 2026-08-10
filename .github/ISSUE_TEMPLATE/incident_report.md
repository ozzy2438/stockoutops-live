---
name: Incident report
about: A production or UAT incident
title: "incident: <short summary>"
labels: ["incident", "P?"]
---

## Summary

<!-- One paragraph. Include start / detect / mitigate / resolve times. -->

## Severity

- [ ] SEV1 — RLS leakage, unauthorized action, data corruption, safety violation
- [ ] SEV2 — Broken workflow, unavailable service, SLO burn > budget
- [ ] SEV3 — Degraded performance or partial feature loss
- [ ] SEV4 — Minor / cosmetic

## Detection

- How was it detected? (alert / user / manual)
- Time to detect: 
- Time to mitigate: 
- Time to resolve: 

## Impact

- Users affected: 
- Runs affected (run_ids): 
- Data at risk: 
- Financial / operational cost: 

## Timeline

<!-- UTC timestamps. Include run_ids, tenant ids, alerts fired. -->

## Root cause

<!-- Deterministic layer, agent layer, data layer, infra layer? -->

## Contributing factors

## Corrective actions

- Immediate: 
- Short-term (this sprint): 
- Long-term / structural: 

## Post-mortem link

- `docs/runbooks/postmortems/YYYY-MM-DD-<slug>.md`

## Fizz verdict

- [ ] APPROVE
- [ ] APPROVE WITH CONDITIONS
- [ ] BLOCK
