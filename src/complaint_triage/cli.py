"""Command-line entry points for the complaint triage project."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from complaint_triage.abstention_analysis import (
    AbstentionAnalysisError,
    analyze_abstention_thresholds,
    safe_abstention_analysis_error,
)
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
from complaint_triage.cli_parser import build_parser
from complaint_triage.db import DatabaseSettingsError
from complaint_triage.live_extraction import acquire_real_run, safe_live_result
from complaint_triage.majority_baseline import (
    MajorityBaselineError,
    evaluate_majority_baseline,
    safe_majority_baseline_error,
)
from complaint_triage.model_selection import (
    ModelSelectionError,
    safe_model_selection_error,
    select_operational_model,
)
from complaint_triage.raw_ingestion import RawIngestionError, ingest_raw_batch, safe_ingestion_error
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
from complaint_triage.transformer_calibration import (
    TransformerCalibrationError,
    calibrate_transformer,
    safe_transformer_calibration_error,
)
from complaint_triage.transformer_dataset import (
    TransformerDatasetError,
    safe_transformer_dataset_error,
    validate_transformer_dataset,
)
from complaint_triage.transformer_fit import (
    TransformerFitError,
    safe_transformer_fit_error,
    train_transformer,
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
from complaint_triage.validation_comparison import (
    ValidationComparisonError,
    compare_validation_models,
    safe_validation_comparison_error,
)

JsonReport = Mapping[str, Any]
ErrorRenderer = Callable[[Any], JsonReport]
FailureFactory = Callable[[], JsonReport]


@dataclass(frozen=True)
class CommandSpec:
    """Declarative adapter for one ordinary report command."""

    runner_name: str
    argument_names: tuple[str, ...]
    error_type: type[Exception]
    error_renderer: ErrorRenderer
    database_failure: FailureFactory | None = None


def _emit(report: JsonReport, exit_code: int = 0) -> int:
    print(json.dumps(report, indent=2, sort_keys=True))
    return exit_code


def _database_error(privacy: Mapping[str, bool]) -> JsonReport:
    return {
        "status": "error",
        "error": {"code": "database_configuration_invalid"},
        "privacy": privacy,
    }


SIMPLE_COMMANDS = {
    "profile-cfpb": CommandSpec("fetch_cfpb_profile", (), ProfileError, safe_error_report),
    "ingest-raw-batch": CommandSpec(
        "ingest_raw_batch",
        ("manifest",),
        RawIngestionError,
        safe_ingestion_error,
        lambda: _database_error({"source_values_logged": False, "raw_payload_logged": False}),
    ),
    "stage-raw-batch": CommandSpec(
        "stage_raw_batch",
        ("batch_id",),
        StagingError,
        safe_staging_error,
        lambda: _database_error({"source_values_logged": False, "raw_payload_logged": False}),
    ),
    "profile-taxonomy": CommandSpec(
        "fetch_taxonomy_profile", (), TaxonomyProfileError, safe_taxonomy_error_report
    ),
    "report-population": CommandSpec(
        "report_analytical_population",
        ("batch_id",),
        PopulationError,
        safe_population_error,
        lambda: _database_error(
            {
                "narratives_logged": False,
                "narratives_in_report": False,
                "narratives_copied_to_analytical": False,
            }
        ),
    ),
    "report-real-run": CommandSpec(
        "report_real_run",
        ("run_manifest",),
        RealRunReportError,
        safe_real_run_report_error,
        lambda: safe_real_run_report_error(RealRunReportError("database_configuration_invalid")),
    ),
    "build-temporal-split": CommandSpec(
        "build_temporal_split",
        ("run_manifest",),
        TemporalSplitError,
        safe_temporal_split_error,
        lambda: safe_temporal_split_error(TemporalSplitError("database_configuration_invalid")),
    ),
    "evaluate-majority-baseline": CommandSpec(
        "evaluate_majority_baseline",
        ("split_manifest",),
        MajorityBaselineError,
        safe_majority_baseline_error,
    ),
    "analyze-baseline-errors": CommandSpec(
        "analyze_baseline_errors",
        ("model_report",),
        BaselineErrorAnalysisError,
        safe_baseline_error,
        lambda: safe_baseline_error(BaselineErrorAnalysisError("database_configuration_invalid")),
    ),
    "profile-transformer-tokens": CommandSpec(
        "profile_transformer_tokens",
        ("split_manifest",),
        TransformerTokenProfileError,
        safe_transformer_token_profile_error,
        lambda: safe_transformer_token_profile_error(
            TransformerTokenProfileError("database_configuration_invalid")
        ),
    ),
    "validate-transformer-dataset": CommandSpec(
        "validate_transformer_dataset",
        ("split_manifest",),
        TransformerDatasetError,
        safe_transformer_dataset_error,
        lambda: safe_transformer_dataset_error(
            TransformerDatasetError("database_configuration_invalid")
        ),
    ),
    "smoke-transformer-training": CommandSpec(
        "smoke_transformer_training",
        ("split_manifest",),
        TransformerTrainingError,
        safe_transformer_training_error,
        lambda: safe_transformer_training_error(
            TransformerTrainingError("database_configuration_invalid")
        ),
    ),
    "compare-validation-models": CommandSpec(
        "compare_validation_models",
        ("baseline_report", "transformer_report"),
        ValidationComparisonError,
        safe_validation_comparison_error,
    ),
    "calibrate-transformer": CommandSpec(
        "calibrate_transformer",
        ("transformer_report",),
        TransformerCalibrationError,
        safe_transformer_calibration_error,
        lambda: safe_transformer_calibration_error(
            TransformerCalibrationError("database_configuration_invalid")
        ),
    ),
    "select-operational-model": CommandSpec(
        "select_operational_model",
        ("calibration_report",),
        ModelSelectionError,
        safe_model_selection_error,
        lambda: safe_model_selection_error(ModelSelectionError("database_configuration_invalid")),
    ),
    "analyze-abstention": CommandSpec(
        "analyze_abstention_thresholds",
        ("model_selection_report",),
        AbstentionAnalysisError,
        safe_abstention_analysis_error,
        lambda: safe_abstention_analysis_error(
            AbstentionAnalysisError("database_configuration_invalid")
        ),
    ),
}


def _command_runners() -> dict[str, Callable[..., JsonReport]]:
    """Resolve runners at dispatch time so tests and adapters can replace them."""
    return {
        "fetch_cfpb_profile": fetch_cfpb_profile,
        "ingest_raw_batch": ingest_raw_batch,
        "stage_raw_batch": stage_raw_batch,
        "fetch_taxonomy_profile": fetch_taxonomy_profile,
        "report_analytical_population": report_analytical_population,
        "report_real_run": report_real_run,
        "build_temporal_split": build_temporal_split,
        "evaluate_majority_baseline": evaluate_majority_baseline,
        "analyze_baseline_errors": analyze_baseline_errors,
        "profile_transformer_tokens": profile_transformer_tokens,
        "validate_transformer_dataset": validate_transformer_dataset,
        "smoke_transformer_training": smoke_transformer_training,
        "compare_validation_models": compare_validation_models,
        "calibrate_transformer": calibrate_transformer,
        "select_operational_model": select_operational_model,
        "analyze_abstention_thresholds": analyze_abstention_thresholds,
    }


def _run_simple(args: argparse.Namespace, spec: CommandSpec) -> int:
    runner = _command_runners()[spec.runner_name]
    values = [getattr(args, name) for name in spec.argument_names]
    try:
        return _emit(runner(*values))
    except spec.error_type as error:
        return _emit(spec.error_renderer(error), 1)
    except DatabaseSettingsError:
        if spec.database_failure is None:
            raise
        return _emit(spec.database_failure(), 1)


def _cleanup(args: argparse.Namespace) -> int:
    try:
        report = cleanup_real_data(
            args.run_manifest, execute=args.execute, confirmation=args.confirmation
        )
    except (ExtractionError, OSError, json.JSONDecodeError) as error:
        controlled = (
            error
            if isinstance(error, ExtractionError)
            else ExtractionError("cleanup_manifest_unreadable")
        )
        return _emit(safe_extraction_error(controlled), 1)
    return _emit(report)


def _acquire(args: argparse.Namespace) -> int:
    try:
        return _emit(acquire_real_run(confirmation=args.confirmation))
    except ExtractionError as error:
        return _emit(safe_live_result(error), 1)


def _tfidf(args: argparse.Namespace) -> int:
    try:
        runner = smoke_tfidf_logreg if args.smoke else train_tfidf_logreg
        return _emit(runner(args.split_manifest))
    except TfidfLogregError as error:
        return _emit(safe_tfidf_logreg_error(error), 1)
    except DatabaseSettingsError:
        error = TfidfLogregError("database_configuration_invalid")
        return _emit(safe_tfidf_logreg_error(error), 1)


def _transformer_progress(event: Mapping[str, Any]) -> None:
    print(json.dumps(dict(event), sort_keys=True), file=sys.stderr, flush=True)


def _fit_transformer(args: argparse.Namespace) -> int:
    try:
        return _emit(train_transformer(args.split_manifest, progress=_transformer_progress))
    except TransformerFitError as error:
        return _emit(safe_transformer_fit_error(error), 1)
    except DatabaseSettingsError:
        error = TransformerFitError("database_configuration_invalid")
        return _emit(safe_transformer_fit_error(error), 1)


SPECIAL_COMMANDS = {
    "cleanup-real-data": _cleanup,
    "acquire-real-run": _acquire,
    "train-tfidf-logreg": _tfidf,
    "train-transformer": _fit_transformer,
}


def dispatch(args: argparse.Namespace) -> int:
    """Dispatch a parsed command through one bounded handler."""
    if spec := SIMPLE_COMMANDS.get(args.command):
        return _run_simple(args, spec)
    try:
        handler = SPECIAL_COMMANDS[args.command]
    except KeyError as error:
        raise AssertionError(f"Unhandled command: {args.command}") from error
    return handler(args)


def main(argv: Sequence[str] | None = None) -> int:
    return dispatch(build_parser().parse_args(argv))
