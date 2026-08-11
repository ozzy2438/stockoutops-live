from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from stockoutops.api import create_app
from stockoutops.config import Settings
from stockoutops.database import Database, run_migrations
from stockoutops.evidence.seed import seed_fixtures
from stockoutops.evidence.tools import EvidenceTools
from stockoutops.identity import Principal, SimulatedIdentityProvider
from stockoutops.reasoning.deterministic_stub import DeterministicStubAdapter
from stockoutops.repository import Repository
from stockoutops.service import InvestigationService

ADMIN_DSN = os.getenv(
    "MIGRATION_DATABASE_URL",
    "postgresql://stockoutops_migration:migration-local-only@localhost:5432/stockoutops",
)
APP_DSN = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://stockoutops_app:app-local-only@localhost:5432/stockoutops",
)

TOKENS = {
    "operator_alpha": "local-test-operator-alpha-NOT-A-SECRET",
    "reviewer_alpha": "local-test-reviewer-alpha-NOT-A-SECRET",
    "reviewer_alpha_wrong": "local-test-reviewer-alpha-wrong-NOT-A-SECRET",
    "operator_beta": "local-test-operator-beta-NOT-A-SECRET",
    "reviewer_beta": "local-test-reviewer-beta-NOT-A-SECRET",
}

PRINCIPALS = {
    TOKENS["operator_alpha"]: Principal("operator-alpha", "t_alpha", frozenset({"operator"})),
    TOKENS["reviewer_alpha"]: Principal(
        "reviewer-alpha-primary", "t_alpha", frozenset({"reviewer"})
    ),
    TOKENS["reviewer_alpha_wrong"]: Principal(
        "reviewer-alpha-secondary", "t_alpha", frozenset({"reviewer"})
    ),
    TOKENS["operator_beta"]: Principal("operator-beta", "t_beta", frozenset({"operator"})),
    TOKENS["reviewer_beta"]: Principal("reviewer-beta-primary", "t_beta", frozenset({"reviewer"})),
}

CANONICAL_REQUEST = {
    "sku_id": "SKU-001",
    "store_id": "STORE-001",
    "supplier_id": "SUPPLIER-001",
    "as_of_ts": "2026-08-10T12:00:00Z",
    "window_start": "2026-08-03T12:00:00Z",
    "window_end": "2026-08-10T12:00:00Z",
}


class MutableClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 8, 10, 12, 30, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.value


@pytest.fixture(scope="session", autouse=True)
def postgres_schema() -> None:
    try:
        with psycopg.connect(ADMIN_DSN) as connection:
            connection.execute("SELECT version()")
    except psycopg.Error as exc:
        pytest.fail(f"Real PostgreSQL 16 is required for integration tests: {exc}")
    run_migrations(
        ADMIN_DSN,
        migrations_dir=Path("migrations"),
        app_role_password="app-local-only",
    )


@pytest.fixture
def clean_database(postgres_schema: None) -> None:
    with psycopg.connect(ADMIN_DSN) as connection, connection.transaction():
        connection.execute(
            """
            TRUNCATE TABLE
                review_decision, tool_invocation, idempotency_key,
                workflow_event, investigation_run
            RESTART IDENTITY CASCADE
            """
        )
    seed_fixtures(ADMIN_DSN, Path("fixtures/v1"))


@pytest.fixture
def clock() -> MutableClock:
    return MutableClock()


@pytest.fixture
def identity_provider() -> SimulatedIdentityProvider:
    return SimulatedIdentityProvider(
        PRINCIPALS,
        {
            "t_alpha": "reviewer-alpha-primary",
            "t_beta": "reviewer-beta-primary",
        },
        app_env="local",
    )


@pytest.fixture
def service(clock, identity_provider, clean_database) -> InvestigationService:
    database = Database(APP_DSN)
    repository = Repository(database)
    return InvestigationService(
        repository,
        EvidenceTools(repository, manifest_version="v1-2026-08-10"),
        DeterministicStubAdapter(),
        identity_provider,
        clock=clock,
    )


@pytest.fixture
def client(service, identity_provider) -> TestClient:
    settings = Settings(
        app_env="local",
        database_url=APP_DSN,
        identity_provider="simulated",
        identities_file=Path(".local/test-not-used.json"),
        reasoning_provider="stub",
    )
    with TestClient(
        create_app(
            settings,
            service=service,
            identity_provider=identity_provider,
            database=service.repository.database,
        )
    ) as test_client:
        yield test_client


def auth(name: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKENS[name]}"}


def create_run(
    client: TestClient,
    *,
    key: str,
    request: dict[str, object] | None = None,
) -> dict[str, object]:
    response = client.post(
        "/v1/investigations",
        headers={**auth("operator_alpha"), "Idempotency-Key": key},
        json=request or CANONICAL_REQUEST,
    )
    assert response.status_code == 201, response.text
    return response.json()
