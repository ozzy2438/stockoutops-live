# Withdrawal and removal procedure

> **OWNER / SCOUT ACTION REQUIRED — NO USERS RECRUITED YET**

1. Receive the withdrawal through the owner-controlled channel.
2. Stop using that participant for new cases immediately.
3. Do not delete mutation-controlled intake rows. From the owner-controlled
   environment, append the allow-listed exclusion event through:

   ```bash
   make shadow-exclude INTAKE_ID=<uuid> TENANT_ID=<tenant> \
     REASON=participant_withdrawal
   ```

   The command is tenant-scoped, requires the local application database role,
   records the fixed owner operator identity, and is idempotent for the same
   non-identifying reason code. Do not put participant identity in arguments.
4. Remove the case from M2-05 eligibility.
5. Retain the offline consent artefact according to the threat-model retention
   policy, or destroy it if the consent terms require destruction.
6. Never publish the participant's name in git, issues, or reports.
