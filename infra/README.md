# Infrastructure

> Milestone 0: documentation only. No AWS account resources, infrastructure-as-code, deployment manifests, Docker images, or feature flags have been created.

The reviewed target is AWS using Docker on ECS Fargate, Amazon RDS for PostgreSQL, S3 where object storage is required, CloudWatch, Secrets Manager, and GitHub Actions. Exact region, networking/ingress, identity, environment topology, and IaC tool remain open.

## Proposed post-M0 layout

```text
infra/
├── environments/    # reviewed AWS environment definitions
├── modules/         # reusable AWS/RDS/ECS/S3/CloudWatch definitions
├── flags/           # feature-flag definitions (versioned)
└── secrets/         # schemas/references only; never secret values
```

## Rules

- No secret is committed. `.env.example` is the only accepted template at repo root.
- Every environment change goes through issue → branch → PR → independent review → merge.
- Every flag flip is logged (actor, scope, effective time).
- No Snowflake or unreviewed major platform is introduced.
- This layout may change through the accepted architecture/IaC ADR; it is not an implementation instruction.
