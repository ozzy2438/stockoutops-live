"""Deterministic genuine-UAT shadow case intake. Never executes or calls a model."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import ValidationError as PydanticValidationError

from stockoutops.database import Database
from stockoutops.errors import AuthorizationError, ConflictError, NotFoundError, ValidationError
from stockoutops.evidence.provenance import canonical_hash
from stockoutops.identity import Principal
from stockoutops.shadow.contracts import ShadowCase, ShadowIntakeDocument
from stockoutops.shadow.repository import _lock_key

INTAKE_DOCUMENT_VERSION = "m2-uat-intake-v1"
CASE_CONTRACT_VERSION = "m2-shadow-case-contract-v2"
EXCLUSION_REASON_CODES = frozenset(
    {
        "participant_withdrawal",
        "owner_data_quality_exclusion",
    }
)


@dataclass(frozen=True)
class ShadowIntakeRecord:
    intake_id: UUID
    tenant_id: str
    case_id: str
    case_version: str
    case_contract_version: str
    payload_hash: str
    provenance_label: str
    baseline_source: str
    deidentification_status: str
    consent_data_use_status: str
    consent_data_use_reference: str
    category: str
    execute: bool
    external_action_count: int
    case_json: dict[str, object]
    created_by: str
    created_at: datetime


def _record(row: dict[str, Any]) -> ShadowIntakeRecord:
    return ShadowIntakeRecord(
        intake_id=row["intake_id"],
        tenant_id=row["tenant_id"],
        case_id=row["case_id"],
        case_version=row["case_version"],
        case_contract_version=row["case_contract_version"],
        payload_hash=row["payload_hash"],
        provenance_label=row["provenance_label"],
        baseline_source=row["baseline_source"],
        deidentification_status=row["deidentification_status"],
        consent_data_use_status=row["consent_data_use_status"],
        consent_data_use_reference=row["consent_data_use_reference"],
        category=row["category"],
        execute=row["execute"],
        external_action_count=row["external_action_count"],
        case_json=row["case_json"],
        created_by=row["created_by"],
        created_at=row["created_at"],
    )


def load_intake_document(path: Path) -> ShadowIntakeDocument:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError(
            "SHADOW_INTAKE_INVALID_JSON", "Intake file is not valid JSON"
        ) from exc
    if isinstance(raw, list):
        raw = {"intake_document_version": INTAKE_DOCUMENT_VERSION, "execute": False, "cases": raw}
    try:
        return ShadowIntakeDocument.model_validate(raw)
    except PydanticValidationError as exc:
        raise ValidationError("SHADOW_INTAKE_SCHEMA_INVALID", str(exc)) from exc


def case_payload_hash(case: ShadowCase) -> str:
    return canonical_hash(case.model_dump(mode="json"))


def validate_exclusion_reason(reason: str) -> str:
    if reason not in EXCLUSION_REASON_CODES:
        raise ValidationError(
            "SHADOW_INTAKE_EXCLUSION_REASON_INVALID",
            "Exclusion reason must be an allow-listed non-identifying reason code",
        )
    return reason


class ShadowIntakeRepository:
    """Every tenant-scoped public method receives Principal first."""

    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _insert_event(
        connection: Any,
        *,
        record: ShadowIntakeRecord,
        actor_id: str,
        event_type: str,
        payload: dict[str, object],
        occurred_at: datetime,
    ) -> None:
        connection.execute(
            """
            INSERT INTO shadow_case_intake_event (
                intake_id, tenant_id, event_type, actor_id, payload, occurred_at
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                record.intake_id,
                record.tenant_id,
                event_type,
                actor_id,
                Jsonb(payload),
                occurred_at,
            ),
        )

    def import_or_observe(
        self,
        principal: Principal,
        case: ShadowCase,
        *,
        payload_hash: str,
        now: datetime,
    ) -> tuple[ShadowIntakeRecord, bool]:
        keys = sorted(
            {_lock_key(f"shadow-intake:{principal.tenant_id}:{case.case_id}:{case.case_version}")}
        )
        connection = psycopg.connect(self.database.dsn, row_factory=dict_row, autocommit=True)
        try:
            for key in keys:
                connection.execute("SELECT pg_advisory_lock(%s)", (key,))
            row = connection.execute(
                """
                SELECT * FROM shadow_case_intake
                WHERE tenant_id = %s AND case_id = %s AND case_version = %s
                """,
                (principal.tenant_id, case.case_id, case.case_version),
            ).fetchone()
            if row:
                record = _record(row)
                if record.payload_hash != payload_hash:
                    self._insert_event(
                        connection,
                        record=record,
                        actor_id=principal.actor_id,
                        event_type="shadow_intake_rejected",
                        payload={"code": "SHADOW_INTAKE_CONFLICT"},
                        occurred_at=now,
                    )
                    raise ConflictError(
                        "SHADOW_INTAKE_CONFLICT",
                        "Case identity was already imported with a different payload",
                    )
                self._insert_event(
                    connection,
                    record=record,
                    actor_id=principal.actor_id,
                    event_type="shadow_intake_replayed",
                    payload={"payload_hash": payload_hash, "execute": False},
                    occurred_at=now,
                )
                return record, False

            inserted = connection.execute(
                """
                INSERT INTO shadow_case_intake (
                    intake_id, tenant_id, case_id, case_version, case_contract_version,
                    payload_hash, provenance_label, baseline_source, deidentification_status,
                    consent_data_use_status, consent_data_use_reference, category,
                    execute, external_action_count, case_json, created_by, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, false, 0, %s, %s, %s
                ) RETURNING *
                """,
                (
                    uuid4(),
                    principal.tenant_id,
                    case.case_id,
                    case.case_version,
                    case.case_contract_version,
                    payload_hash,
                    case.provenance_label,
                    case.baseline_source,
                    case.deidentification_status,
                    case.consent_data_use_status,
                    case.consent_data_use_reference,
                    case.category,
                    Jsonb(case.model_dump(mode="json")),
                    principal.actor_id,
                    now,
                ),
            ).fetchone()
            record = _record(inserted)
            self._insert_event(
                connection,
                record=record,
                actor_id=principal.actor_id,
                event_type="shadow_intake_imported",
                payload={
                    "execute": False,
                    "external_action_count": 0,
                    "payload_hash": payload_hash,
                    "accepted_for_m2_05": False,
                },
                occurred_at=now,
            )
            return record, True
        finally:
            if not connection.closed:
                for key in reversed(keys):
                    connection.execute("SELECT pg_advisory_unlock(%s)", (key,))
                connection.close()

    def get(self, principal: Principal, intake_id: UUID | str) -> ShadowIntakeRecord:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM shadow_case_intake WHERE intake_id = %s AND tenant_id = %s",
                (intake_id, principal.tenant_id),
            ).fetchone()
        if row is None:
            raise NotFoundError()
        return _record(row)

    def list_for_tenant(self, principal: Principal) -> list[ShadowIntakeRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM shadow_case_intake
                WHERE tenant_id = %s
                ORDER BY case_id, case_version
                """,
                (principal.tenant_id,),
            ).fetchall()
        return [_record(row) for row in rows]

    def list_all(self) -> list[ShadowIntakeRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM shadow_case_intake ORDER BY tenant_id, case_id, case_version"
            ).fetchall()
        return [_record(row) for row in rows]

    def events(self, principal: Principal, intake_id: UUID | str) -> list[dict[str, object]]:
        self.get(principal, intake_id)
        with self.database.connect() as connection:
            return connection.execute(
                """
                SELECT intake_event_id, intake_id, tenant_id, event_type,
                       actor_id, payload, occurred_at
                FROM shadow_case_intake_event
                WHERE intake_id = %s AND tenant_id = %s
                ORDER BY intake_event_id
                """,
                (intake_id, principal.tenant_id),
            ).fetchall()

    def accept_for_m2_05(
        self,
        principal: Principal,
        intake_id: UUID | str,
        *,
        now: datetime,
    ) -> ShadowIntakeRecord:
        record = self.get(principal, intake_id)
        if not principal.has_role("operator"):
            raise AuthorizationError("M2-05 acceptance requires the simulated operator role")
        with self.database.connect() as connection, connection.transaction():
            connection.execute(
                "SELECT pg_advisory_xact_lock(%s)",
                (_lock_key(f"shadow-intake-control:{principal.tenant_id}:{record.intake_id}"),),
            )
            existing = connection.execute(
                """
                SELECT 1 FROM shadow_case_intake_event
                WHERE intake_id = %s AND tenant_id = %s AND event_type = 'accepted_for_m2_05'
                """,
                (record.intake_id, principal.tenant_id),
            ).fetchone()
            if existing is None:
                self._insert_event(
                    connection,
                    record=record,
                    actor_id=principal.actor_id,
                    event_type="accepted_for_m2_05",
                    payload={"official_m2_05": True, "execute": False},
                    occurred_at=now,
                )
        return record

    def exclude(
        self,
        principal: Principal,
        intake_id: UUID | str,
        *,
        reason: str,
        now: datetime,
    ) -> tuple[ShadowIntakeRecord, bool]:
        record = self.get(principal, intake_id)
        if not principal.has_role("operator"):
            raise AuthorizationError("Shadow intake exclusion requires the simulated operator role")
        reason = validate_exclusion_reason(reason)
        with self.database.connect() as connection, connection.transaction():
            connection.execute(
                "SELECT pg_advisory_xact_lock(%s)",
                (_lock_key(f"shadow-intake-control:{principal.tenant_id}:{record.intake_id}"),),
            )
            existing = connection.execute(
                """
                SELECT payload FROM shadow_case_intake_event
                WHERE intake_id = %s AND tenant_id = %s AND event_type = 'excluded'
                ORDER BY intake_event_id DESC
                LIMIT 1
                """,
                (record.intake_id, principal.tenant_id),
            ).fetchone()
            if existing is not None:
                if (existing["payload"] or {}).get("reason") != reason:
                    raise ConflictError(
                        "SHADOW_INTAKE_EXCLUSION_CONFLICT",
                        "Intake was already excluded with a different reason code",
                    )
                return record, False
            self._insert_event(
                connection,
                record=record,
                actor_id=principal.actor_id,
                event_type="excluded",
                payload={"reason": reason, "execute": False},
                occurred_at=now,
            )
        return record, True

    def accepted_intake_ids(self) -> set[UUID]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT intake_id
                FROM shadow_case_intake_event
                WHERE event_type = 'accepted_for_m2_05'
                """
            ).fetchall()
        return {row["intake_id"] for row in rows}

    def excluded_intake_ids(self) -> dict[UUID, str]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT ON (intake_id) intake_id, payload
                FROM shadow_case_intake_event
                WHERE event_type = 'excluded'
                ORDER BY intake_id, intake_event_id DESC
                """
            ).fetchall()
        reasons: dict[UUID, str] = {}
        for row in rows:
            payload = row["payload"] or {}
            reasons[row["intake_id"]] = str(payload.get("reason", "unspecified"))
        return reasons


class ShadowIntakeService:
    def __init__(self, repository: ShadowIntakeRepository, *, clock=None) -> None:
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(UTC))

    def import_case(
        self,
        principal: Principal,
        case: ShadowCase,
        *,
        execute: bool = False,
    ) -> tuple[ShadowIntakeRecord, bool]:
        if execute is not False:
            raise ValidationError(
                "SHADOW_EXECUTION_FORBIDDEN",
                "M2 shadow intake is permanently hard-locked to execute=false",
            )
        if case.execute is not False:
            raise ValidationError(
                "SHADOW_EXECUTION_FORBIDDEN",
                "M2 shadow intake is permanently hard-locked to execute=false",
            )
        if principal.tenant_id != case.tenant_id:
            raise NotFoundError()
        if not principal.has_role("operator"):
            raise AuthorizationError("Shadow intake requires the simulated operator role")
        if case.provenance_label != "GENUINE_UAT_ANALYST_LABELLED":
            raise ValidationError(
                "SHADOW_INTAKE_PROVENANCE_INVALID",
                "Genuine UAT intake rejects SIMULATED or uncontrolled provenance",
            )
        if case.case_contract_version != CASE_CONTRACT_VERSION:
            raise ValidationError(
                "SHADOW_INTAKE_VERSION_INVALID",
                "Intake case_contract_version is not supported",
            )
        if not case.minimum_evidence_citation_expectations.required_tools:
            raise ValidationError(
                "SHADOW_INTAKE_REQUIRED_TOOLS_INVALID",
                "Intake cases require a non-empty required_tools set",
            )
        record, created = self.repository.import_or_observe(
            principal,
            case,
            payload_hash=case_payload_hash(case),
            now=self.clock(),
        )
        if record.external_action_count != 0 or record.execute is not False:
            raise RuntimeError("Shadow intake violated the execute=false invariant")
        return record, created

    def exclude_case(
        self,
        principal: Principal,
        intake_id: UUID | str,
        *,
        reason: str,
    ) -> tuple[ShadowIntakeRecord, bool]:
        return self.repository.exclude(
            principal,
            intake_id,
            reason=validate_exclusion_reason(reason),
            now=self.clock(),
        )


def import_document(
    service: ShadowIntakeService,
    document: ShadowIntakeDocument,
    *,
    execute: bool = False,
) -> list[tuple[ShadowIntakeRecord, bool]]:
    if execute is not False or document.execute is not False:
        raise ValidationError(
            "SHADOW_EXECUTION_FORBIDDEN",
            "M2 shadow intake is permanently hard-locked to execute=false",
        )
    imported: list[tuple[ShadowIntakeRecord, bool]] = []
    for case in document.cases:
        principal = Principal(
            actor_id=f"shadow-intake-{case.tenant_id}",
            tenant_id=case.tenant_id,
            roles=frozenset({"operator"}),
        )
        imported.append(service.import_case(principal, case, execute=False))
    return imported


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import owner-approved de-identified UAT shadow cases without execution"
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--execute", choices=["false"], default="false")
    args = parser.parse_args()
    document = load_intake_document(Path(args.input))
    service = ShadowIntakeService(ShadowIntakeRepository(Database(os.environ["DATABASE_URL"])))
    results = import_document(service, document, execute=False)
    print(
        json.dumps(
            {
                "imported_count": sum(created for _record, created in results),
                "replayed_count": sum(not created for _record, created in results),
                "execute": False,
                "external_action_count": 0,
                "accepted_for_m2_05": False,
                "cases": [
                    {
                        "intake_id": str(record.intake_id),
                        "case_id": record.case_id,
                        "case_version": record.case_version,
                        "payload_hash": record.payload_hash,
                        "created": created,
                    }
                    for record, created in results
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )


def exclude_main() -> None:
    parser = argparse.ArgumentParser(
        description="Exclude a UAT shadow intake through the owner-operated append-only path"
    )
    parser.add_argument("--intake-id", required=True, type=UUID)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--reason", required=True, choices=sorted(EXCLUSION_REASON_CODES))
    args = parser.parse_args()
    service = ShadowIntakeService(ShadowIntakeRepository(Database(os.environ["DATABASE_URL"])))
    record, created = service.exclude_case(
        Principal(
            actor_id="owner-shadow-intake-operator",
            tenant_id=args.tenant_id,
            roles=frozenset({"operator"}),
        ),
        args.intake_id,
        reason=args.reason,
    )
    print(
        json.dumps(
            {
                "intake_id": str(record.intake_id),
                "tenant_id": record.tenant_id,
                "reason": args.reason,
                "excluded": True,
                "created": created,
                "execute": False,
                "external_action_count": 0,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
