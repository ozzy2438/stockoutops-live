# 00 — Project Charter

## Name

**StockoutOps Live — Human-Supervised AI Decisioning & Reliability Platform**

## Purpose

Convert the existing **PharmaRetail AI Control Tower** (governed Snowflake/dbt stockout-investigation system) into an **operated, observable, human-supervised product** with credible evidence of user acceptance, incidents, reliability and cost.

The deliverable is **not** another portfolio dashboard. The deliverable is the end-to-end chain:

> business problem → governed data → bounded AI agent → human decision → live deployment → sustained operation → incidents and recovery → user evidence → measured outcome → cost → independent assurance.

## Why now

The portfolio already contains 47 projects covering analytics, data engineering, ML, AI automation and BI. What is missing is **operational maturity**: shadow/assisted pilot, baseline comparison, acceptance/edit rate, time-to-decision, cost per investigation, and evidence of sustained operation.

## Business job

When a stockout alert or investigation request is received, the platform:

1. Validates identity, tenant, eligibility and data freshness.
2. Retrieves inventory, sales, supplier, promotion and approved SOP evidence.
3. Identifies the likely root cause and affected scope.
4. Prepares a cited recovery recommendation.
5. Requires human approval before any write action.
6. Records the final outcome in a fully auditable workflow.

## Initial autonomy

**A2 — approve-to-act.** See `README.md` §3 for the allowed and forbidden lists. Change of autonomy level requires an ADR + Fizz sign-off + rollout-gate evidence.

## Non-goals for Phase 2

- No new warehouse, no new dashboard, no new tahmin model, no generic AI copilot.
- No commercial production-A/B claim. UAT is honestly labelled as *controlled UAT experiment*.
- No purchase-order, transfer, pricing, promotion, supplier-commitment automation.

## Success (top-line)

The project succeeds when **all** DoD bullets in `README.md` §6 are true, Fizz has returned a final verdict, and the honest state label matches reality (`Production-grade ... controlled UAT` at minimum; `Human-supervised production pilot` if real operators use it).

## Stakeholders

- **Owner / accountable:** Osman Orka.
- **Delivery team:** Buzz agents (Orchestrator, Honey, Bumble, Scout).
- **Independent assurance:** Fizz.
- **UAT participants:** ≥ 3 external users (identified in M2 planning).

## Timeline (target)

- M0 — Planning (this milestone).
- M1 — Historical replay (G0).
- M2 — Shadow mode (G1).
- M3 — Assisted operation (G2).
- M4 — Low-risk canary (G3).
- M5 — Controlled operation (G4) — 8–12 weeks.

Dates are set at the end of M0.

## Guardrails

- No direct pushes to `main`.
- No fabricated evidence. Labels: MEASURED / SIMULATED / ASSUMED / TARGET.
- No new external dependency without an ADR.
- Passing tests ≠ milestone completion.
- Zero RLS leakage is a release-blocker.
