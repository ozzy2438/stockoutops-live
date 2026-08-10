# 05 — Architecture v2: AWS Target Proposal

> Owner: Honey. Reviewer: Fizz. Status: **proposal for Milestone-0 review; not implemented or accepted**.

AWS is the owner-selected target cloud. The component boundaries, workflow-engine choice, persistence schema, and tool contracts below remain proposals until the M0 review records a decision. No production service or cloud resource exists in this repository.

## Constraints

- Python
- PostgreSQL / Amazon RDS
- Amazon S3 only where object storage is required
- dbt-core only where transformations justify it
- FastAPI
- lightweight human-review web UI
- Docker
- AWS ECS Fargate
- Amazon CloudWatch
- AWS Secrets Manager
- GitHub Actions

Kafka, Kubernetes, Databricks, Airflow, Snowflake, MLflow, and other major platforms are outside the baseline. Adding one requires a later ADR with evidence that the simple stack cannot meet a concrete requirement.

## Design principles

1. **Deterministic control spine; bounded AI reasoning.** Identity, tenancy, authorisation, freshness, state transitions, approval, writes, and audit are deterministic. AI is limited to uncertain analysis and drafting.
2. **A2 approve-to-act.** No external write occurs before a valid human approval bound to the same `run_id` and proposed payload.
3. **Durable and replayable.** Every investigation receives a `run_id` before evidence gathering. Steps are idempotent, resumable, and auditable.
4. **Allow-listed, contract-first tools.** No free-form SQL, shell, or arbitrary HTTP is exposed to the model.
5. **Provenance before persuasion.** Findings and recommendations cite retrieved evidence; missing or stale evidence fails closed.
6. **Tenant isolation in depth.** Server-derived identity, application authorisation, PostgreSQL controls, and tests all enforce scope.
7. **Observable by default.** Logs, metrics, traces, costs, approvals, failures, and version identifiers correlate on `run_id`.
8. **Smallest sufficient platform.** Prefer explicit Python and PostgreSQL behavior over new infrastructure.

## Proposed component view

```text
Authenticated operator
        |
        v
Lightweight review UI
        |
        v
FastAPI boundary ---------------------------------------------------+
        |                                                           |
        v                                                           |
Deterministic control spine                                         |
(intake, authz, state, budgets, approval, idempotency)               |
        |                         |                                  |
        |                         +--> bounded LLM adapter            |
        v                                                            |
Proposed v2 tool layer                                               |
        |                                                            |
        +--> Amazon RDS for PostgreSQL                               |
        |    operational data, run state, events, approvals,         |
        |    provenance, version registry, action outbox              |
        |                                                            |
        +--> Amazon S3                                               |
        |    immutable source documents and large eval artifacts      |
        |                                                            |
        +--> approved task/notification system, post-approval only ---+

Docker containers on AWS ECS Fargate
CloudWatch for logs, metrics, traces, dashboards, and alerts
Secrets Manager for runtime secrets
GitHub Actions for reviewed build/deploy automation
dbt-core -> PostgreSQL only for justified repeatable transformations
```

The diagram is a target proposal, not proof that these components exist.

## Proposed runtime responsibilities

### FastAPI and review UI

- FastAPI is the only application boundary exposed to the UI and integration clients.
- The server, not the browser, derives actor, tenant, role, and eligible scope.
- The UI presents evidence, provenance, uncertainty, and the exact proposed write payload.
- Review outcomes are **approve**, **edit then approve**, **reject with reason**, and **escalate**.
- The UI framework, identity provider, and AWS ingress design remain open decisions.

### Deterministic control spine

- Assign `run_id` at intake and enforce the reviewed workflow transition table.
- Apply authentication, tenant, authorisation, freshness, budget, and tool-contract gates.
- Pause durably at human review and resume without repeating successful side effects.
- Bind approval to `run_id`, reviewer, tool/payload hash, expiry, and tenant.
- Use idempotency keys and an outbox-style boundary for post-approval writes.

The implementation approach—small explicit Python state machine versus an adopted workflow library—remains open. Any engine outside the preferred stack requires an ADR.

### Bounded reasoning

- The model receives only redacted, authorised evidence and the proposed tool schemas.
- Maximum tool calls, tokens, wall time, and output schema are deterministic configuration.
- Model output is untrusted until schema, evidence, policy, and approval checks pass.
- Provider and model remain open under ADR-0002.

### Proposed v2 tool layer

- The current proposal contains seven v2 tool names in `06_workflow_and_tool_contracts.md`.
- They are derived from Phase-1 lessons; they are not “exactly the seven tools from PharmaRetail”.
- Tool invocations execute under server-derived tenant and actor scope and return machine-readable provenance.
- Audit logging is a control-spine responsibility, not an eighth model-callable tool.

## Proposed persistence design

PostgreSQL on Amazon RDS is the default candidate for the first operational system of record. The logical design is:

| Record | Purpose |
|---|---|
| investigation run | current state, tenant, actor, timestamps, configuration/version pins |
| workflow event | append-only transition and integrity evidence |
| tool invocation | validated arguments/results hashes, latency, outcome, provenance |
| review decision | reviewer, decision, reason, approved payload hash, expiry |
| action outbox | idempotent post-approval write intent and delivery outcome |
| version registry | model, prompt, policy-corpus, tool-schema, and application versions |

Source documents and large immutable evaluation artifacts may live in S3; PostgreSQL stores their URI, content hash, classification, version, and tenant scope. dbt-core is proposed only for transformations that are clearer, testable, and reusable as data models; it is not required for transactional workflow state.

The table/schema layout, PostgreSQL RLS policy, partitioning, retention, backup, and recovery design remain subject to M0 review.

## Deployment and operations proposal

- Package the API/control spine and UI as Docker images.
- Run the smallest sufficient number of ECS Fargate services/tasks; API/worker separation is decided from measured workload needs.
- Send structured logs, metrics, and traces to CloudWatch with `run_id` and `tenant_id` correlation.
- Store service secrets in Secrets Manager; no static AWS credentials in the repository or container images.
- Use GitHub Actions for reviewed CI/CD. AWS authentication should use a short-lived/OIDC path if approved.
- No Snowflake compatibility layer or migration bridge is part of the target.

## Initial targets

All values are **TARGET**, not measured:

| Dimension | Initial target |
|---|---|
| Availability | 99.5% during agreed business hours |
| P50 intake-to-recommendation latency | ≤ 60 seconds |
| P95 intake-to-recommendation latency | ≤ 180 seconds |
| Cross-tenant or unauthorised leakage | 0; release blocker |
| Unsupported claim rate | ≤ 2% in the reviewed golden suite |
| Cost per investigation | measured before a numeric target is accepted |

## Review gates

M0 acceptance requires Honey’s architecture review, threat-model diff, Fizz verdict, and Osman approval. The review must explicitly resolve or defer:

- workflow-engine approach;
- persistence schema and approval/outbox transaction boundary;
- AWS region, networking/ingress, identity provider, and tenant model;
- UI technology;
- source-data and dbt-core boundary;
- LLM provider, retention, cost attribution, and external task integration.

No part of this proposal authorises Milestone-1 implementation.
