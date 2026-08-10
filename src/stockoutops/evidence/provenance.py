"""Deterministic hashing helpers for evidence and request provenance."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        normalised = value.astimezone(UTC)
        return normalised.isoformat().replace("+00:00", "Z")
    raise TypeError(f"Unsupported canonical JSON type: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        default=_json_default,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_hash(value: Any) -> str:
    return sha256_text(canonical_json(value))


def expected_evidence_id(source_ref: str, content_hash: str) -> str:
    return f"ev_{sha256_text(f'{source_ref}:{content_hash}')}"


def provenance_fields(
    *,
    source_ref: str,
    query: dict[str, object],
    facts: dict[str, object],
    retrieved_at: datetime,
    freshness_ts: datetime,
    fixture_manifest_version: str,
) -> dict[str, object]:
    content_hash = canonical_hash(facts)
    return {
        "evidence_id": expected_evidence_id(source_ref, content_hash),
        "source_type": "postgres_fixture",
        "source_ref": source_ref,
        "query_hash": canonical_hash(query),
        "content_hash": content_hash,
        "retrieved_at": retrieved_at,
        "freshness_ts": freshness_ts,
        "fixture_manifest_version": fixture_manifest_version,
    }
