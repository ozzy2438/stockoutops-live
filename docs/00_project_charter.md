# 00 — Project Charter

## Name

**StockoutOps Live — Human-Supervised AI Decisioning & Reliability Platform**

## Purpose

Create a new canonical Phase-2 implementation of a stockout investigation workflow as an **operated, observable, human-supervised product** with credible evidence of user acceptance, incidents, reliability, and cost.

The PharmaRetail AI Control Tower is reference material only. Its closed Snowflake environment is not a dependency, and its code is not migrated wholesale. Select patterns may be brought across later after a scoped review.

The deliverable is **not** another portfolio dashboard. The deliverable is the end-to-end chain:

> business problem → governed data → bounded AI agent → human decision → live deployment → sustained operation → incidents and recovery → user evidence → measured outcome → cost → independent assurance.

## Why now

Phase 1 demonstrates useful data, governance, citation, and deterministic-control patterns. What is still missing is **operational maturity**: a durable approve-to-act workflow, authenticated tenant isolation, an AWS deployment, shadow/assisted operation, baseline comparison, acceptance/edit evidence, time-to-decision, cost per investigation, and sustained-operation evidence.

## Business job

When a stockout alert or investigation request is received, the platform:

1. Validates identity, tenant, eligibility and data freshness.
2. Assigns and persists a durable `run_id`.
3. Retrieves authorised inventory, sales, supplier, promotion and approved SOP evidence.
4. Identifies the likely root cause and affected scope.
5. Prepares a cited recovery recommendation.
6. Requires human approval before any write action.
7. Records the final outcome in a fully auditable workflow.

## Initial autonomy

**A2 — approve-to-act.** See `README.md` §3 for the allowed and forbidden lists. Change of autonomy level requires an ADR + Fizz sign-off + rollout-gate evidence.

## Non-goals for Phase 2

- No wholesale Phase-1 port and no Snowflake compatibility layer.
- No second analytics warehouse, new forecasting model, or generic AI copilot.
- No Kafka, Kubernetes, Databricks, Airflow, MLflow, or other major platform without a later ADR demonstrating a concrete need.
- No commercial production-A/B claim. UAT is honestly labelled as *controlled UAT experiment*.
- No purchase-order, transfer, pricing, promotion, supplier-commitment automation.

## Success (top-line)

The project succeeds when **all** DoD bullets in `README.md` section 6 are true, Fizz has returned a final verdict, and the honest state label matches reality. During Milestone 0 the only valid label is “planning scaffold — no application or live deployment”.

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
- No application implementation starts before the M0 verdict and Osman’s approval.
