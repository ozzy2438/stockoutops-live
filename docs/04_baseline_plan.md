# 04 — Business Baseline Measurement Plan

> Owner: Scout. Reviewer: Fizz. Status: **plan, not yet executed**.

## Purpose

Before we claim that AI-assisted investigation is better, faster, cheaper or more consistent than the current manual process, we need an honest, pre-registered baseline of the current process.

## Baseline definitions

We measure the **current manual investigation process** on a defined case cohort *without* any agent assistance.

### Case cohort

- Source: last 90 days of real or controlled-synthetic stockout events (see `evaluation/replay/` for sampling method).
- Stratification: by severity, SKU velocity band, and root-cause category (where known).
- Sample size target: sufficient to detect a ≥ 30% median-time reduction with 80% power at α = 0.05 (exact N computed in M1 planning).

### Primary metric

- **Time-to-decision (TTD)**: minutes from investigation-open to first defensible recommendation, measured by the analyst UI.

### Secondary metrics

- Correct root-cause rate (against a labelled adjudication set).
- Evidence completeness score (0–1) against a rubric.
- Number of tool / data-source consultations.
- Analyst-reported confidence (1–5) at decision time.
- Cost (analyst minutes × loaded rate; no LLM cost in baseline).

### Guardrails

- No investigation is *only* run as baseline if it delays a real business decision.
- Baseline runs happen in the same UI as assisted runs so environmental factors are held constant.
- Any incident that occurs during baseline collection is treated identically to any other incident.

## Adjudication

- Two independent adjudicators label root cause and evidence completeness.
- Disagreements are resolved by a third adjudicator; Cohen’s κ is reported.
- Labels are frozen before any assisted-mode comparison is run.

## Deliverables

1. Baseline plan (this doc, finalised).
2. Adjudication rubric (`evaluation/golden_cases/rubric.md` — stub in M0).
3. Baseline dataset & measurement notebook.
4. Baseline results report with confidence intervals.
5. Pre-registration note capturing the primary metric, sample size, and stopping rules **before** comparison to assisted mode begins.

## Honest labelling

Baseline numbers are **MEASURED**. Any extrapolation to “expected savings” is **TARGET**. We never present TARGET as MEASURED.
