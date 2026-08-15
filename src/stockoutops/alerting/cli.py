"""Local/CI alert-policy rehearsal over a generated simulated shadow report."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from stockoutops.alerting.delivery_settings import AlertDeliverySettings
from stockoutops.alerting.report import (
    build_alert_report,
    load_shadow_alert_source,
    write_alert_reports,
)
from stockoutops.alerting.repository import AlertRepository
from stockoutops.alerting.service import AlertService
from stockoutops.alerting.sink import build_alert_sink
from stockoutops.database import Database
from stockoutops.identity import Principal


def _git_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _timestamp(value: str | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("--generated-at requires an ISO-8601 timezone")
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local M2-04 alert-policy rehearsal")
    parser.add_argument(
        "--shadow-report",
        default="evaluation/reports/m2-shadow-foundation-pilot.json",
    )
    parser.add_argument("--output-dir", default="evaluation/reports")
    parser.add_argument("--git-sha", default=None)
    parser.add_argument("--generated-at", default=None)
    args = parser.parse_args()

    source = load_shadow_alert_source(Path(args.shadow_report))
    generated_at = _timestamp(args.generated_at)
    database = Database(os.environ["DATABASE_URL"])
    service = AlertService(
        AlertRepository(database),
        clock=lambda: generated_at,
        sink=build_alert_sink(database, AlertDeliverySettings.from_env()),
    )
    evaluations = []
    for snapshot in source.snapshots:
        principal = Principal(
            actor_id="m2-alert-policy-local-ci",
            tenant_id=snapshot.correlation.tenant_id,
            roles=frozenset({"operator"}),
        )
        evaluations.extend(
            service.evaluate(
                principal,
                snapshot,
                idempotency_prefix=source.source_report_sha256,
            )
        )

    report = build_alert_report(
        source,
        evaluations,
        git_sha=args.git_sha or _git_sha(),
        generated_at=generated_at,
    )
    written = write_alert_reports(report, Path(args.output_dir))
    print(
        json.dumps(
            {
                "evaluation_count": len(evaluations),
                "idempotent_replay_count": sum(item.idempotent_replay for item in evaluations),
                "execute": False,
                "external_action_count": report["controls"]["external_action_count"],
                "external_alert_delivery_count": 0,
                "live_slo_evidence_eligible": False,
                "json_path": str(written.json_path),
                "json_sha256": written.json_sha256,
                "markdown_path": str(written.markdown_path),
                "markdown_sha256": written.markdown_sha256,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
