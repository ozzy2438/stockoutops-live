# Security Policy

## Reporting a vulnerability

Please **do not** open a public GitHub issue for suspected security problems. Email the maintainer (Osman Orka) with subject `SECURITY: <short title>` and include:

- Affected component / commit / environment.
- Reproduction steps or proof-of-concept.
- Impact assessment (confidentiality / integrity / availability / privacy).
- Any suggested mitigation.

Expect an acknowledgement within 3 business days and a triage decision within 10 business days.

## Scope

In scope:

- StockoutOps Live application code and prompts.
- Tool contracts and their enforcement layer.
- RBAC / RLS / tenancy isolation.
- Deployment infrastructure defined in `infra/`.
- Data marts consumed by the platform.

Out of scope (report to the appropriate vendor):

- Snowflake platform vulnerabilities.
- LLM provider platform vulnerabilities.
- Third-party libraries (please still notify us).

## Threat model

See `docs/07_threat_model.md`. Any change to the trust boundaries, tool permissions, or data-flow requires a threat-model diff in the PR.

## Handling of secrets

- No secret is ever committed. `.env` is git-ignored; `.env.example` is the only accepted template.
- CI uses OIDC or short-lived tokens where possible; static secrets live in the platform's secret manager.
- Secret scanning is enabled (see `.github/workflows/security.yml`).

## Data handling

- All data access must go through governed marts with RLS.
- Zero RLS leakage is a **release-blocking** invariant; any regression is a P0 incident.
- PII / customer-identifying fields are not surfaced to the agent unless explicitly whitelisted by a data contract.
