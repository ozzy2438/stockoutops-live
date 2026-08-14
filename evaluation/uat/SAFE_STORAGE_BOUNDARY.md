# Safe storage boundary for genuine UAT records

> **OWNER / SCOUT ACTION REQUIRED — NO USERS RECRUITED YET**

## May live in this public repository

- Blank templates
- De-identified shadow-case JSON after owner attestation
- Opaque consent references matching `OFFLINE-CONSENT-[A-Z0-9-]{8,64}`
- Aggregate counts with no person-level data

## Must remain outside this repository

- Signed consent forms
- Participant names, emails, phone numbers, or workplace identifiers
- Recruitment lists and correspondence
- Unredacted source tickets, screenshots, or operator notes
- Any record that can re-identify a person or tenant customer

## Required owner-controlled store

Keep signed consent, recruitment, and withdrawal records in an owner-controlled
offline store that is not git, not CI artefacts, not `evaluation/reports/`, and
not PostgreSQL `shadow_case_intake.case_json`.

The public case record may contain only the opaque consent reference. The
private store maps that reference to the signed artefact.

## Retention

Follow `docs/07_threat_model.md`. Do not copy private artefacts into agent
transcripts, pull-request bodies, or chat logs.
