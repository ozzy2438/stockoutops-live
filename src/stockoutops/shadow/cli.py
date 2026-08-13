"""Local deterministic M2 shadow pilot; never calls OpenAI or an external action."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from stockoutops.database import Database
from stockoutops.evidence.tools import EvidenceTools
from stockoutops.identity import Principal, SimulatedIdentityProvider
from stockoutops.reasoning.deterministic_stub import DeterministicStubAdapter
from stockoutops.repository import Repository
from stockoutops.service import InvestigationService
from stockoutops.shadow.cases import load_case_pack, seed_case_fixtures
from stockoutops.shadow.report import aggregate_report, write_reports
from stockoutops.shadow.repository import ShadowRepository
from stockoutops.shadow.service import ShadowService


def _git_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _fixed_clock(value: datetime) -> Callable[[], datetime]:
    def current() -> datetime:
        return value

    return current


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the execute-false M2 shadow pilot")
    parser.add_argument("--cases", default="evaluation/shadow/cases/v1")
    parser.add_argument("--output-dir", default="evaluation/reports")
    parser.add_argument("--execute", choices=["false"], default="false")
    parser.add_argument("--git-sha", default=None)
    parser.add_argument(
        "--test-evidence",
        default="UNMEASURED — run the full test suite independently before assurance.",
    )
    args = parser.parse_args()
    migration_dsn = os.environ["MIGRATION_DATABASE_URL"]
    application_dsn = os.environ["DATABASE_URL"]
    loaded = load_case_pack(Path(args.cases))
    seed_case_fixtures(migration_dsn, loaded.pack)

    database = Database(application_dsn)
    repository = Repository(database)
    identity_provider = SimulatedIdentityProvider(
        {},
        {
            "t_alpha": "reviewer-alpha-primary",
            "t_beta": "reviewer-beta-primary",
        },
        app_env="local",
    )
    results = []
    for case in loaded.pack.cases:
        fixed_now = case.as_of_timestamp + timedelta(minutes=30)
        clock = _fixed_clock(fixed_now)
        investigation_service = InvestigationService(
            repository,
            EvidenceTools(repository, manifest_version=loaded.pack.case_pack_version),
            DeterministicStubAdapter(),
            identity_provider,
            clock=clock,
        )
        shadow_service = ShadowService(
            ShadowRepository(database), investigation_service, clock=clock
        )
        principal = Principal(
            actor_id=f"shadow-operator-{case.tenant_id}",
            tenant_id=case.tenant_id,
            roles=frozenset({"operator"}),
        )
        results.append(
            shadow_service.process(
                principal,
                case,
                case_pack_version=loaded.pack.case_pack_version,
                idempotency_key=(
                    f"{loaded.pack.case_pack_version}:{case.case_id}:{case.case_version}"
                ),
                execute=False,
            )
        )

    report = aggregate_report(
        results,
        loaded,
        git_sha=args.git_sha or _git_sha(),
        generated_at=datetime.now(UTC),
        test_evidence=args.test_evidence,
    )
    written = write_reports(report, Path(args.output_dir))
    print(
        json.dumps(
            {
                "case_count": len(results),
                "execute": False,
                "external_action_count": 0,
                "provider": "deterministic-stub-v1",
                "aggregate_json": str(written.aggregate_json),
                "aggregate_json_sha256": written.aggregate_json_sha256,
                "aggregate_markdown": str(written.aggregate_markdown),
                "aggregate_markdown_sha256": written.aggregate_markdown_sha256,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
