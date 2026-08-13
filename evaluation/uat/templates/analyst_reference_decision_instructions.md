# Analyst / reference-decision instructions

> **OWNER / SCOUT ACTION REQUIRED — NO USERS RECRUITED YET**

Record the reference decision **before** looking at system shadow output.

Required fields:

- expected state: `awaiting_human` or `escalated`
- escalation expected true/false and code when escalated
- root-cause statement, recommendation action type, and confidence when not escalated
- required evidence tools and minimum unique citations
- notes / limitations, including any ambiguity

Do not:

- paste the model draft into the reference
- invent an analyst decision for synthetic cases
- label a controlled-synthetic fixture as `analyst_reference`

The existing 12-case pack remains `controlled_synthetic_reference` / `SIMULATED`.
