# Source code

This directory contains the closed bounded Issue #14 M1-I1 slice, the merged
Issue #17 M2-01/M2-02 execute-false shadow foundation, and the Issue #19 UAT /
real-shadow readiness bridge. The authoritative scope is
`docs/12_backlog_and_milestones.md` and ADR-0002–0006.

Only the local simulated T1–T3 investigation and human review path is implemented.
There is no AWS deployment, external write, workflow engine, production identity, or
live-model validation.

`stockoutops/shadow/` reuses the M1 intake/analysis path, persists separate shadow
results and deterministic diffs, and cannot enable execution or an external action.
Genuine UAT intake is shadow-only JSON persistence; it does not recruit users or
count synthetic cases toward M2-05.
