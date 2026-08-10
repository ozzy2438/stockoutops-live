## Summary

<!-- One-paragraph description of what this PR changes and why. -->

## Linked issue

Closes #

## Type of change

- [ ] feat (new capability)
- [ ] fix (bug fix)
- [ ] docs
- [ ] chore / infra
- [ ] test / evaluation
- [ ] refactor
- [ ] runbook

## Change scope declaration

- [ ] This change is within the scope stated on the linked issue.
- [ ] No new external dependency was added (or an ADR was added: `docs/decisions/NNNN-*.md`).
- [ ] No change to agent autonomy level (still A2).
- [ ] No change to tool contracts (or `docs/06_workflow_and_tool_contracts.md` was updated).
- [ ] No change to RBAC / RLS / tenancy (or `docs/07_threat_model.md` was updated).
- [ ] No change to rollout gates (or `docs/09_rollout_plan.md` was updated).

## Evidence produced

<!-- Link tests, eval runs, screenshots, dashboards, log excerpts. -->
<!-- Clearly label each item as MEASURED / SIMULATED / ASSUMED / TARGET. -->

## Risk & rollback

- Risk level: `low` | `medium` | `high`
- Feature flag: `N/A` or `<flag_name>`
- Rollback plan: <!-- how to disable/revert in <5 minutes -->

## Reviewers

- Author: @
- Independent reviewer: @
- Fizz review required? `yes` | `no` — required if this touches prompts, tool contracts, RBAC, threat model, rollout, evaluation methodology or SLOs.

## Checklist

- [ ] I did not push directly to `main`.
- [ ] Branch name follows `<type>/<issue-#>-<slug>`.
- [ ] Commit messages follow Conventional Commits.
- [ ] CI is green.
- [ ] Docs / ADRs updated as required.
- [ ] No fabricated metrics, users or outcomes.
- [ ] Observability preserved (run_id, tenant, structured logs, traces).
