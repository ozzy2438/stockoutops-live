# 13 — Risks, Assumptions, and Open Decisions

> Owner: Orchestrator. Status: current for the Milestone-0 handoff; update at every milestone PR.

## Owner-set constraints

These are inputs to M0 review, not claims that the architecture is implemented:

- **C-01** — `stockoutops-live` is the canonical Phase-2 repository.
- **C-02** — PharmaRetail AI Control Tower is reference material only; migration is selective and reviewed.
- **C-03** — The old Snowflake account is closed and Snowflake is not a target dependency.
- **C-04** — AWS is the target cloud.
- **C-05** — Preferred baseline: Python, PostgreSQL/Amazon RDS, S3 where needed, dbt-core where justified, FastAPI, a lightweight review UI, Docker, ECS Fargate, CloudWatch, Secrets Manager, and GitHub Actions.
- **C-06** — Major platforms outside that baseline require a later ADR demonstrating a real need.
- **C-07** — A2 approve-to-act and the delivery, provenance, audit, tenancy, observability, failure-injection, honest-labelling, and Fizz-blocking principles are non-negotiable.

Architecture v2, the workflow-engine choice, persistence design, and v2 tool contracts remain proposals until M0 review.

## Risks

| ID | Risk | Probability | Impact | Owner | Mitigation |
|---|---|:---:|:---:|---|---|
| R-01 | Fewer than three genuine external UAT users | M | High | Scout | Recruit early; keep a backup pool; never relabel internal agents as external users. |
| R-02 | LLM cost or latency blowout | M | Medium | Bumble | Per-run budgets, bounded calls, model comparison, CloudWatch alerts. |
| R-03 | Prompt injection through SOP or incident content | M | High | Honey/Fizz | Curated ingestion, content-as-data boundary, adversarial cases, FI-5. |
| R-04 | Cross-tenant or role-scope leakage | L | Critical | Honey/Fizz | Server-derived identity, PostgreSQL controls, blocking isolation tests, FI-4. |
| R-05 | Golden cases do not represent live investigations | M | Medium | Scout | Blinded review, provenance labels, disagreement analysis, refresh on incidents. |
| R-06 | Operator study is underpowered or poorly defined | M | Medium | Scout | Pre-register population, boundaries, sample size, and confidence intervals. |
| R-07 | Autonomy scope creeps beyond A2 | M | High | Fizz | Pin autonomy; require ADR, owner approval, rollout evidence, and Fizz verdict. |
| R-08 | LLM-provider lock-in | M | Medium | Honey | Stable adapter and versioned evaluation under ADR-0002. |
| R-09 | RDS/ECS/S3 capacity or cost spikes | M | Medium | Bumble | Query/row/time caps, connection limits, tagging, budgets, and load evidence before scaling. |
| R-10 | Team over-claims production status or evidence | M | High | Orchestrator/Fizz | Mandatory MEASURED/SIMULATED/ASSUMED/TARGET labels and review of external claims. |
| R-11 | Phase-1 assumptions are copied with Snowflake-specific behavior | M | High | Orchestrator/Honey | Use the disposition table in `01_current_state_audit.md`; migrate only through scoped PRs. |
| R-12 | Approval and write are separated by a race, replay, or payload change | M | Critical | Honey/Fizz | Approval binding, transaction/outbox design, idempotency, expiry, FI-6. |

## Assumptions to validate

- **A-01** — Selected Phase-1 model definitions, scenarios, and citations are useful after source/provenance review.
- **A-02** — The proposed seven-tool v2 catalogue is sufficient for the first bounded workflow.
- **A-03** — Osman can source at least three external UAT users before assisted operation.
- **A-04** — A hosted LLM with structured tool use is sufficient; self-hosting is not required.
- **A-05** — A small explicit Python control spine with PostgreSQL durability can meet M1 needs without another workflow platform.
- **A-06** — PostgreSQL plus S3 can meet the reviewed data volume, isolation, lineage, and recovery requirements.
- **A-07** — dbt-core adds value only for a subset of repeatable transformations.

## Open decisions

| ID | Decision | Required output / blocker |
|---|---|---|
| OD-01 | LLM provider and model family | ADR-0002 before model-backed implementation. |
| OD-02 | Workflow-engine approach | ADR: explicit Python state machine vs adopted library; additional platform requires evidence. |
| OD-03 | PostgreSQL persistence design | Reviewed run/event/approval/provenance/outbox schema, transaction boundaries, RLS, backup, and recovery. |
| OD-04 | AWS region, network/ingress, and environment topology | ADR before infrastructure implementation. |
| OD-05 | Identity provider, session model, RBAC mapping, and tenant definition | Threat-model and data-contract approval before authenticated UAT. |
| OD-06 | Human-review UI technology | Choice within the lightweight UI constraint; accessibility and approval-integrity review. |
| OD-07 | Source systems, canonical data contracts, and dbt-core boundary | Data design review before building tools T1–T6. |
| OD-08 | External task and notification targets | Contract, tenant credentials, sandbox, and idempotency plan before write execution. |
| OD-09 | Cost-attribution method | Per-run LLM/AWS attribution and shared-cost allocation before cost claims. |
| OD-10 | Prompt/response, audit, and source-document retention | Data classification and deletion/legal requirements before live data. |
| OD-11 | UAT consent and data-usage terms | Scout/owner approval before recruitment. |
| OD-12 | Operator-study primary-metric boundaries | Pre-registered definition before baseline collection. |
| OD-13 | Acceptance of the proposed v2 tool schemas and evidence rubric | Honey/Fizz/owner review before implementation. |

## Change log

- 2026-08-10 — Reconciled owner decisions, retired Snowflake assumptions, and separated settled constraints from M0 proposals.
