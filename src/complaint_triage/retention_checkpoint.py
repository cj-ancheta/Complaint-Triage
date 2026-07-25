"""Aggregate-only checkpoint for the approved local raw-data deadline."""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from complaint_triage.retention_policy import (
    REAL_RETENTION_DEADLINE_UTC,
    REAL_RETENTION_POLICY_ID,
)

WARNING_WINDOW = timedelta(days=30)
STATUS_RANK = {"scheduled": 0, "due_soon": 1, "overdue": 2}


def build_retention_checkpoint(now_utc: datetime | None = None) -> dict[str, Any]:
    """Return a deterministic reminder without reading governed local data."""
    observed = now_utc or datetime.now(UTC)
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise ValueError("retention checkpoint requires a timezone-aware timestamp")
    observed = observed.astimezone(UTC)
    remaining = REAL_RETENTION_DEADLINE_UTC - observed
    if remaining.total_seconds() < 0:
        status = "overdue"
    elif remaining <= WARNING_WINDOW:
        status = "due_soon"
    else:
        status = "scheduled"

    return {
        "checkpoint_version": "retention-checkpoint-1.0.0",
        "status": status,
        "policy_id": REAL_RETENTION_POLICY_ID,
        "observed_at_utc": observed.isoformat().replace("+00:00", "Z"),
        "deadline_utc": REAL_RETENTION_DEADLINE_UTC.isoformat().replace("+00:00", "Z"),
        "days_remaining": max(0, math.ceil(remaining.total_seconds() / 86_400)),
        "cleanup_required": status == "overdue",
        "cleanup_command": (
            "complaint-triage cleanup-real-data --run-manifest <RUN_MANIFEST> "
            "--execute --confirmation <RUN_ID>"
        ),
        "privacy": {
            "filesystem_scanned": False,
            "raw_data_read": False,
            "network_used": False,
            "contains_narratives": False,
            "contains_complaint_ids": False,
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fail-on",
        choices=("due_soon", "overdue", "never"),
        default="overdue",
        help="Earliest status that returns exit code 2.",
    )
    args = parser.parse_args(argv)
    report = build_retention_checkpoint()
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.fail_on != "never" and STATUS_RANK[report["status"]] >= STATUS_RANK[args.fail_on]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
