# M2 shadow foundation

The implemented candidate is a local/containerised engineering rehearsal over
controlled-synthetic cases. M2-01 and M2-02 are merged via PR #18. PR #20 merged
the Issue #19 UAT/real-shadow readiness bridge; it is not live UAT, the first 100
genuine cases, or G1 exit evidence.

Every case and persisted shadow run is hard-locked to `execute=false`. The CLI has
no true mode, the service rejects `execute=true` before persistence or analysis, and
PostgreSQL has `CHECK (execute = false)` plus `external_action_count = 0`. There is no
external executor, ticket, email, task, supplier write, or review decision in this
path.

## Case contract

`cases/v1/cases.json` is pinned by `cases/v1/manifest.json`. The strict contract
records case/version, tenant, injected `as_of_timestamp`, M1 request, fixture facts,
reference outcome and escalation, minimum evidence/citation expectations,
provenance, de-identification status, consent/data-use status, notes, and
limitations. The committed 12-case pack remains:

- `controlled_synthetic_reference`
- `SIMULATED`
- `deidentification_status = not_applicable_controlled_synthetic`

Future genuine de-identified cases may use `analyst_reference` /
`GENUINE_UAT_ANALYST_LABELLED` with an opaque offline consent reference. No such
record is committed in this pack.

## Missing required evidence

See `METRICS.md`. The canonical count is the number of case-specific
`required_tools` absent from actual evidence. Unused T1/T2/T3 slots are not
counted. `actual` and comparison/aggregate metrics share this definition.
Historical three-tool-slot `actual` values remain historical.

## Processing and persistence

The processor invokes the existing deterministic M1 `InvestigationService.intake`
path with `run_mode=shadow` and stops before any human decision. Server-side review
rejects shadow runs, and the local review page disables its decision controls.
Dedicated PostgreSQL `shadow_run`,
`shadow_diff`, and `shadow_control_event` records preserve tenant, versions, hashes,
provider metadata, and zero external actions without overloading `review_decision`.

Two ordered PostgreSQL advisory locks cover the tenant/idempotency key and the
tenant/case/version/processor identity. Repeated or concurrent equivalent requests
converge on one shadow run and one M1 reasoning invocation. A conflicting payload
fails closed and is audited. Completed runs permit no further update/delete;
field-diff and control-event rows are append-only under both permissions and database
triggers. These controls are not WORM or cryptographic tamper evidence.

## Diff report contents

- Exact structured outcome and escalation agreement.
- Recommendation action-type and confidence agreement where defined.
- Required evidence and citation coverage.
- Unsupported citation and missing required evidence counts.
- Deterministic provider/cost labels and latency metadata.
- Per-field disagreement categories; no LLM-as-judge or semantic score.

Per-case JSON and aggregate JSON/Markdown are generated beneath
`evaluation/reports/`. Final handoff evidence may instead be written under the
immutable-date convention in `/Users/osmanorka/.buzz/OUTBOX/`.

## Run locally

```bash
make migrate
make shadow-cases
make shadow-pilot
make shadow-collection
```

Genuine UAT import, when owner-approved de-identified JSON exists later:

```bash
make shadow-intake INPUT=path/to/intake.json
```

Intake does not run analysis. The committed tree contains no genuine intake file.

The pilot requires the migration/admin DSN only to seed controlled fixtures and the
restricted application DSN for processing/persistence. Local and CI use only
`DeterministicStubAdapter`; no OpenAI key or network model call is used.

## Recovery, disable, and rollback

- Retry with the same case/version/processor identity. The advisory lock serialises
  an active peer; a durable `started` row resumes through M1's existing idempotency.
- Disable by not invoking `stockoutops-shadow-pilot` or intake/collection CLIs; no
  long-running consumer or external integration exists.
- Code rollback is a revert of the implementation commit. Migrations 0004 and 0005
  are additive and forward-only; retain immutable shadow evidence for inspection
  rather than using a destructive down migration.

## Honest status and handoff

- M2-01 engineering foundation merged (PR #18).
- M2-02 engineering foundation merged (PR #18).
- UAT/real-shadow readiness bridge merged (PR #20); no users or genuine cases exist.
- M2-03 pending — no users recruited or consent recorded.
- M2-04 pending — Issue #21 is a local/CI policy candidate with no delivered alert
  or SLO-compliance evidence.
- M2-05 pending — these 12 cases are not the first 100 genuine shadow cases.
- M2-06 pending — no G1 exit report, Fizz verdict, or owner completion decision.

Future genuine UAT collection is an Owner/Scout action. Do not relabel synthetic
records as analyst decisions or use this deterministic rehearsal to claim reasoning
quality, accuracy, reliability, adoption, ROI, SLOs, or business impact.
