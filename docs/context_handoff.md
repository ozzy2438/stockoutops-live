# Milestone-0 Context Handoff

> Read this first. This repository contains planning and governance scaffolding only. There is no application implementation, production service, cloud deployment, or implemented v2 architecture.

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
- Only Fizz `APPROVE` opens a milestone gate. `APPROVE WITH CONDITIONS` pauses merge until resolution and re-review; `BLOCK` stops the milestone.

## M0 handoff state

- The Phase-1 high-level audit is populated in `01_current_state_audit.md`.
- The gap matrix is populated in `02_gap_matrix.md`.
- Architecture v2 is rewritten as an AWS-targeted proposal in `05_architecture_v2.md`.
- The seven proposed v2 tool names are preserved in `06_workflow_and_tool_contracts.md` and are explicitly not described as the exact Phase-1 seven.
- Snowflake assumptions have been removed from the current target architecture, threat model, environment template, and operating plans.

Document presence does not prove M0 approval. The authoritative gate and verdict semantics are in `12_backlog_and_milestones.md`; live evidence is the linked GitHub issue and PR.

## Deferred technical decisions

- Architecture component boundaries.
- Workflow-engine approach.
- PostgreSQL persistence, RLS, approval, idempotency, and outbox design.
- v2 tool schemas and evidence rubric.
- UI technology, identity/tenant model, source-data contracts, dbt-core boundary, and external task integration.

M0 approval may accept the planning scaffold without selecting these options. The complete decision list and the implementation point each item gates are in `13_risks_and_open_decisions.md`.

## Required close-out sequence

1. Complete the owner-authorised M0 consolidation issue and PR, including its threat-model diff.
2. Pass required CI and Markdown checks on the exact PR head.
3. Obtain independent Fizz `APPROVE` for that exact head. A conditional verdict pauses merge; `BLOCK` stops the milestone.
4. Squash-merge only after `APPROVE`, then verify the authoritative files on GitHub `main`.
5. Record Osman’s explicit approval before any Milestone-1 work.

Do not create application code, tests, Docker images, AWS resources, database schemas, or an agent during M0 close-out.

## Authority and history

- Current authority: owner decisions, project charter, accepted ADRs, risks/open decisions, and the reviewed architecture/tool documents.
- `kickoff_message.md` is a historical transcript and is non-authoritative where later owner decisions supersede it.
- If documents disagree, stop, open an issue, and resolve the conflict in the authoritative document and any dependent summaries.
