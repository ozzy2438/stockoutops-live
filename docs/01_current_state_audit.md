# 01 — Current-State Audit

> Scope: StockoutOps Live scaffold base `7d13cae` and PharmaRetail AI Control Tower reference `544d3c7`, inspected 2026-08-10. Status: **complete for the Milestone-0 high-level handoff**. This is a static repository audit, not a live-runtime certification.

## Repository boundary

- [MEASURED — repository inspection] [`stockoutops-live`](https://github.com/ozzy2438/stockoutops-live) is the new canonical Phase-2 repository.
- [MEASURED — repository inspection] [`PharmaRetail-AI-Control-Tower`](https://github.com/ozzy2438/PharmaRetail-AI-Control-Tower) is a Phase-1 reference implementation.
- [ASSUMED — owner statement] The Phase-1 Snowflake account no longer exists. No Snowflake object, credential, scheduled job, or live test was revalidated.
- KEEP / HARDEN / REPLACE decisions below govern ideas and patterns only. They do not authorise wholesale copying into StockoutOps Live.

## Evidence labels

- **MEASURED** — directly observed in repository code, configuration, documentation, or Git history.
- **SIMULATED** — produced from deterministic fixtures, synthetic data, or an offline evaluation.
- **ASSUMED** — supplied by the owner or not independently verifiable in the current environment.
- **TARGET** — a desired Phase-2 outcome, not a current capability.

## Phase-1 inventory

| Area | Observed current state | Evidence |
|---|---|---|
| Delivery history | Issue/branch/PR/CI delivery is visible through PR #46 and multiple specialised GitHub Actions workflows. | MEASURED |
| Data platform | Snowflake-backed RAW → STAGING → INTERMEDIATE → MARTS with dbt-core. Phase-1 docs report 23 models and 147 tests after Phase 4. The UCI sales facts and synthetic store/product operational facts intentionally use separate identifier spaces. | MEASURED for repository structure; SIMULATED for synthetic operational facts |
| Operational data | Six stockout-related marts cover supplier, inventory, delivery, stockout, promotion, and incident data. Deterministic scenarios carry labelled ground-truth root causes. | MEASURED / SIMULATED |
| SOP retrieval | Eight versioned synthetic SOP/policy documents, deterministic section chunking, metadata/effective-date/access filters, extractive answers, citations, and an append-only retrieval audit. The Phase-1 report records 36/36 offline evaluation cases passing. | MEASURED for implementation; SIMULATED for results |
| Agent/control path | A fixed Python investigation plan enforces an allow-list, constant parameterised queries, role/scope filtering, citation-bearing findings, prompt-injection screening, and draft-only actions. The inspected Phase-6 path does not invoke an LLM. | MEASURED |
| Audit and drafts | Append-only Snowflake sinks persist interaction and action-draft records keyed by deterministic query/audit/draft hashes. There is no durable `run_id` spanning intake, pause/resume, approval, and write execution. | MEASURED |
| Security | Snowflake roles, explicit grants, row-access policies, masking, service identities, and leakage tests are documented and implemented. These controls are Snowflake-specific and the backing account is closed. | MEASURED / ASSUMED |
| UI | The Streamlit UI uses `UI_DEMO_USER`, lets the operator select role/scope, and constructs `InMemoryGateway`, `InMemoryAuditSink`, and `InMemoryDraftSink`. It displays pending drafts but has no authenticated approval persistence or external write. | MEASURED |
| API and tenancy | No FastAPI service, real IdP/session integration, tenant boundary, or server-derived authorisation context is implemented. | MEASURED |
| Operations | No current AWS deployment, CloudWatch telemetry, service SLO evidence, cost per investigation, sustained-operation record, external UAT evidence, canary, or formal failure-injection results were found. | MEASURED |

## Phase-1 tool catalogue

The seven Phase-1 tool names are:

1. `get_stockout_metrics`
2. `get_inventory_position`
3. `get_supplier_performance`
4. `get_promotion_impact`
5. `search_policy_docs`
6. `draft_action_plan`
7. `log_ai_interaction`

The proposed v2 catalogue in `06_workflow_and_tool_contracts.md` is a new set derived from Phase-1 lessons. It is not this list renamed wholesale and is not implemented.

## Disposition

| Component or pattern | Decision | Handoff direction |
|---|---|---|
| Issue → branch → PR → independent review → merge discipline | **KEEP** | Preserve as the delivery control; passing tests alone never closes a milestone. |
| Deterministic synthetic stockout scenarios and ground-truth labels | **KEEP** | Reuse the scenario concepts after provenance and licensing review; do not copy generated datasets blindly. |
| dbt model layering, contracts, reconciliation, and business tests | **HARDEN** | Selectively port justified transformations to dbt-core/PostgreSQL; rewrite Snowflake SQL and revalidate every source assumption. |
| SOP metadata, effective-date filtering, citation format, and evaluation cases | **HARDEN** | Retain the governed-evidence ideas; redesign storage for PostgreSQL/S3 and expand beyond the small synthetic corpus. |
| Deterministic control spine, allow-listed calls, fail-closed checks, and draft-only action invariant | **HARDEN** | Add durable `run_id` state, tenant identity, resumability, idempotency, approval binding, and bounded LLM reasoning. |
| Phase-1 seven-tool catalogue | **REPLACE** | Use the proposed v2 catalogue as the review baseline. `log_ai_interaction` becomes a control-spine responsibility, while v2 adds explicit demand and similar-incident evidence capabilities. |
| Query-hash audit and Snowflake action-draft persistence | **REPLACE** | Propose PostgreSQL workflow/event/approval/outbox persistence; final schema remains subject to M0 review. |
| Snowflake DDL, warehouses, roles, policies, connectors, service identities, and Snowflake deployment workflows | **RETIRE** | The account is closed and Snowflake is not a Phase-2 target dependency. Preserve only design lessons in this audit. |
| User-selectable role/scope simulation | **REPLACE** | Authorisation must come from authenticated server-side identity and tenant context. |
| Streamlit demo implementation | **REPLACE** | Preserve useful review-screen interaction ideas, but use FastAPI plus a lightweight human-review UI selected during M0 review. |
| Phase-1 GitHub Actions and test organisation | **HARDEN** | Keep workflow separation and blocking checks; replace Snowflake jobs with Docker/AWS/RDS/dbt-core checks only when Milestone 1 is authorised. |
| [Phase-1 `project.md`](https://github.com/ozzy2438/PharmaRetail-AI-Control-Tower/blob/main/project.md) and Phase-1 architecture claims | **RETIRE as authority** | Keep as historical reference only. Current decisions live in the StockoutOps Live charter, ADRs, risks, and reviewed architecture. |

## Audit conclusion

Phase 1 is useful evidence for deterministic governance, citations, dbt testing, synthetic scenarios, and repository discipline. It is not a deployable base for Phase 2: its live data platform is gone, its persistence and security controls are Snowflake-specific, and its UI/agent path lacks the durable, authenticated approve-to-act lifecycle required by StockoutOps Live.

Runtime performance, live security posture, current test pass rates, and operational claims remain **unverified**. Any later migration requires a scoped issue, branch, PR, independent review, and evidence appropriate to the component.
