# 01 — Current-State Audit (PharmaRetail AI Control Tower → StockoutOps Live)

> Status: **template**. Orchestrator populates during M0. Every claim below must be labelled MEASURED / SIMULATED / ASSUMED / TARGET when filled in.

## Purpose

Establish, on paper and by inspection, exactly what the existing PharmaRetail AI Control Tower delivers today, so we can distinguish what to **keep**, **harden**, or **replace** in StockoutOps Live.

## Method

1. Repo walk of the existing PharmaRetail codebase (governance, data, agent, UI, CI).
2. Read of every ADR / design doc.
3. Inspection of live artifacts: Snowflake objects, dbt models, tool definitions, RBAC policy, audit log schema, CI pipelines.
4. Interview / notes with Osman on the current usage pattern.
5. Evidence review: existing test results, RLS-leakage tests, screenshots, logs.

## Inventory (fill in)

### Data layer

- Snowflake account & warehouse profile: 
- dbt project structure (staging / intermediate / marts): 
- Data contracts / model tests: 
- Freshness SLAs: 
- PII inventory & masking: 

### Agent layer

- LLM provider(s) & model(s) in use: 
- Allow-listed tools (should be 7): 
  1. 
  2. 
  3. 
  4. 
  5. 
  6. 
  7. 
- Tool argument schemas: 
- Prompt versioning approach: 
- Citation enforcement mechanism: 

### Governance / security

- RBAC roles & permission matrix: 
- Row-level security policies: 
- Audit log schema (append-only): 
- Human-approval mechanism: 
- Secrets management: 

### Application layer

- Streamlit UI structure & pages: 
- Auth path (IdP, sessions): 
- Tenant isolation: 

### CI/CD & test

- Pipelines & required checks: 
- Test coverage (unit / integration / RLS): 
- Deployment target(s): 

### Operations

- Existing dashboards / alerts / SLOs (if any): 
- Existing runbooks (if any): 
- Existing incidents (if any): 

## Findings summary

- Strengths carried forward: 
- Weaknesses to remediate: 
- Items to retire: 

## Output

This document, plus:

- A dependency graph (`docs/artifacts/current-state-graph.svg` — produced in M0).
- A tool-contract inventory (`docs/06_workflow_and_tool_contracts.md` initial fill).
- Feeds directly into `02_gap_matrix.md`.
