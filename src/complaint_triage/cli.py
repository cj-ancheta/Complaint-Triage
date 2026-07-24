"""Command-line entry points for the complaint triage project."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from complaint_triage.analytical_population import (
    PopulationError,
    report_analytical_population,
    safe_population_error,
)
from complaint_triage.baseline_error_analysis import (
    BaselineErrorAnalysisError,
    analyze_baseline_errors,
    safe_baseline_error,
)
from complaint_triage.cfpb_profile import ProfileError, fetch_cfpb_profile, safe_error_report
from complaint_triage.db import DatabaseSettingsError
from complaint_triage.live_extraction import acquire_real_run, safe_live_result
from complaint_triage.majority_baseline import (
    MajorityBaselineError,
    evaluate_majority_baseline,
    safe_majority_baseline_error,
)
from complaint_triage.raw_ingestion import (
    RawIngestionError,
    ingest_raw_batch,
    safe_ingestion_error,
)
from complaint_triage.real_extraction import (
    ExtractionError,
    cleanup_real_data,
    safe_extraction_error,
)
from complaint_triage.real_run_report import (
    RealRunReportError,
    report_real_run,
    safe_real_run_report_error,
)
from complaint_triage.staging import StagingError, safe_staging_error, stage_raw_batch
from complaint_triage.taxonomy_profile import (
    TaxonomyProfileError,
    fetch_taxonomy_profile,
    safe_taxonomy_error_report,
)
from complaint_triage.temporal_split import (
    TemporalSplitError,
    build_temporal_split,
    safe_temporal_split_error,
)
from complaint_triage.tfidf_logreg import (
    TfidfLogregError,
    safe_tfidf_logreg_error,
    smoke_tfidf_logreg,
    train_tfidf_logreg,
)
from complaint_triage.transformer_dataset import (
    TransformerDatasetError,
    safe_transformer_dataset_error,
    validate_transformer_dataset,
)
from complaint_triage.transformer_token_profile import (
    TransformerTokenProfileError,
    profile_transformer_tokens,
    safe_transformer_token_profile_error,
)
from complaint_triage.transformer_training import (
    TransformerTrainingError,
    safe_transformer_training_error,
    smoke_transformer_training,
)


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
    subcommands.add_parser(
        "profile-taxonomy",
        help="Run the fixed aggregate-only CFPB taxonomy stability profile.",
    )
    population_parser = subcommands.add_parser(
        "report-population",
        help="Create a versioned aggregate analytical-population report.",
    )
    population_parser.add_argument("--batch-id", required=True, help="Staged raw batch ID.")
    cleanup_parser = subcommands.add_parser(
        "cleanup-real-data",
        help="Inventory an extraction run, or delete it with exact confirmation.",
    )
    cleanup_parser.add_argument("--run-manifest", type=Path, required=True)
    cleanup_parser.add_argument("--execute", action="store_true")
    cleanup_parser.add_argument("--confirmation")
    acquire_parser = subcommands.add_parser(
        "acquire-real-run",
        help="Acquire the approved retained CFPB run from a clean commit.",
    )
    acquire_parser.add_argument(
        "--confirmation",
        required=True,
        help="Must exactly match the accepted retention policy ID.",
    )
    run_report_parser = subcommands.add_parser(
        "report-real-run",
        help="Reconcile and publish an aggregate-only report for one real run.",
    )
    run_report_parser.add_argument("--run-manifest", type=Path, required=True)
    split_parser = subcommands.add_parser(
        "build-temporal-split",
        help="Build the approved deduplicated temporal split for one real run.",
    )
    split_parser.add_argument("--run-manifest", type=Path, required=True)
    majority_parser = subcommands.add_parser(
        "evaluate-majority-baseline",
        help="Evaluate the training-majority reference against the accepted split.",
    )
    majority_parser.add_argument("--split-manifest", type=Path, required=True)
    tfidf_parser = subcommands.add_parser(
        "train-tfidf-logreg",
        help="Run the approved validation-only TF-IDF logistic search.",
    )
    tfidf_parser.add_argument("--split-manifest", type=Path, required=True)
    tfidf_parser.add_argument(
        "--smoke",
        action="store_true",
        help="Fit a bounded training-only sample without writing evidence.",
    )
    error_analysis_parser = subcommands.add_parser(
        "analyze-baseline-errors",
        help="Produce validation-only aggregate error analysis for the selected baseline.",
    )
    error_analysis_parser.add_argument("--model-report", type=Path, required=True)
    token_profile_parser = subcommands.add_parser(
        "profile-transformer-tokens",
        help="Profile pinned MiniLM token lengths using training narratives only.",
    )
    token_profile_parser.add_argument("--split-manifest", type=Path, required=True)
    dataset_parser = subcommands.add_parser(
        "validate-transformer-dataset",
        help="Validate deterministic train/validation tokenization and dynamic padding.",
    )
    dataset_parser.add_argument("--split-manifest", type=Path, required=True)
    transformer_smoke_parser = subcommands.add_parser(
        "smoke-transformer-training",
        help="Run approved synthetic-memory and training-only MiniLM smokes.",
    )
    transformer_smoke_parser.add_argument("--split-manifest", type=Path, required=True)
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

    if args.command == "profile-taxonomy":
        try:
            report = fetch_taxonomy_profile()
        except TaxonomyProfileError as error:
            print(json.dumps(safe_taxonomy_error_report(error), indent=2, sort_keys=True))
            return 1

        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.command == "report-population":
        try:
            report = report_analytical_population(args.batch_id)
        except PopulationError as error:
            print(json.dumps(safe_population_error(error), indent=2, sort_keys=True))
            return 1
        except DatabaseSettingsError:
            print(
                json.dumps(
                    {
                        "status": "error",
                        "error": {"code": "database_configuration_invalid"},
                        "privacy": {
                            "narratives_logged": False,
                            "narratives_in_report": False,
                            "narratives_copied_to_analytical": False,
                        },
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 1

        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.command == "cleanup-real-data":
        try:
            report = cleanup_real_data(
                args.run_manifest,
                execute=args.execute,
                confirmation=args.confirmation,
            )
        except (ExtractionError, OSError, json.JSONDecodeError) as error:
            controlled = (
                error
                if isinstance(error, ExtractionError)
                else ExtractionError("cleanup_manifest_unreadable")
            )
            print(json.dumps(safe_extraction_error(controlled), indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.command == "acquire-real-run":
        try:
            report = acquire_real_run(confirmation=args.confirmation)
        except ExtractionError as error:
            print(json.dumps(safe_live_result(error), indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.command == "report-real-run":
        try:
            report = report_real_run(args.run_manifest)
        except RealRunReportError as error:
            print(json.dumps(safe_real_run_report_error(error), indent=2, sort_keys=True))
            return 1
        except DatabaseSettingsError:
            print(
                json.dumps(
                    safe_real_run_report_error(
                        RealRunReportError("database_configuration_invalid")
                    ),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.command == "build-temporal-split":
        try:
            report = build_temporal_split(args.run_manifest)
        except TemporalSplitError as error:
            print(json.dumps(safe_temporal_split_error(error), indent=2, sort_keys=True))
            return 1
        except DatabaseSettingsError:
            print(
                json.dumps(
                    safe_temporal_split_error(TemporalSplitError("database_configuration_invalid")),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.command == "evaluate-majority-baseline":
        try:
            report = evaluate_majority_baseline(args.split_manifest)
        except MajorityBaselineError as error:
            print(json.dumps(safe_majority_baseline_error(error), indent=2, sort_keys=True))
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.command == "train-tfidf-logreg":
        try:
            report = (
                smoke_tfidf_logreg(args.split_manifest)
                if args.smoke
                else train_tfidf_logreg(args.split_manifest)
            )
        except TfidfLogregError as error:
            print(json.dumps(safe_tfidf_logreg_error(error), indent=2, sort_keys=True))
            return 1
        except DatabaseSettingsError:
            print(
                json.dumps(
                    safe_tfidf_logreg_error(TfidfLogregError("database_configuration_invalid")),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.command == "analyze-baseline-errors":
        try:
            report = analyze_baseline_errors(args.model_report)
        except BaselineErrorAnalysisError as error:
            print(json.dumps(safe_baseline_error(error), indent=2, sort_keys=True))
            return 1
        except DatabaseSettingsError:
            print(
                json.dumps(
                    safe_baseline_error(
                        BaselineErrorAnalysisError("database_configuration_invalid")
                    ),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.command == "profile-transformer-tokens":
        try:
            report = profile_transformer_tokens(args.split_manifest)
        except TransformerTokenProfileError as error:
            print(json.dumps(safe_transformer_token_profile_error(error), indent=2, sort_keys=True))
            return 1
        except DatabaseSettingsError:
            print(
                json.dumps(
                    safe_transformer_token_profile_error(
                        TransformerTokenProfileError("database_configuration_invalid")
                    ),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.command == "validate-transformer-dataset":
        try:
            report = validate_transformer_dataset(args.split_manifest)
        except TransformerDatasetError as error:
            print(json.dumps(safe_transformer_dataset_error(error), indent=2, sort_keys=True))
            return 1
        except DatabaseSettingsError:
            print(
                json.dumps(
                    safe_transformer_dataset_error(
                        TransformerDatasetError("database_configuration_invalid")
                    ),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.command == "smoke-transformer-training":
        try:
            report = smoke_transformer_training(args.split_manifest)
        except TransformerTrainingError as error:
            print(json.dumps(safe_transformer_training_error(error), indent=2, sort_keys=True))
            return 1
        except DatabaseSettingsError:
            print(
                json.dumps(
                    safe_transformer_training_error(
                        TransformerTrainingError("database_configuration_invalid")
                    ),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 1
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    raise AssertionError(f"Unhandled command: {args.command}")
