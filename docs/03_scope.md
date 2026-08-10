# 03 — Scope

## In scope (Phase 2)

1. **Stockout / low-stock investigation workflow** as described in `docs/00_project_charter.md`.
2. Reading reviewed, tenant-authorised inventory, sales, supplier, promotion and SOP sources through governed contracts.
3. Deterministic quality, freshness, permissioning, tenancy and policy checks.
4. AI-driven root-cause hypothesis and affected-scope estimation.
5. Cited recovery recommendation preparation.
6. Approve / edit / reject / escalate UI for a human analyst.
7. Creation of an approved incident / operational task after human approval.
8. Notifying the assigned owner (in-tenant channel).
9. Recording final outcome and audit trail with a durable `run_id`.
10. Full observability: logs, traces, metrics, SLOs, cost telemetry.
11. Evaluation harness: golden cases, historical replay, shadow-mode diffs.
12. Failure-injection exercises against a canary / staging environment.
13. Controlled UAT with ≥ 3 external operators and a small randomised operator study.
14. Independent milestone reviews by Fizz.

## Out of scope (Phase 2)

- Wholesale migration of the PharmaRetail repository or preservation of its Snowflake runtime.
- Purchase-order creation, modification, cancellation.
- Inventory transfer initiation.
- Pricing or promotion changes.
- Supplier commitments or contractual communication.
- Customer-facing outbound communication.
- Deletion of source records.
- Any direct unrestricted DB writes bypassing the tool layer.
- New forecasting / demand-planning models.
- Building a generic “AI copilot” that answers arbitrary questions.
- Kafka, Kubernetes, Databricks, Airflow, Snowflake, MLflow, or another major platform unless a later ADR proves a requirement.
- Full commercial production-A/B test with statistical claims of ROI.
- Multi-region HA, disaster-recovery guarantees beyond SLO targets.
- Non-stockout workflows (returns, receiving, shrinkage) — candidate for Phase 3.

## Boundary decisions (why these lines)

- **Autonomy line:** any action that changes commercial or physical state is a Phase-3 candidate. In Phase 2, the agent only *prepares* such actions and never executes them.
- **Model line:** we do not train new models. Reviewed Phase-1 semantic definitions may inform PostgreSQL/dbt-core models, but no existing mart is assumed to be available. A hosted LLM is proposed behind allow-listed tools; provider selection remains open.
- **Evaluation line:** we run a *controlled UAT experiment*, not a production A/B. Labelling honesty is a hard requirement.
- **Architecture line:** AWS and the simple target stack are owner constraints. Component, workflow, persistence, and tool designs are M0 proposals; accepting the scaffold does not decide unresolved options, which require accepted ADRs or contracts before dependent implementation.

## Scope-change control

Any expansion to this list requires:

1. A new issue with the `feature` template.
2. An ADR under `docs/decisions/`.
3. Honey sign-off (design implications).
4. Fizz sign-off (risk / assurance).
5. Owner (Osman) approval.
