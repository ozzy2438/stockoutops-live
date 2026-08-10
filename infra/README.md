# Infrastructure

Infrastructure-as-code, deployment manifests, feature-flag definitions.

## Layout

```
infra/
├── environments/    # staging, prod, canary
├── modules/         # reusable IaC modules
├── flags/           # feature-flag definitions (versioned)
└── secrets/         # secret schemas (never actual secrets)
```

## Rules

- No secret is committed. `.env.example` is the only accepted template at repo root.
- Every environment change goes through PR + review.
- Every flag flip is logged (actor, scope, effective time).
