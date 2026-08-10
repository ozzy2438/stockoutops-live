# 0001. Record architecture decisions

- **Status:** Accepted
- **Date:** repo bootstrap
- **Deciders:** Orchestrator, Honey

## Context

We need a lightweight, durable, and searchable record of decisions that constrain future work. Reviewers need to understand *why* a choice was made and under what conditions it should be revisited.

## Decision

Use Nygard-style ADRs stored under `docs/decisions/`. Numbered sequentially. Every ADR follows `adr-template.md`. Status is one of Proposed / Accepted / Superseded / Deprecated. ADRs are immutable once merged; changes are made via new ADRs that supersede the previous.

## Consequences

### Positive

- Explicit, reviewable, versioned decision history.
- New contributors can trace *why*, not just *what*.

### Negative / trade-offs

- Adds friction to trivial decisions if applied too broadly. Mitigation: use ADRs only for the classes listed in `docs/decisions/README.md`.

## Alternatives considered

- Free-form wiki — rejected: no versioning discipline, harder to review.
- Inline README updates only — rejected: loses history and rationale.
