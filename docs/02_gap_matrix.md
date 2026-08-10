# 02 — Gap-to-Deliverable Matrix

> Status: **template**. Orchestrator + Scout fill during M0.

## How to read this

Each row maps a **Definition-of-Done** requirement from `README.md` §6 to its current state in PharmaRetail today, the gap, the owner, and the milestone where it will be closed.

## Legend

- `PRESENT` — fully in place; only verification needed.
- `PARTIAL` — partially in place; needs extension.
- `ABSENT` — not in place; needs to be built.
- Evidence label: **M**easured / **S**imulated / **A**ssumed / **T**arget.

## Matrix

| # | DoD requirement | Current state | Gap description | Owner | Milestone | Evidence label |
|---|-----------------|---------------|------------------|-------|-----------|-----------------|
| 1 | Real cloud deployment with auth & RBAC | | | Bumble | M1 | |
| 2 | ≥ 3 external UAT users | | | Scout | M2–M3 | |
| 3 | 8–12 weeks of continuous operation | | | Bumble | M5 | |
| 4 | Scheduled runs & release history | | | Bumble | M1 | |
| 5 | Structured logs, run_id, traces | | | Bumble | M1 | |
| 6 | Operational dashboard | | | Bumble | M2 | |
| 7 | Defined SLOs + automated alerts | | | Honey/Bumble | M2 | |
| 8 | Model/prompt/tool version registry | | | Honey | M1 | |
| 9 | Golden-case regression suite | | | Scout | M1 | |
| 10 | Shadow model/prompt evaluation | | | Scout | M2 | |
| 11 | Canary + rollback | | | Bumble | M4 | |
| 12 | ≥ 6 failure-injection scenarios | | | Fizz + Bumble | M3–M5 | |
| 13 | ≥ 1 real incident post-mortem | | | Bumble + Fizz | M4–M5 | |
| 14 | Cost-per-investigation report | | | Scout | M3–M5 | |
| 15 | Baseline vs assisted workflow comparison | | | Scout | M2–M3 | |
| 16 | User acceptance/edit/reject evidence | | | Scout | M3 | |
| 17 | Traceable Issue → PR → review → release history | | | Orchestrator | continuous | |
| 18 | Architecture, tool contracts, threat model, runbooks, system card | | | Honey | M0 | |
| 19 | Independent final assurance | | | Fizz | M5 | |
| 20 | Honest live-status label | | | Orchestrator | M5 | |

## Open questions / unresolved dependencies

- LLM provider decision (see `docs/decisions/`).
- Hosting target for the Streamlit / API layer.
- UAT user recruitment source and consent form.
- Cost-attribution method (per-run vs monthly amortised).
- Data-residency / privacy constraints from Osman.
