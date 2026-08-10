# Glossary

- **A2 — approve-to-act.** Agent may prepare actions; a human must approve before any external write.
- **Assisted operation (G2).** Rollout gate where the agent prepares an investigation pack; a human approves / edits / rejects / escalates.
- **Canary (G3).** Small workload slice where a specific automated step is enabled behind a feature flag with fast rollback.
- **Citation.** A machine-readable evidence reference produced by a tool call: source mart, filter, row count, freshness timestamp.
- **Controlled UAT experiment.** A randomised operator study conducted with limited traffic and sample size; not a commercial production A/B test.
- **Definition of Done (DoD).** The full set of conditions in `README.md` §6 required to close the project.
- **Feature flag.** A toggle controlling behaviour at runtime; used to gate rollout and enable rollback.
- **Fizz verdict.** Independent assurance result at a milestone gate. Only `APPROVE` opens the gate; `APPROVE WITH CONDITIONS` pauses merge until resolution and re-review; `BLOCK` stops the milestone.
- **Golden case.** A curated case with expected root cause, evidence, tool set, and escalation flag used for regression.
- **Historical replay (G0).** Blind rerun of past resolved cases in staging.
- **RLS.** Row-level security proposed at the PostgreSQL data boundary and backed by application-level tenant checks.
- **Run ID.** Durable identifier for a single investigation across intake, tool calls, LLM calls, approval and audit.
- **Shadow mode (G1).** Agent analyses live cases without executing any external action; diffed against analyst decisions.
- **SLO.** Service-level objective; a target on an SLI over a window.
- **Tool contract.** JSON-schema definition of a tool’s arguments and results; enforced at runtime.
- **Unsupported claim.** Any assertion in an agent output not traceable to an evidence citation.
