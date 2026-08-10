# 13 — Risks, Assumptions & Open Decisions

> Owner: Orchestrator. Live document — updated at every milestone PR.

## Legend

- **Risk** = something that can go wrong; has probability & impact.
- **Assumption** = something we’re taking as true without proof; will be validated.
- **Open decision** = a choice not yet made; blocks specific issues.

## Risks (initial)

| ID | Risk | Prob | Impact | Owner | Mitigation |
|----|------|:----:|:------:|-------|------------|
| R-01 | Insufficient real UAT users (< 3) | M | High | Scout | Recruit early in M1; have back-up pool. |
| R-02 | Hosted LLM cost blowout | M | Med | Bumble | Token/latency caps; per-tenant budgets; alerts. |
| R-03 | Prompt injection via SOP corpus | M | High | Honey/Fizz | Curated corpus; ingestion signing; FI-5 exercise. |
| R-04 | RLS regression | L | Critical | Honey | Automated tests, blocking CI, FI-4. |
| R-05 | Golden-case dataset drift from reality | M | Med | Scout | Refresh quarterly; add new categories on incidents. |
| R-06 | Operator study underpowered | M | Med | Scout | Pre-register N; report CIs, not point estimates. |
| R-07 | Autonomy scope creep | M | High | Fizz | Autonomy pinned in config; ADR + Fizz approval required. |
| R-08 | Vendor lock-in on LLM provider | M | Med | Honey | Adapter interface; ADR-0002 mandates portability. |
| R-09 | Snowflake credit spikes | L | Med | Bumble | Warehouse sizing policy; per-tool row caps. |
| R-10 | Team over-claiming (“production-proven”) | M | High | Orchestrator | Labelling rules; Fizz review of every external claim. |

## Assumptions (initial)

- A-01: Existing PharmaRetail RLS & audit-log design is sound enough to build on. **Validate in M0-01.**
- A-02: The 7 allow-listed tools cover the M1 scope. **Validate in M0-06.**
- A-03: Osman can source ≥ 3 UAT users. **Validate before M2.**
- A-04: A hosted LLM with function-calling suffices; we do not need self-hosted. **Validate in ADR-0002.**
- A-05: A workflow engine is cheaper to adopt than to build. **Validate in an ADR before M1.**

## Open decisions (blocking issues reference these)

- **OD-01** — LLM provider & model family (owner: Honey; deadline: end of M0). → ADR-0002.
- **OD-02** — Workflow engine (build vs adopt; e.g. Temporal, Prefect, custom). → ADR-0003.
- **OD-03** — Hosting target (managed vs self-hosted; region). → ADR-0004.
- **OD-04** — Cost-attribution method (per-run vs monthly amortised). → ADR-0005.
- **OD-05** — Retention policy for LLM prompt/response bodies. → ADR-0006.
- **OD-06** — UAT consent form & data-usage terms. → Scout.
- **OD-07** — Operator-study primary metric operational definition (TTD boundaries). → Scout.

## Change log

- Repo bootstrap — Doc created.
