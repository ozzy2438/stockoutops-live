# Tests (not started)

> No test code exists in Milestone 0. Proposed layout for M1+:
>
> ```text
> tests/
> ├── unit/              # per-module unit tests
> ├── contract/          # tool JSON-schema contract tests
> ├── workflow/          # state-machine transitions & idempotency
> ├── rls/               # zero-leakage invariants (blocking in CI)
> ├── integration/       # end-to-end against staging fixtures
> └── property/          # property-based tests for parsers/validators
> ```
>
> Passing tests are necessary but **not sufficient** for milestone completion (see `README.md` §6 and `CONTRIBUTING.md`).
