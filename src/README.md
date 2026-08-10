# Source code (not started)

> This directory intentionally contains only this README in Milestone 0. No application code or agent exists.
>
> No production code is written until:
> - Milestone 0 is complete (see `docs/12_backlog_and_milestones.md`),
> - Fizz has returned an APPROVE (or APPROVE WITH CONDITIONS) verdict,
> - Osman has approved the start of Milestone 1,
> - blocking architecture, workflow, persistence, identity, and tool-contract decisions are accepted.
>
> The following M1 layout is illustrative and remains subject to those decisions:
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
