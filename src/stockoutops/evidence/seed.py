"""Verify the committed fixture manifest and seed PostgreSQL deterministically."""

from __future__ import annotations

import csv
import os
from pathlib import Path

import psycopg

from stockoutops.evidence.manifest import verify_manifest


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def seed_fixtures(dsn: str, fixtures_dir: Path) -> str:
    version = verify_manifest(fixtures_dir)
    inventory = _rows(fixtures_dir / "inventory.csv")
    demand = _rows(fixtures_dir / "demand.csv")
    supplier = _rows(fixtures_dir / "supplier.csv")
    with psycopg.connect(dsn) as connection, connection.transaction():
        connection.executemany(
            """
            INSERT INTO inventory_fixture (
                tenant_id, sku_id, store_id, on_hand, reserved, on_order, updated_at
            ) VALUES (
                %(tenant_id)s, %(sku_id)s, %(store_id)s, %(on_hand)s,
                %(reserved)s, %(on_order)s, %(updated_at)s
            )
            ON CONFLICT (tenant_id, sku_id, store_id) DO UPDATE SET
                on_hand = EXCLUDED.on_hand,
                reserved = EXCLUDED.reserved,
                on_order = EXCLUDED.on_order,
                updated_at = EXCLUDED.updated_at
            """,
            inventory,
        )
        connection.executemany(
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
        connection.executemany(
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
                status = EXCLUDED.status,
                updated_at = EXCLUDED.updated_at
            """,
            supplier,
        )
    return version


def main() -> None:
    fixtures_dir = Path(os.getenv("FIXTURES_DIR", "fixtures/v1"))
    version = seed_fixtures(os.environ["MIGRATION_DATABASE_URL"], fixtures_dir)
    print(f"Verified and seeded fixture manifest {version}")


if __name__ == "__main__":
    main()
