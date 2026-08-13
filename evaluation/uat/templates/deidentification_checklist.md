# De-identification checklist

> **OWNER / SCOUT ACTION REQUIRED — NO USERS RECRUITED YET**

A case may be imported only after the owner attests every item.

- [ ] No person name, email, phone number, or account identifier
- [ ] No customer name or loyalty identifier
- [ ] Store/SKU/supplier IDs are study identifiers, not production secrets
- [ ] Free-text notes contain no residual PII or screenshot OCR residue
- [ ] Timestamps are as-of study timestamps, not hidden identifiers
- [ ] Consent reference is opaque and does not encode a name
- [ ] Source artefacts remain outside git
- [ ] `deidentification_status` is `deidentified_owner_attested`

If any item fails, do not import. Do not attempt to "clean" PII inside the
public repository.
