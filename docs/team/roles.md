# Team & RACI

> Buzz agent roles and responsibilities. Fizz is **independent** and does not report to the implementation team.

## Roles

### Orchestrator

- Owns scope, milestone plan, backlog and delivery gates.
- Chairs milestone reviews; ensures Fizz gets what it needs.
- Guardian of the honest labelling rule.

### Honey — Design

- Owns architecture v2, durable workflow state, tool contracts, RBAC, threat model, SLOs.
- ADRs on framework and vendor choices.

### Bumble — Build & Run

- Owns implementation, deployment, CI/CD, telemetry, alerts, recovery, runbooks.
- On-call rotation lead.

### Scout — Evaluate

- Owns baseline, golden cases, evaluation methodology, UAT, operator study, evidence pack.
- Pre-registration of experiments.

### Fizz — Independent Assurance

- Reviews every major milestone; returns APPROVE / APPROVE WITH CONDITIONS / BLOCK.
- Runs adversarial tests and failure-injection design.
- Reviews any change to prompts, tools, RBAC, threat model, rollout, evaluation methodology, or SLOs.
- Has authority to block a release.

## RACI (summary)

| Activity | Orchestrator | Honey | Bumble | Scout | Fizz | Osman |
|----------|:---:|:---:|:---:|:---:|:---:|:---:|
| Scope & milestones | A/R | C | C | C | I | I |
| Architecture v2 | I | A/R | C | I | C | I |
| Tool contracts | I | A/R | C | I | C | I |
| Implementation & deployment | I | C | A/R | I | I | I |
| CI/CD & observability | I | C | A/R | I | C | I |
| Threat model | I | A/R | C | I | C | I |
| Golden cases & evaluation | I | I | I | A/R | C | I |
| UAT & operator study | I | I | I | A/R | C | I |
| Failure injection | I | C | R | I | A | I |
| Milestone verdict | R | I | I | I | A | I |
| Autonomy-level change | R | C | I | I | A | A |
| Release comms & labelling | A/R | I | I | C | C | A |

A = Accountable, R = Responsible, C = Consulted, I = Informed.
