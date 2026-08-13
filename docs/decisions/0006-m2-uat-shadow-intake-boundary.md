# 0006. Local genuine-UAT shadow intake and contract-derived evidence metrics

- **Status:** Proposed
- **Date:** 2026-08-13
- **Deciders:** TBD pending Buzz/Fizz assurance and owner merge
- **Consulted:** Scout (methodology), Fizz (evaluation/privacy)
- **Informed:** Orchestrator, Honey

## Context

PR #18 merged the M2-01/M2-02 execute-false shadow foundation. Scout identified a
non-blocking methodology residual: `actual.missing_required_evidence_count` used a
hardcoded three-tool-slot formula while the aggregate/comparison metric used each
case's `required_tools`. M2-03 recruitment and M2-05 genuine-100 collection still
need a safe contract, intake path, and counting rule that cannot treat synthetic
cases as genuine UAT evidence. AWS, OpenAI, and live users remain out of scope.

## Decision

- Define missing required evidence as the count of case-contract `required_tools`
  absent from actual evidence. Keep T1–T3 as the only legal tool names.
- Extend the existing shadow case contract with provenance, baseline source,
  de-identification, and opaque consent-reference fields. Defaults preserve the
  committed 12-case controlled-synthetic pack.
- Accept future genuine cases only through a local JSON intake path into
  PostgreSQL. Duplicate identity with the same hash replays; a conflicting payload
  fails closed. Intake does not run analysis and cannot set `execute=true`.
- Count a case toward official M2-05 only when it is
  `GENUINE_UAT_ANALYST_LABELLED` / `analyst_reference` and has an append-only
  `accepted_for_m2_05` event. Synthetic cases contribute zero.
- Keep signed consent and participant PII outside the public repository.

## Consequences

### Positive

- One measurement definition for actual, comparison, and aggregate missing-evidence
  counts.
- A fail-closed path for later genuine UAT cases without inventing those cases now.

### Negative / trade-offs

- Historical `actual.missing_required_evidence_count` values from the three-slot
  formula remain historical and must not be rewritten.
- Official M2-05 still starts at zero until later authorised collection.

### Neutral

- No new platform, broker, cloud service, or model provider is introduced.
- M2-04 SLO alerts remain unimplemented.

## Alternatives considered

- **Keep the three-slot actual metric** — rejected; it disagrees with the case
  contract on subset `required_tools` cases.
- **Put genuine cases into the synthetic pack** — rejected; it would mix evidence
  classes.
- **External queue or warehouse intake** — rejected as out of authorised scope.

## Follow-ups

- Issues opened: #19
- Docs updated: `evaluation/shadow/METRICS.md`, UAT templates, threat-model delta
- Tests / evaluation impact: contract, intake, collection, and PostgreSQL tests;
  synthetic cases must continue to contribute `0` to official M2-05
