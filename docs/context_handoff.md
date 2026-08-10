# Milestone-0 Context Handoff

> Read this first. This repository contains planning and governance scaffolding only. There is no application implementation, production service, cloud deployment, or accepted v2 architecture yet.

## Canonical context

- `stockoutops-live` is the canonical Phase-2 repository.
- PharmaRetail AI Control Tower is a read-only Phase-1 reference. Its useful patterns may be selectively migrated later through issue → branch → PR → independent review → merge.
- The Phase-1 Snowflake account is closed. StockoutOps Live has no Snowflake dependency.
- AWS is the target cloud, with the preferred simple stack recorded in `05_architecture_v2.md` and `13_risks_and_open_decisions.md`.

## Settled project principles

- A2 approve-to-act.
- Deterministic control spine and bounded AI reasoning.
- Human approval before every write action.
- Allow-listed, schema-validated tools.
- Durable `run_id` and resumable, auditable state.
- Citations/provenance, RBAC, tenant isolation, and observability.
- Failure injection and honest MEASURED / SIMULATED / ASSUMED / TARGET labels.
- Issue → branch → PR → independent review → merge.
- Passing tests alone do not complete a milestone.
- Fizz may return APPROVE, APPROVE WITH CONDITIONS, or BLOCK.

## M0 handoff state

- The Phase-1 high-level audit is populated in `01_current_state_audit.md`.
- The gap matrix is populated in `02_gap_matrix.md`.
- Architecture v2 is rewritten as an AWS-targeted proposal in `05_architecture_v2.md`.
- The seven proposed v2 tool names are preserved in `06_workflow_and_tool_contracts.md` and are explicitly not described as the exact Phase-1 seven.
- Snowflake assumptions have been removed from the current target architecture, threat model, environment template, and operating plans.

These documents are ready for review, not accepted. M0 checkboxes stay open until their issue/PR evidence, independent review, and verdict exist.

## Proposals still requiring review

- Architecture component boundaries.
- Workflow-engine approach.
- PostgreSQL persistence, RLS, approval, idempotency, and outbox design.
- v2 tool schemas and evidence rubric.
- UI technology, identity/tenant model, source-data contracts, dbt-core boundary, and external task integration.

The complete decision list is `13_risks_and_open_decisions.md`.

## Required close-out sequence

1. Review `00_project_charter.md`, `01_current_state_audit.md`, `02_gap_matrix.md`, `03_scope.md`, `05_architecture_v2.md`, `06_workflow_and_tool_contracts.md`, `07_threat_model.md`, and `13_risks_and_open_decisions.md`.
2. Resolve or explicitly defer the blocking decisions through ADRs.
3. Obtain Honey, Bumble, and Scout reviews for their assigned sections.
4. Obtain the independent Fizz M0 verdict; a BLOCK stops the milestone.
5. Record Osman’s approval before any Milestone-1 work.

Do not create application code, tests, Docker images, AWS resources, database schemas, or an agent during M0 close-out.

## Authority and history

- Current authority: owner decisions, project charter, accepted ADRs, risks/open decisions, and the reviewed architecture/tool documents.
- `kickoff_message.md` is a historical transcript and is non-authoritative where later owner decisions supersede it.
- If documents disagree, stop, open an issue, and resolve the conflict in the authoritative document and any dependent summaries.
