"""Local/CI entry point for the durable alert-outbox delivery worker.

Requires explicit webhook configuration. Contacts only the configured
destination; local proofs use a loopback receiver. No AWS and no OpenAI.
"""

from __future__ import annotations

import argparse
import json
import os
import uuid

from stockoutops.alerting.delivery_settings import AlertDeliverySettings
from stockoutops.alerting.outbox import DEFAULT_LEASE_SECONDS, AlertOutboxRepository
from stockoutops.alerting.worker import build_worker
from stockoutops.database import Database


def main() -> None:
    parser = argparse.ArgumentParser(description="Drain the durable alert outbox once")
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--lease-seconds", type=float, default=DEFAULT_LEASE_SECONDS)
    parser.add_argument("--worker-id", default=None)
    args = parser.parse_args()

    settings = AlertDeliverySettings.from_env()
    if not settings.enabled:
        print(
            json.dumps(
                {
                    "status": "DISABLED",
                    "reason": "STOCKOUTOPS_ALERT_WEBHOOK_ENABLED is not set",
                    "leased": 0,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    database = Database(os.environ["DATABASE_URL"])
    worker = build_worker(
        AlertOutboxRepository(database),
        settings,
        worker_id=args.worker_id or f"worker-{uuid.uuid4()}",
        lease_seconds=args.lease_seconds,
    )
    result = worker.run_once(batch_size=args.batch_size)
    print(
        json.dumps(
            {
                "status": "RAN",
                "leased": result.leased,
                "delivered": result.delivered,
                "retried": result.retried,
                "dead_lettered": result.dead_lettered,
                "lease_lost": result.lease_lost,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
