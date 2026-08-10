# 0005. Use server-derived simulated identity for local M1

- **Status:** Accepted for local M1 only (effective after this scope-lock PR merges)
- **Date:** 2026-08-10
- **Deciders:** Ozzy (owner), Honey (architecture), Orchestrator (scope)
- **Assurance:** Fizz review of the exact documentation PR head is required

## Context

M1 must deterministically prove identity, role, and tenant checks without claiming production authentication. Full IdP, session, MFA, provisioning, and PostgreSQL RLS would expand the local vertical slice.

## Decision

- Define `IdentityProvider.resolve(request) -> Principal(actor_id, tenant_id, roles)`.
- The M1 `SimulatedIdentityProvider` maps opaque local bearer tokens from an ignored/test-only identity fixture to principals.
- The server derives actor, tenant, and roles. Any request body or query containing `actor_id`, `tenant_id`, or `role` is rejected before processing.
- Fixtures include `t_alpha` and `t_beta`, operator and reviewer roles, and two `t_alpha` reviewers for wrong-reviewer tests.
- Every tenant-scoped repository function accepts `Principal` first and applies `WHERE tenant_id = :principal_tenant`; contract tests enforce this choke point.
- Missing/invalid credentials return `401`. A valid principal requesting another tenant's run returns `404` to avoid confirming existence. Reviewer role, tenant, run state, payload hash, and expiry are checked server-side.
- If `APP_ENV` is not `local`, selecting the simulated provider prevents application startup.
- API requests use the `Authorization: Bearer` header. The lightweight review page may hold a locally entered token in browser memory only and use same-origin authenticated requests; it must not put identity/token data in URL, query, request body, local storage, screenshots, logs, or repository files.

## Rationale

This proves the server-derived identity invariant and cross-tenant fail-closed behaviour using deterministic fixtures while keeping a replaceable provider boundary for later OIDC/SSO work.

## Consequences and limitations

- M1 measures fixture-backed application checks only. It does not prove production tenant safety.
- No SSO/OIDC, MFA, signed JWT validation, token expiry/refresh, session, provisioning, delegation, separation of duties, CSRF programme, or RLS exists.
- The in-memory browser-token mechanism is local smoke infrastructure, not a production login design. Accessibility and browser security hardening remain open.

## Security and privacy

- Fixture tokens are non-production test material and must be clearly labelled; real credentials are forbidden.
- Cross-tenant reads, findings, decisions, and audits must return no data. Test threshold is zero leakage across the two fixtures.
- No real personal or tenant data is introduced in M1.

## Recovery and rollback

Disable the local application or rotate the test fixture tokens. No production identity system is affected. Replacing the provider must preserve the `Principal` contract and requires threat-model review before authenticated UAT.

## Alternatives considered

- Full IdP/RLS now: deferred because it does not help prove the local workflow slice and would create false production-readiness implications.
- Client-supplied tenant or role: rejected because it violates the core trust boundary.
- Cookie session for the review page: deferred; it introduces session and CSRF scope.

## Next gate

Fizz verifies the fail-closed contract in the docs PR. Bumble later implements only the local provider. Real authentication and RLS require a separate decision and evidence before UAT.
