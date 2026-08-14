# Case submission instructions

> **OWNER / SCOUT ACTION REQUIRED — NO USERS RECRUITED YET**

1. Complete consent and de-identification checklists offline.
2. Assign `case_id` / `case_version` that will not collide with the synthetic pack.
3. Fill the shadow case contract (`m2-shadow-case-contract-v2`) with:
   - `provenance_label`: `GENUINE_UAT_ANALYST_LABELLED`
   - `baseline_source`: `analyst_reference`
   - opaque `consent_data_use_reference`
   - `execute`: `false`
   - `required_tools` for the evidence that must be present
4. Wrap one or more cases in an intake document:

   ```json
   {
     "intake_document_version": "m2-uat-intake-v1",
     "execute": false,
     "cases": []
   }
   ```

5. Import with `python -m stockoutops.shadow.intake --input <file> --execute false`.
6. Do not run the shadow processor unless a later authorised task says so.
   Intake must not create tickets, emails, orders, or review decisions.
7. Keep the signed consent artefact outside git.
