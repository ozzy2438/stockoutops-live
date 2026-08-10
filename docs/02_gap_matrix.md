# 02 — Gap-to-Deliverable Matrix

> Status: **populated for the Milestone-0 handoff** from the high-level Phase-1 audit. Live gate state and evidence are authoritative in `12_backlog_and_milestones.md` and [GitHub PR #6](https://github.com/ozzy2438/stockoutops-live/pull/6); this matrix does not encode temporal gate status.

## Legend

- `PRESENT` — the required capability and relevant evidence are in place.
- `PARTIAL` — a useful Phase-1 pattern or artifact exists, but it does not satisfy the Phase-2 requirement.
- `ABSENT` — no usable current capability was found.
- Evidence labels are **MEASURED**, **SIMULATED**, **ASSUMED**, and **TARGET** as defined in `01_current_state_audit.md`.

## Matrix

| # | Definition-of-Done requirement | Phase-1/current state | Gap to StockoutOps Live | Owner | Earliest milestone | Evidence |
|---|---|---|---|---|---|---|
| 1 | Real AWS deployment with auth and RBAC | **ABSENT** — the Snowflake account is closed; the UI is an offline demo without real auth. | Review architecture; implement authenticated FastAPI/UI on ECS Fargate with RDS tenant controls. | Honey/Bumble | M1 | MEASURED / ASSUMED / TARGET |
| 2 | ≥ 3 external UAT users | **ABSENT** | Recruit, consent, and record genuine external participants. | Scout | M2–M3 | TARGET |
| 3 | 8–12 weeks continuous operation | **ABSENT** | Establish a real controlled-operation window after earlier gates pass. | Bumble | M5 | TARGET |
| 4 | Scheduled runs and release history | **PARTIAL** — Phase-1 GitHub workflows and PR history exist, but no current application deployment/release line exists. | Define Phase-2 release, schedule, rollback, and evidence process. | Bumble | M1 | MEASURED / TARGET |
| 5 | Structured logs, durable `run_id`, and traces | **PARTIAL** — append-only query-hash audit exists; no end-to-end `run_id` or distributed traces. | Persist run state/events and export correlated telemetry to CloudWatch. | Honey/Bumble | M1 | MEASURED / TARGET |
| 6 | Operational dashboard | **ABSENT** — the Streamlit investigation screen is not an operations dashboard. | Build CloudWatch operational views only after signals exist. | Bumble | M2 | MEASURED / TARGET |
| 7 | Defined SLOs and automated alerts | **PARTIAL** — targets are documented in this scaffold; no measured SLIs or alerts exist. | Baseline, implement, alert, and validate error budgets. | Honey/Bumble | M2 | TARGET |
| 8 | Model/prompt/tool version registry | **PARTIAL** — immutable contracts and a fixed allow-list exist; no full registry or promotion history. | Design and persist a version registry tied to every `run_id`. | Honey | M1 | MEASURED / TARGET |
| 9 | Golden-case regression suite | **PARTIAL** — Phase-1 has synthetic RAG and agent tests, not the v2 end-to-end blinded suite. | Curate ≥ 34 v2 cases with provenance, rubric, and blocking thresholds. | Scout | M1 | SIMULATED / TARGET |
| 10 | Shadow model/prompt evaluation | **ABSENT** | Implement `execute=false` shadow capture and version-diff reporting. | Scout | M2 | TARGET |
| 11 | Canary and rollback | **ABSENT** | Define feature flags, workload slice, kill switch, and rollback evidence. | Bumble | M4 | TARGET |
| 12 | ≥ 6 executed failure-injection scenarios | **ABSENT** — security tests are not executed failure-injection exercises. | Run and evidence the approved catalogue in bounded environments. | Fizz/Bumble | M3–M5 | TARGET |
| 13 | ≥ 1 real incident post-mortem | **ABSENT** — no qualifying Phase-2 operational post-mortem exists. | Capture a genuine incident; do not manufacture one to meet the gate. | Bumble/Fizz | M4–M5 | TARGET |
| 14 | Cost-per-investigation report | **ABSENT** | Choose attribution method; capture LLM plus AWS/RDS/ECS/S3 costs per run. | Scout/Bumble | M3–M5 | TARGET |
| 15 | Baseline vs assisted workflow comparison | **ABSENT** | Execute the pre-registered baseline and controlled comparison. | Scout | M2–M3 | TARGET |
| 16 | Acceptance/edit/reject evidence | **ABSENT** | Persist real review decisions and report them without fabricated users. | Scout | M3 | TARGET |
| 17 | Traceable Issue → branch → PR → independent review → release history | **PARTIAL** — Phase-1 issue/PR/CI history is useful; the Phase-2 review/release chain is not yet established. | Enforce branch protection and preserve independent review evidence for every milestone. | Orchestrator | Continuous | MEASURED / TARGET |
| 18 | Architecture, tool contracts, threat model, runbooks, and system card | **PARTIAL** — M0 documents exist, but architecture, persistence, workflow, and tools are proposals; runbooks are an index. | Accept the M0 planning baseline through the authoritative gate; resolve each deferred technical decision before its dependent implementation. | Honey/Fizz | M0–M1 | MEASURED / TARGET |
| 19 | Independent final assurance | **ABSENT** | Fizz must issue a recorded final `APPROVE`; a conditional verdict pauses and `BLOCK` stops the gate. | Fizz | M5 | TARGET |
| 20 | Honest live-status label | **PARTIAL** — the repository now correctly says “Milestone 0, no implementation”; the final operating label depends on later evidence. | Re-evaluate at every gate and before any external claim. | Orchestrator/Fizz | Continuous/M5 | MEASURED / TARGET |

## Deferred technical decisions

The authoritative list is `13_risks_and_open_decisions.md`. M0 scaffold acceptance does not decide these items. Each must be resolved or explicitly deferred before the dependent Milestone-1 implementation begins:

- workflow-engine approach and durable PostgreSQL persistence design;
- AWS region, network/ingress, identity provider, and tenant-authorisation model;
- proposed v2 tool contracts and source-data contracts;
- LLM provider/model and prompt/response retention;
- human-review UI technology and approved task/notification integration;
- dbt-core boundary, cost attribution, and evaluation/UAT definitions.
