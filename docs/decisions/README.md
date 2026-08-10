# Architecture Decision Records (ADRs)

We use lightweight ADRs (Michael Nygard style) to record decisions that constrain future work.

## When to write an ADR

- Framework / library / vendor choice.
- Data-contract change or new mart.
- Autonomy-level change.
- New external dependency.
- New tool or tool-schema change.
- Prompt-family change.
- Retention / privacy policy change.
- SLO change.

## Process

1. Copy `adr-template.md` to `NNNN-short-slug.md` using the next number.
2. Set status to `Proposed`.
3. Open a PR with the ADR; link the driving issue.
4. Get required reviewers (Honey for design; Fizz for anything security / autonomy / evaluation-related).
5. On merge, set status to `Accepted`.
6. If later revised or reversed, keep the file and add a follow-up ADR that supersedes it.

## Index

- `0001-record-architecture-decisions.md` — Accepted.
- `0002-choose-llm-provider.md` — Accepted for M1; effective after scope-lock merge.
- `0003-use-explicit-m1-state-machine.md` — Accepted for M1; effective after scope-lock merge.
- `0004-use-local-postgres-for-m1-state-and-evidence.md` — Accepted for M1; effective after scope-lock merge.
- `0005-use-local-simulated-identity-for-m1.md` — Accepted for local M1; effective after scope-lock merge.
