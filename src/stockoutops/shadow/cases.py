"""Manifest verification and controlled-synthetic fixture loading for shadow cases."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import psycopg

from stockoutops.shadow.contracts import ShadowCasePack


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65_536), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class LoadedCasePack:
    pack: ShadowCasePack
    cases_sha256: str
    manifest_sha256: str


def load_case_pack(cases_dir: Path) -> LoadedCasePack:
    manifest_path = cases_dir / "manifest.json"
    cases_path = cases_dir / "cases.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if set(manifest) != {"case_pack_version", "files"}:
        raise ValueError("Shadow case manifest has unexpected fields")
    if manifest["files"] != {"cases.json": _sha256(cases_path)}:
        raise ValueError("Shadow case manifest hash does not match cases.json")
    pack = ShadowCasePack.model_validate_json(cases_path.read_text(encoding="utf-8"))
    if pack.case_pack_version != manifest["case_pack_version"]:
        raise ValueError("Shadow case pack version does not match its manifest")
    return LoadedCasePack(
        pack=pack,
        cases_sha256=_sha256(cases_path),
        manifest_sha256=_sha256(manifest_path),
    )


def seed_case_fixtures(dsn: str, case_pack: ShadowCasePack) -> None:
    inventory: list[dict[str, object]] = []
    demand: list[dict[str, object]] = []
    supplier: list[dict[str, object]] = []
    for case in case_pack.cases:
        request = case.input
        if case.fixture_setup.inventory is not None:
            inventory.append(
                {
                    "tenant_id": case.tenant_id,
                    "sku_id": request.sku_id,
                    "store_id": request.store_id,
                    **case.fixture_setup.inventory.model_dump(),
                }
            )
        if case.fixture_setup.demand is not None:
            demand.append(
                {
                    "tenant_id": case.tenant_id,
                    "sku_id": request.sku_id,
                    "store_id": request.store_id,
                    "window_start": request.window_start,
                    "window_end": request.window_end,
                    **case.fixture_setup.demand.model_dump(),
                }
            )
        if case.fixture_setup.supplier is not None:
            supplier.append(
                {
                    "tenant_id": case.tenant_id,
                    "sku_id": request.sku_id,
                    "supplier_id": request.supplier_id,
                    **case.fixture_setup.supplier.model_dump(),
                }
            )

    with (
        psycopg.connect(dsn) as connection,
        connection.transaction(),
        connection.cursor() as cursor,
    ):
        cursor.executemany(
            """
            INSERT INTO inventory_fixture (
                tenant_id, sku_id, store_id, on_hand, reserved, on_order, updated_at
            ) VALUES (
                %(tenant_id)s, %(sku_id)s, %(store_id)s, %(on_hand)s,
                %(reserved)s, %(on_order)s, %(updated_at)s
            )
            ON CONFLICT (tenant_id, sku_id, store_id) DO UPDATE SET
                on_hand = EXCLUDED.on_hand, reserved = EXCLUDED.reserved,
                on_order = EXCLUDED.on_order, updated_at = EXCLUDED.updated_at
            """,
            inventory,
        )
        cursor.executemany(
            """
            INSERT INTO demand_fixture (
                tenant_id, sku_id, store_id, window_start, window_end,
                units_sold, average_daily_units, demand_signal, updated_at
            ) VALUES (
                %(tenant_id)s, %(sku_id)s, %(store_id)s, %(window_start)s,
                %(window_end)s, %(units_sold)s, %(average_daily_units)s,
                %(demand_signal)s, %(updated_at)s
            )
            ON CONFLICT (tenant_id, sku_id, store_id, window_start, window_end)
            DO UPDATE SET
                units_sold = EXCLUDED.units_sold,
                average_daily_units = EXCLUDED.average_daily_units,
                demand_signal = EXCLUDED.demand_signal,
                updated_at = EXCLUDED.updated_at
            """,
            demand,
        )
        cursor.executemany(
            """
            INSERT INTO supplier_fixture (
                tenant_id, sku_id, supplier_id, open_order_quantity,
                expected_receipt_at, historical_lead_time_days, status, updated_at
            ) VALUES (
                %(tenant_id)s, %(sku_id)s, %(supplier_id)s,
                %(open_order_quantity)s, %(expected_receipt_at)s,
                %(historical_lead_time_days)s, %(status)s, %(updated_at)s
            )
            ON CONFLICT (tenant_id, sku_id, supplier_id) DO UPDATE SET
                open_order_quantity = EXCLUDED.open_order_quantity,
                expected_receipt_at = EXCLUDED.expected_receipt_at,
                historical_lead_time_days = EXCLUDED.historical_lead_time_days,
                status = EXCLUDED.status, updated_at = EXCLUDED.updated_at
            """,
            supplier,
        )
