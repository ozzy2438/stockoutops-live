# Tests

> Empty in Milestone 0. Layout target for M1+:
>
> ```
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
