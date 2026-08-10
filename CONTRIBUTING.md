# Contributing to StockoutOps Live

This project is deliberately governed. Please read this file **before** opening an issue or PR.

## Ground rules

1. **Never push to `main`.** Every change goes through Issue → Branch → PR → independent review → merge.
2. **No fabricated evidence.** Never invent users, clients, incidents, latency numbers, cost figures or business outcomes. Clearly distinguish *measured*, *simulated*, *assumed* and *target*.
3. **No scope creep.** New tools, dependencies or agent capabilities require a written ADR (`docs/decisions/`) and Honey + Fizz sign-off.
4. **Passing tests are not milestone completion.** A milestone gate opens only when its documented evidence is complete and Fizz returns `APPROVE`. `APPROVE WITH CONDITIONS` pauses merge until the conditions are resolved and Fizz approves the new head; `BLOCK` stops the milestone.
5. **Autonomy stays at A2 (approve-to-act) until a documented rollout gate says otherwise.**

## Branching

- Naming: `<type>/<issue-#>-<short-slug>` where `<type>` is one of `feat`, `fix`, `docs`, `chore`, `test`, `refactor`, `infra`, `eval`, `runbook`.
- Example: `feat/42-shadow-mode-runner`.

## Commits

- Conventional Commits: `type(scope): subject`.
- Reference the issue in the body: `Refs #42`.
- Keep commits atomic. Squash on merge.

## Pull Requests

- Use the PR template. Do not delete sections; write `N/A` if not applicable.
- A PR must link its issue, list evidence produced, and declare risk level.
- **Independent reviewer required** (someone other than the author).
- For any change that touches: agent prompts, tool contracts, RBAC, threat model, rollout gates, evaluation methodology, or observability SLOs → **Fizz review is mandatory**.
- CI must be green. Coverage may not drop below the last release's number.

## ADRs

Any decision that constrains future work (framework choice, data contract change, autonomy change, new external dependency, prompt-family change) requires an ADR. Copy `docs/decisions/adr-template.md` and increment the number.

## Reviewing checklist

- Does this change match its issue's stated scope?
- Is there an updated or new ADR if required?
- Are prompts / tools / permissions changes accompanied by an updated threat model diff?
- Is there test / eval evidence appropriate for the change type?
- Are observability signals (logs, traces, metrics, run_id, tenant) preserved?
- Are there any *unsupported claims* in code comments, docs, or PR body?

## Reporting security issues

See `SECURITY.md`. Do **not** open a public issue for a suspected vulnerability.
