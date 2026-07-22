"""Command-line entry points for the complaint triage project."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from complaint_triage.cfpb_profile import ProfileError, fetch_cfpb_profile, safe_error_report
from complaint_triage.db import DatabaseSettingsError
from complaint_triage.raw_ingestion import (
    RawIngestionError,
    ingest_raw_batch,
    safe_ingestion_error,
)
from complaint_triage.staging import StagingError, safe_staging_error, stage_raw_batch


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="complaint-triage")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser(
        "profile-cfpb",
        help="Run one fixed, five-hit CFPB source-contract check.",
    )
    ingest_parser = subcommands.add_parser(
        "ingest-raw-batch",
        help="Validate and load one content-addressed CFPB raw batch.",
    )
    ingest_parser.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help="Manifest under data/manifests/cfpb/.",
    )
    stage_parser = subcommands.add_parser(
        "stage-raw-batch",
        help="Create versioned staging outcomes for one ingested raw batch.",
    )
    stage_parser.add_argument("--batch-id", required=True, help="Raw ingestion batch ID.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "profile-cfpb":
        try:
            report = fetch_cfpb_profile()
        except ProfileError as error:
            print(json.dumps(safe_error_report(error), indent=2, sort_keys=True))
            return 1

        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.command == "ingest-raw-batch":
        try:
            report = ingest_raw_batch(args.manifest)
        except RawIngestionError as error:
            print(json.dumps(safe_ingestion_error(error), indent=2, sort_keys=True))
            return 1
        except DatabaseSettingsError:
            print(
                json.dumps(
                    {
                        "status": "error",
                        "error": {"code": "database_configuration_invalid"},
                        "privacy": {
                            "source_values_logged": False,
                            "raw_payload_logged": False,
                        },
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 1

        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.command == "stage-raw-batch":
        try:
            report = stage_raw_batch(args.batch_id)
        except StagingError as error:
            print(json.dumps(safe_staging_error(error), indent=2, sort_keys=True))
            return 1
        except DatabaseSettingsError:
            print(
                json.dumps(
                    {
                        "status": "error",
                        "error": {"code": "database_configuration_invalid"},
                        "privacy": {
                            "source_values_logged": False,
                            "raw_payload_logged": False,
                        },
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 1

        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    raise AssertionError(f"Unhandled command: {args.command}")
