# Source code

> This directory is intentionally **empty** in Milestone 0.
>
> No production code is written until:
> - Milestone 0 is complete (see `docs/12_backlog_and_milestones.md`),
> - Fizz has returned an APPROVE (or APPROVE WITH CONDITIONS) verdict,
> - Osman has approved the start of Milestone 1,
> - ADR-0002 (LLM provider) and the workflow-engine ADR are accepted.
>
> The intended M1 layout is:
>
> ```
> src/
> ├── intake/            # request validation, freshness, identity, tenancy
> ├── workflow/          # durable state machine, run_id, audit events
> ├── tools/             # T1..T7 with schema-validated contracts
> ├── agent/             # LLM adapter, prompt registry, bounded reasoning
> ├── review/            # human approve/edit/reject/escalate UI + API
> ├── executor/          # post-approval write executor
> ├── audit/             # append-only log writers
> └── observability/     # logging, tracing, metrics, cost telemetry
> ```
