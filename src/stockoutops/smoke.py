"""Deterministic local stub smoke; never contacts a model provider."""

from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

import httpx


def _token(name: str) -> str:
    return (Path(".local") / f"{name}.token").read_text(encoding="utf-8").strip()


def main() -> None:
    base_url = os.getenv("STOCKOUTOPS_URL", "http://localhost:8000")
    intake_key = f"stub-smoke-{uuid4()}"
    request = {
        "sku_id": "SKU-001",
        "store_id": "STORE-001",
        "supplier_id": "SUPPLIER-001",
        "as_of_ts": "2026-08-10T12:00:00Z",
        "window_start": "2026-08-03T12:00:00Z",
        "window_end": "2026-08-10T12:00:00Z",
    }
    with httpx.Client(base_url=base_url, timeout=10) as client:
        operator_headers = {
            "Authorization": f"Bearer {_token('t_alpha_operator')}",
            "Idempotency-Key": intake_key,
        }
        first = client.post("/v1/investigations", headers=operator_headers, json=request)
        first.raise_for_status()
        created = first.json()
        replay = client.post("/v1/investigations", headers=operator_headers, json=request)
        replay.raise_for_status()
        replayed = replay.json()
        reviewer_headers = {
            "Authorization": f"Bearer {_token('t_alpha_reviewer_primary')}",
            "Idempotency-Key": f"review-{uuid4()}",
        }
        reviewed = client.post(
            f"/v1/investigations/{created['run_id']}/review",
            headers=reviewer_headers,
            json={"action": "approve", "draft_hash": created["draft_hash"]},
        )
        reviewed.raise_for_status()
        audit = client.get(
            f"/v1/investigations/{created['run_id']}/audit",
            headers={"Authorization": reviewer_headers["Authorization"]},
        )
        audit.raise_for_status()
    summary = {
        "run_id_stable": created["run_id"] == replayed["run_id"],
        "idempotent_replay": replayed["idempotent_replay"],
        "evidence_count": len(created["evidence"]),
        "final_state": reviewed.json()["state"],
        "audit_replay_matches": (audit.json()["current_state"] == audit.json()["replayed_state"]),
        "reasoning_provider": "deterministic-stub-v1",
        "external_writes": 0,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
