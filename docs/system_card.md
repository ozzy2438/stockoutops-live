# System Card — StockoutOps Live

> Owner: Honey + Orchestrator. Finalised at M5. This file is a **live scaffold** — sections are filled in as evidence accumulates.

**Current status:** Milestone-0 planning only. The system described below is intended behavior, not an implemented or deployed capability.

## Purpose & intended use

StockoutOps Live prepares a human-approved investigation and recovery recommendation for retail stockout / low-stock events. It is **not** an autonomous decisioning system and **not** a general-purpose assistant.

## Users & context

- Primary users: retail operations analysts and their leads inside participating tenants.
- Deployment context: internal, authenticated, tenant-isolated.
- Not for: consumer-facing use, supplier-facing outbound communication, autonomous purchasing or pricing decisions.

## Autonomy level

- Current: **A2 — approve-to-act.**
- History of changes: (populated as gates advance).

## Data

- Proposed evidence domains: inventory, sales and demand, supplier, promotion, SOP corpus, and incidents.
- Freshness SLAs: source-specific values remain part of the data-contract review.
- PII/data-classification inventory: required before M1 data access; location is not yet decided.
- RLS: proposed for PostgreSQL with application-level tenant checks; zero-leakage invariant.

## Model & prompts

- LLM provider / model: (from ADR-0002).
- Prompt bundle version: (from registry).
- Update policy: golden-case + shadow diff before promotion; Fizz sign-off.

## Tools

- Proposed v2 catalogue: seven allow-listed tools (T1–T7) with JSON-schema contracts. The catalogue is derived from Phase-1 lessons and is not the exact Phase-1 tool set — see `docs/06_workflow_and_tool_contracts.md`.
- No free-form execution.

## Guardrails

- Freshness gate.
- RBAC + RLS.
- Citation requirement for every recommendation field.
- Human approval before any external write.
- Autonomy pinned in config.

## Evaluation summary

- Golden-case pass rate (last release): (measured).
- Shadow-diff agreement (last window): (measured).
- Acceptance / edit / reject rates: (measured).
- Correct root-cause rate: (measured).
- P50 / P95 latency: (measured).
- Cost per investigation: (measured).
- RLS leakage: 0 (invariant).

## Known limitations

- Recommendation quality is bounded by the quality and freshness of the underlying marts.
- The SOP corpus is a snapshot; policy changes must be re-ingested and re-hashed.
- The operator study is a *controlled UAT experiment* — not a commercial production A/B test.
- The system is a decision-support tool. Final accountability lies with the human approver.

## Incidents & post-mortems

- Index at `docs/runbooks/postmortems/`.

## Live status label

- Current: *Milestone-0 planning scaffold — no application or live deployment.*
- After the required controlled UAT and failure-injection evidence: *Production-grade Stockout Investigation Platform validated through controlled UAT and failure-injection testing.*
- If real operators later use the system in a bounded process: *Human-supervised production pilot.*
- *Production-proven* is not used without real users and sustained operation.
