# StockoutOps Live

**Human-Supervised AI Decisioning & Reliability Platform**

> **Current implementation status: M1 local simulated human-supervised vertical slice — implementation candidate pending evidence and assurance.** This is not production-ready, production-proven, deployed to AWS, or evidence of model or business quality. Milestone-gate status is determined by `docs/12_backlog_and_milestones.md` and its linked GitHub evidence.

StockoutOps Live is the new canonical Phase-2 implementation. The [PharmaRetail AI Control Tower](https://github.com/ozzy2438/PharmaRetail-AI-Control-Tower) is reference material only; useful patterns may be selectively migrated after review, but the old project is not a runtime dependency or a codebase to copy wholesale.

AWS is the target cloud. The preferred simple stack is Python, PostgreSQL/Amazon RDS, S3 where needed, dbt-core where justified, FastAPI, a lightweight human-review UI, Docker, ECS Fargate, CloudWatch, Secrets Manager, and GitHub Actions. Architecture v2, workflow engine, persistence design, and tool contracts are Milestone-0 proposals. Accepting the planning scaffold does not select unresolved technical options; accepted ADRs govern implementation.

## M1 local execution

The accepted M1 subset is intentionally smaller than the future architecture: one
simulated stockout case, PostgreSQL 16, T1–T3 evidence, one deterministic reasoning
step, and a human review decision. It performs no external write.

```bash
make setup
make up
make test
make smoke-stub
make down
```

`make up` builds the image, starts PostgreSQL 16, applies ordered plain-SQL
migrations, verifies/seeds the SHA-256 fixture manifest, and starts FastAPI. The review
page is at `http://127.0.0.1:8000/review`. Generated local bearer tokens live only
under ignored `.local/`; do not put them in URLs, logs, screenshots, source files, or
browser storage.

For a host-Python path, export the values in `.env.example`, then run
`make migrate`, `make seed`, and `make serve`. Migrations are repeatable and use
the migration role; the application uses the restricted `stockoutops_app` role.

### M1 architecture-to-code map

| Responsibility | Implementation |
|---|---|
| FastAPI and same-origin Jinja review page | `src/stockoutops/api.py`, `templates/review.html` |
| Deterministic state/control spine | `state_machine.py`, `service.py` |
| Server-derived local identity | `identity.py` |
| PostgreSQL transactions and tenant boundary | `database.py`, `repository.py`, `migrations/` |
| T1–T3 contracts, provenance, freshness and fixtures | `evidence/`, `fixtures/v1/` |
| Stub and provider-neutral OpenAI boundary | `reasoning/` |

Security boundaries are fail-closed: client-supplied identity/tenant/role is rejected,
cross-tenant reads return 404, evidence must pass schema/freshness/provenance checks
before reasoning, citations are bound after reasoning, review is bound to reviewer,
tenant, draft hash and PT24H expiry, and audit mutation is denied by permissions and a
database trigger. This local application does not implement production IdP, sessions,
MFA, RLS, backup/PITR, distributed execution, or external writes.

Recovery is restart plus retry with the original idempotency key. The same request
returns the durable `run_id`; completed or failed reasoning is not automatically
called again. Rollback is to stop the local app and retain PostgreSQL evidence/audit
for inspection; migrations are forward-only and non-destructive.

No live OpenAI call was made during M1-I1 implementation. The OpenAI adapter is tested
with an injected mock only; local and CI execution use `DeterministicStubAdapter`.

---

## 1. Business Problem

Retail operations teams receiving a stockout or low-stock alert today manually assemble evidence from many places: current stock, recent sales & demand, open orders, supplier lead time, promotion/campaign impact, store & SKU comparisons, relevant SOP or operations policy, and prior similar incidents. This is slow, inconsistent between analysts, and the evidentiary basis of the final decision is often not traceable after the fact.

## 2. Intended Workflow

Once implemented and admitted through the rollout gates, a stockout alert or investigation request will follow this workflow:

1. Validates identity, tenant, eligibility and data freshness.
2. Persists a workflow record with a durable `run_id`.
3. Retrieves inventory, sales, supplier, promotion and approved SOP evidence.
4. Runs deterministic quality and policy checks.
5. Uses AI to identify likely root cause and affected scope.
6. Prepares a **cited** recovery recommendation.
7. Requires **human approval / edit / reject / escalate** before any write action.
8. Creates the approved incident/task record.
9. Records audit, outcome, latency, cost and quality telemetry.

## 3. Initial Autonomy — A2 (approve-to-act)

**Once implemented, the bounded agent may:** read governed data; fetch supplier and promotion evidence; retrieve SOP/policy evidence; check freshness and data quality; find similar incidents; propose root cause and affected scope; prepare a recovery recommendation; draft an incident/task.

**After human approval only:** create the approved incident/task; send notification to the assigned owner; record investigation outcome.

**Forbidden in V1:** automatic purchase-order changes; automatic inventory transfers; pricing or promotion changes; supplier commitments; deletion of records; unapproved outbound communication; direct unrestricted DB writes.

> Agentic reasoning is used **only** where genuine uncertainty exists. Identity, authorization, freshness, approval, write and audit remain deterministic.

## 4. Rollout Gates

| Gate | Name | Purpose |
|------|------|---------|
| G0 | Historical replay | Known-outcome cases, blind, measure correctness, tool choice/order, evidence completeness, escalation, unsupported claims |
| G1 | Shadow mode | Agent analyses live UAT cases; **no** actions; compare against analyst |
| G2 | Assisted operation | Approve/edit/reject/escalate; only approved low-risk tasks created |
| G3 | Low-risk canary | Small workload slice, feature-flagged, fast rollback |
| G4 | Controlled operation | 8–12 weeks of planned workload, monitoring, incidents and releases |

## 5. Success Metrics (no vibes)

| Dimension | Metric |
|-----------|--------|
| Business workflow | Median investigation time |
| User acceptance | Recommendation acceptance rate |
| Human intervention | Edit and rejection rate |
| Decision quality | Correct root-cause rate |
| Risk mgmt | Correct escalation rate |
| Evidence | Citation & evidence completeness |
| Tool quality | Tool-call success & argument validity |
| Security | RLS leakage / unauthorised access (must be 0) |
| Reliability | Availability, retry & recovery success |
| Performance | P50 / P95 investigation latency |
| Economics | Cost per investigation |
| Operations | Incident recurrence, duplicate action count |

## 6. Definition of Done

The project is done **only** when all of the following are true:

- Real AWS deployment with auth and RBAC.
- ≥ 3 external UAT users.
- 8–12 weeks of continuous operation.
- Scheduled runs and a release history.
- Structured logs, `run_id`, distributed traces.
- Operational dashboard.
- Defined SLOs with automated alerts.
- Model / prompt / tool version registry.
- Golden-case regression suite.
- Shadow model & prompt evaluation.
- Canary + rollback.
- ≥ 6 failure-injection scenarios executed.
- ≥ 1 real incident post-mortem.
- Cost-per-investigation report.
- Baseline vs assisted workflow comparison.
- User acceptance / edit / reject evidence.
- Traceable Issue → Branch → PR → independent review → Release history.
- Architecture, tool contracts, threat model, runbooks, system card.
- Independent final **APPROVE** verdict by **Fizz**.
- Honest live-status label.

### Honest labelling

- Current state: **M1 local simulated human-supervised vertical slice — implementation candidate pending evidence and assurance.**
- Only after controlled UAT and failure-injection evidence: **Production-grade Stockout Investigation Platform validated through controlled UAT and failure-injection testing.**
- If real retail operators later use it under a bounded process: **Human-supervised production pilot.**
- **Never** use the phrase *production-proven* without real users and sustained operation.

## 7. Team (Buzz)

| Agent | Responsibility |
|-------|----------------|
| Orchestrator | Repo audit, scope, milestones, backlog, delivery gates |
| Honey | Architecture v2, durable workflow state, tool contracts, RBAC, threat model, SLOs |
| Bumble | Implementation, deployment, CI/CD, telemetry, alerts, recovery, runbooks |
| Scout | Baseline, golden cases, evaluation methodology, UAT, operator study, evidence pack |
| Fizz | Independent risk review, adversarial tests, failure injection, release verdict (APPROVE / APPROVE WITH CONDITIONS / BLOCK) |

Fizz does **not** report into the implementation team.

Only `APPROVE` opens a milestone gate. `APPROVE WITH CONDITIONS` pauses merge and progression until the conditions are resolved and Fizz approves the new head; `BLOCK` stops the milestone.

## 8. Repository Map

```text
.
├── docs/                       # All governance & design docs
│   ├── 00_project_charter.md
│   ├── 01_current_state_audit.md
│   ├── 02_gap_matrix.md
│   ├── 03_scope.md
│   ├── 04_baseline_plan.md
│   ├── 05_architecture_v2.md
│   ├── 06_workflow_and_tool_contracts.md
│   ├── 07_threat_model.md
│   ├── 08_evaluation_plan.md
│   ├── 09_rollout_plan.md
│   ├── 10_observability_slo_cost.md
│   ├── 11_failure_injection.md
│   ├── 12_backlog_and_milestones.md
│   ├── 13_risks_and_open_decisions.md
│   ├── system_card.md
│   ├── glossary.md
│   ├── decisions/              # ADRs
│   ├── runbooks/               # Operational runbooks
│   └── team/                   # Roles & RACI
├── evaluation/
│   ├── golden_cases/
│   ├── replay/                 # G0 historical replay
│   ├── shadow/                 # G1 shadow-mode analysis
│   └── uat/                    # G2 operator study
├── observability/              # Dashboards, alert rules, SLO defs
├── infra/                      # IaC, deployment, secrets scaffolding
├── src/stockoutops/            # Bounded M1 application
├── migrations/                 # Ordered, forward-only PostgreSQL SQL
├── fixtures/v1/                # Hash-manifested simulated T1–T3 fixtures
├── tests/                      # Unit and real-PostgreSQL integration tests
├── milestones/                 # Per-milestone deliverable folders
└── .github/                    # Templates, workflows, CODEOWNERS
```

## 9. How Work Flows

1. Every unit of work starts as a GitHub **Issue** using the correct template.
2. Work happens on a **branch** named `<type>/<issue-#>-<slug>` — never on `main`.
3. A **Pull Request** links the issue and fills the PR template completely.
4. **Independent review** is required. For milestone gates, **Fizz** must approve.
5. Merges are squash-only; releases are tagged `vMAJOR.MINOR.PATCH`.
6. `main` is protected: required reviews, required status checks, no force-push, no direct commits.

## 10. Milestone 0 — Completed planning baseline

Milestone 0 remains the documentation baseline under `docs/` and
`milestones/M0-planning/`. The authoritative small M1 scope and its remaining gates
are in `docs/12_backlog_and_milestones.md`.

---

*Last updated: 2026-08-11 M1-I1 local implementation candidate. Owner: Osman Orka. Independent M1 evidence and assurance remain pending.*
