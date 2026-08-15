# Changelog

All notable changes to this project will be documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Initial repository bootstrap (Milestone 0 scaffold): governance docs, architecture v2 outline, tool contracts, threat model, rollout plan, evaluation plan, observability & SLO plan, failure-injection scenarios, backlog & milestones, ADR framework, CI/security/eval workflow skeletons, issue & PR templates, CODEOWNERS.
- M2 execute-false shadow foundation: versioned controlled-synthetic case pack, processor, PostgreSQL persistence, and deterministic diff reports (PR #18).
- M2 UAT/real-shadow readiness bridge: contract-derived missing-evidence metric, future genuine-case contract, local JSON intake, UAT/consent templates, and first-100 collection tooling that excludes synthetic cases from M2-05.
- M2 local HTTPS webhook `AlertSink` candidate: disabled-by-default generic webhook delivery with claim-before-send persistence and loopback proof (Issue #24). M2-04 remains pending.

### Changed

- Completed the high-level Phase-1 audit and gap matrix.
- Reframed Architecture v2 as an unaccepted AWS-target proposal using the preferred simple stack.
- Removed Snowflake as a StockoutOps Live target dependency.
- Clarified that the seven proposed v2 tools are derived from Phase-1 lessons, not the exact Phase-1 catalogue.
- Reconciled README, charter, scope, threat model, environment template, risks, and context handoff for the M0 review package.
- Removed fail-open placeholder Python test steps from M0 CI, made the evaluation scaffold manual/non-evidentiary, and added an explicit markdownlint configuration for the existing documentation style.

---

_No releases yet. First tagged release will follow completion of Milestone 0 review and Fizz verdict._
