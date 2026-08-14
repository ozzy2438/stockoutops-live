# Evidence labelling rules

> **OWNER / SCOUT ACTION REQUIRED — NO USERS RECRUITED YET**

| Label | Meaning | May count toward M2-05? |
|---|---|---|
| `SIMULATED` / `controlled_synthetic_reference` | Controlled fixture, including the 12-case pack | No |
| `GENUINE_UAT_ANALYST_LABELLED` / `analyst_reference` | Owner-approved de-identified UAT/analyst case | Only after `accepted_for_m2_05` |
| `SCHEMA/INTAKE FIXTURE` in tests | Contract test object, not a real case | No, unless a test explicitly accepts it inside PostgreSQL |

Reports must keep these classes separate. Do not relabel synthetic agreement as
analyst agreement, model quality, or G1 exit evidence.
