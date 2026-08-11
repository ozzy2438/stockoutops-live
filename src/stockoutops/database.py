"""psycopg connection helper and ordered plain-SQL migration runner."""

from __future__ import annotations

import argparse
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.sql import SQL, Literal


class Database:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    @contextmanager
    def connect(self) -> Iterator[Connection[dict[str, object]]]:
        with psycopg.connect(self.dsn, row_factory=dict_row) as connection:
            yield connection

    def health(self) -> bool:
        with self.connect() as connection:
            return connection.execute("SELECT 1").fetchone() is not None


def run_migrations(
    dsn: str,
    *,
    migrations_dir: Path,
    app_role_password: str | None = None,
) -> list[str]:
    applied: list[str] = []
    with psycopg.connect(dsn) as connection:
        with connection.transaction():
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migration (
                    version text PRIMARY KEY,
                    applied_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        for migration in sorted(migrations_dir.glob("*.sql")):
            with connection.transaction():
                exists = connection.execute(
                    "SELECT 1 FROM schema_migration WHERE version = %s",
                    (migration.name,),
                ).fetchone()
                if exists:
                    continue
                connection.execute(migration.read_text(encoding="utf-8"))
                connection.execute(
                    "INSERT INTO schema_migration (version) VALUES (%s)",
                    (migration.name,),
                )
                applied.append(migration.name)
        if app_role_password:
            with connection.transaction():
                connection.execute(
                    SQL("ALTER ROLE stockoutops_app PASSWORD {}").format(Literal(app_role_password))
                )
    return applied


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply ordered StockoutOps SQL migrations")
    parser.add_argument("--migrations", default="migrations")
    args = parser.parse_args()
    dsn = os.environ["MIGRATION_DATABASE_URL"]
    applied = run_migrations(
        dsn,
        migrations_dir=Path(args.migrations),
        app_role_password=os.getenv("APP_DB_PASSWORD"),
    )
    print(f"Applied {len(applied)} migration(s)")


if __name__ == "__main__":
    main()
