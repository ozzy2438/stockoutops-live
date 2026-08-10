# Project Kickoff (verbatim)

> This is the exact kickoff message posted to the `Production-Ready-Real-World` channel. It is preserved here as authoritative context for anyone picking up the project.

---

**PROJECT KICKOFF**

**Project:** StockoutOps Live — Human-Supervised AI Decisioning & Reliability Platform

**Context:** This is Phase 2 of the existing PharmaRetail AI Control Tower. We are not starting another broad portfolio demo. We are converting an existing governed Snowflake/dbt stockout-investigation system into an operated, observable, human-supervised product with credible user, incident, reliability and cost evidence.

**Business job:** When a stockout alert or investigation request is received, the platform must validate identity, tenant, eligibility and data freshness; retrieve inventory, sales, supplier, promotion and approved SOP evidence; identify the likely root cause and affected scope; prepare a cited recovery recommendation; require human approval before any write action; and record the final outcome in a fully auditable workflow.

**Initial autonomy:** A2 — approve-to-act.

**Allowed initial outcomes:**
- read and analyse governed data
- prepare investigation pack
- recommend recovery action
- draft incident or operational task
- create an approved low-risk task after human approval

**Forbidden:**
- automatic purchase-order changes
- automatic inventory transfers
- pricing or promotion changes
- contractual or supplier commitments
- deletion of records
- unapproved outbound communication
- direct unrestricted database writes

**Team ownership:**
- Orchestrator: scope, milestone plan, backlog, dependencies and gates
- Honey: architecture, contracts, durable state, RBAC, threat model and SLOs
- Bumble: implementation, deployment, CI/CD, observability and recovery
- Scout: baselines, evaluation, UAT, operator study and evidence
- Fizz: independent assurance and release verdict

**Operating rules:**
- Keep scope tightly constrained.
- Do not add technologies without a written reason.
- Work through issue → branch → PR → independent review → merge → release.
- Do not change main directly.
- Do not fabricate clients, users, production status or business outcomes.
- Passing tests alone is not milestone completion.
- Clearly distinguish measured, simulated, assumed and target outcomes.
- Fizz must independently review every major milestone.
- High-impact decisions must be escalated to Osman.

**Milestone 0:** *Do not implement production code yet.* Produce:
1. Current-state repository and evidence audit.
2. Gap-to-deliverable matrix.
3. Exact in-scope and out-of-scope definition.
4. Business baseline measurement plan.
5. Architecture v2 proposal.
6. Workflow-state and tool-contract proposal.
7. Security, privacy and threat-model outline.
8. Evaluation and golden-case plan.
9. Historical replay → shadow → assisted UAT → canary rollout plan.
10. Observability, SLO and cost-measurement plan.
11. Six initial failure-injection scenarios.
12. Prioritised GitHub issue and milestone breakdown.
13. Risks, assumptions and unresolved owner decisions.

**Required review:** Honey, Bumble and Scout prepare their assigned sections. Fizz performs an independent review and returns APPROVE, APPROVE WITH CONDITIONS or BLOCK.

**Stop after Milestone 0 and wait for Osman’s approval before implementation.**
