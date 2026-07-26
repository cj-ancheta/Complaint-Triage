"""Generate the manuscript's result tables from committed aggregate evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from complaint_triage.paper_figures import render_figures
from complaint_triage.real_extraction import PROJECT_ROOT

EVALUATION_ROOT = PROJECT_ROOT / "data" / "evaluations" / "cfpb"
MANUSCRIPT_PATH = PROJECT_ROOT / "paper" / "manuscript.md"
GENERATED_ROOT = PROJECT_ROOT / "paper" / "generated"
TABLES_PATH = GENERATED_ROOT / "result_tables.md"
MANIFEST_PATH = GENERATED_ROOT / "source_manifest.json"
RUN_REPORT_PATH = (
    PROJECT_ROOT
    / "data"
    / "manifests"
    / "cfpb"
    / "reports"
    / "cfpb-run-20260722T130728Z-2b7815d4c850.json"
)
SPLIT_MANIFEST_PATH = (
    PROJECT_ROOT
    / "data"
    / "manifests"
    / "cfpb"
    / "splits"
    / "cfpb-run-20260722T130728Z-2b7815d4c850-split-1.0.0.json"
)
QA_FINDINGS_PATH = PROJECT_ROOT / "docs" / "qa" / "qa_findings.json"


def _load_single_report(directory: str) -> dict[str, Any]:
    paths = sorted((EVALUATION_ROOT / directory).glob("*.json"))
    if len(paths) != 1:
        raise RuntimeError(f"expected one {directory} report, found {len(paths)}")
    return json.loads(paths[0].read_text(encoding="utf-8"))


def _fixed(value: float) -> str:
    return f"{value:.6f}"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def render_cohort_table() -> str:
    run = _load_json(RUN_REPORT_PATH)
    split = _load_json(SPLIT_MANIFEST_PATH)
    rows = (
        ("Structurally staged", run["counts"]["staging_accepted_record_count"], "input"),
        ("English eligible", run["counts"]["eligible_record_count"], "801 language exclusions"),
        (
            "Canonical included",
            split["counts"]["included_record_count"],
            "after duplicate isolation",
        ),
        ("Train", split["split_counts"]["train"], "model fitting"),
        ("Validation", split["split_counts"]["validation"], "model and policy tuning"),
        ("Frozen test", split["split_counts"]["test"], "sealed; no paper performance"),
    )
    return "\n".join(
        (
            "| Cohort stage | Records | Role or disposition |",
            "|---|---:|---|",
            *(f"| {label} | {count:,} | {note} |" for label, count, note in rows),
        )
    )


def render_model_comparison_table() -> str:
    majority = _load_single_report("majority")["evaluation"]["validation"]["metrics"]
    comparison = _load_single_report("model-comparison")["comparison"]["shared_validation_metrics"]
    rows = []
    specifications = (
        ("Accuracy", "accuracy"),
        ("Macro F1", "macro_f1"),
        ("Weighted F1", "weighted_f1"),
        ("Worst-class recall", "worst_class_recall"),
    )
    for label, key in specifications:
        evidence = comparison[key]
        majority_value = 0.0 if key == "worst_class_recall" else majority[key]
        rows.append(
            f"| {label} | {_fixed(majority_value)} | {_fixed(evidence['baseline'])} | "
            f"{_fixed(evidence['transformer'])} | "
            f"{evidence['delta_transformer_minus_baseline']:+.6f} |"
        )
    return "\n".join(
        (
            "| Metric | Majority reference | TF-IDF | MiniLM | MiniLM - TF-IDF |",
            "|---|---:|---:|---:|---:|",
            *rows,
        )
    )


def render_calibration_table() -> str:
    evaluation = _load_single_report("calibration")["results"]["calibration_evaluation"]
    before = evaluation["before"]
    after = evaluation["after"]
    specifications = (
        ("Accuracy", "accuracy"),
        ("Mean top-label confidence", "mean_top_label_confidence"),
        ("Confidence minus accuracy", "signed_confidence_minus_accuracy"),
        ("Negative log likelihood", "negative_log_likelihood"),
        ("Multiclass Brier loss", "multiclass_brier_loss"),
        ("Equal-width ECE, 15 bins", "top_label_ece_equal_width_15"),
        ("Equal-mass ECE, 15 bins", "top_label_ece_equal_mass_15"),
    )
    rows = [
        f"| {label} | {_fixed(before[key])} | {_fixed(after[key])} | "
        f"{after[key] - before[key]:+.6f} |"
        for label, key in specifications
    ]
    return "\n".join(
        (
            "| October diagnostic | Before | After | Change |",
            "|---|---:|---:|---:|",
            *rows,
        )
    )


def render_per_class_table() -> str:
    comparison = _load_single_report("model-comparison")["comparison"]["per_class"]
    rows = []
    for entry in comparison:
        rows.append(
            f"| {entry['label']} | {entry['support']:,} | "
            f"{_fixed(entry['baseline']['f1'])} | {_fixed(entry['baseline']['recall'])} | "
            f"{_fixed(entry['transformer']['f1'])} | "
            f"{_fixed(entry['transformer']['recall'])} | {entry['f1_winner']} |"
        )
    return "\n".join(
        (
            "| Class | Support | TF-IDF F1 | TF-IDF recall | MiniLM F1 | "
            "MiniLM recall | F1 winner |",
            "|---|---:|---:|---:|---:|---:|---|",
            *rows,
        )
    )


def _blocking_evidence(entry: dict[str, Any]) -> str:
    failures = [name for name, passed in entry["checks"].items() if not passed]
    descriptions = []
    if "false_suggestion_rate_at_most_0p05" in failures:
        descriptions.append("false suggestions exceed 0.05")
    if "every_predicted_class_has_at_least_20_suggestions" in failures:
        minimum = entry["minimum_predicted_class_suggestions"]
        descriptions.append(f"least-suggested class has {minimum} cases")
    if "every_predicted_class_precision_at_least_0p50" in failures:
        descriptions.append("predicted-class precision gate fails")
    return "; ".join(descriptions)


def render_abstention_table() -> str:
    thresholds = _load_single_report("abstention")["thresholds"]
    selected = [entry for entry in thresholds if entry["threshold"] in (0.75, 0.8)]
    if [entry["threshold"] for entry in selected] != [0.75, 0.8]:
        raise RuntimeError("required diagnostic abstention thresholds are missing")
    rows = [
        f"| {entry['threshold']:.2f} | {_fixed(entry['coverage'])} | "
        f"{_fixed(entry['review_rate'])} | {_fixed(entry['selective_accuracy'])} | "
        f"{_fixed(entry['false_suggestion_rate'])} | {_blocking_evidence(entry)} |"
        for entry in selected
    ]
    return "\n".join(
        (
            "| Threshold | Coverage | Review rate | Selective accuracy | "
            "False suggestion rate | Blocking evidence |",
            "|---:|---:|---:|---:|---:|---|",
            *rows,
        )
    )


def render_qa_table() -> str:
    findings = _load_json(QA_FINDINGS_PATH)
    summary = findings["summary"]
    severity_rows = [
        f"| {severity.title()} | {summary[severity]} |"
        for severity in ("critical", "high", "medium", "low")
    ]
    category_counts: dict[str, int] = {}
    for finding in findings["findings"]:
        category = finding["category"]
        category_counts[category] = category_counts.get(category, 0) + 1
        if finding["status"] != "resolved":
            raise RuntimeError(f"unresolved accepted QA finding: {finding['finding_id']}")
    category_rows = [
        f"| {category} | {count} | resolved |"
        for category, count in sorted(category_counts.items())
    ]
    return "\n".join(
        (
            "### Severity",
            "",
            "| Severity | Findings |",
            "|---|---:|",
            *severity_rows,
            "",
            "### Control family",
            "",
            "| Control family | Findings | Accepted status |",
            "|---|---:|---|",
            *category_rows,
        )
    )


def render_tables() -> dict[str, str]:
    return {
        "model-comparison": render_model_comparison_table(),
        "calibration": render_calibration_table(),
        "abstention": render_abstention_table(),
    }


def render_generated_tables() -> str:
    tables = render_tables()
    return "\n".join(
        (
            "# Generated validation result tables",
            "",
            "Status: deterministic aggregate output; validation-only",
            "",
            "These tables are generated from the committed JSON listed in",
            "`source_manifest.json`. Do not edit them manually.",
            "",
            "## T1. Governed cohort flow",
            "",
            render_cohort_table(),
            "",
            "*Aggregate cohort evidence; frozen-test performance is not accessed.*",
            "",
            "## T2. Validation model comparison",
            "",
            tables["model-comparison"],
            "",
            "*Validation-only comparison; the frozen test is not reported.*",
            "",
            "## T3. Per-class validation comparison",
            "",
            render_per_class_table(),
            "",
            "*Validation-only class metrics in immutable taxonomy order.*",
            "",
            "## T4. October temperature-scaling assessment",
            "",
            tables["calibration"],
            "",
            "*Validation-only tuning evidence from October.*",
            "",
            "## T5. Representative abstention failures",
            "",
            tables["abstention"],
            "",
            "*Validation-only policy evidence; neither threshold was eligible.*",
            "",
            "## T6. Accepted repository QA findings",
            "",
            render_qa_table(),
            "",
            "*Repository assurance evidence; not a model-validity measure.*",
            "",
        )
    )


def _source_paths() -> list[Path]:
    directories = ("majority", "model-comparison", "calibration", "abstention")
    paths = []
    for directory in directories:
        matches = sorted((EVALUATION_ROOT / directory).glob("*.json"))
        if len(matches) != 1:
            raise RuntimeError(f"expected one {directory} report, found {len(matches)}")
        paths.append(matches[0])
    return [RUN_REPORT_PATH, SPLIT_MANIFEST_PATH, *paths, QA_FINDINGS_PATH]


def canonical_sha256(path: Path) -> str:
    canonical_bytes = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(canonical_bytes).hexdigest()


def render_source_manifest() -> str:
    sources = []
    for path in _source_paths():
        sources.append(
            {
                "path": path.relative_to(PROJECT_ROOT).as_posix(),
                "sha256": canonical_sha256(path),
            }
        )
    manifest = {
        "generator": "complaint_triage.paper_tables",
        "manifest_version": "1.0.0",
        "outputs": [
            TABLES_PATH.relative_to(PROJECT_ROOT).as_posix(),
            MANUSCRIPT_PATH.relative_to(PROJECT_ROOT).as_posix(),
            *[f"paper/generated/{filename}" for filename in sorted(render_figures())],
        ],
        "privacy": {
            "contains_complaint_ids": False,
            "contains_narratives": False,
            "contains_row_values": False,
        },
        "sources": sources,
    }
    return json.dumps(manifest, indent=2, sort_keys=True) + "\n"


def render_manuscript(manuscript: str) -> str:
    rendered = manuscript
    for name, table in render_tables().items():
        start = f"<!-- GENERATED:{name}:start -->"
        end = f"<!-- GENERATED:{name}:end -->"
        if rendered.count(start) != 1 or rendered.count(end) != 1:
            raise RuntimeError(f"expected one generated block for {name}")
        prefix, remainder = rendered.split(start, maxsplit=1)
        _, suffix = remainder.split(end, maxsplit=1)
        rendered = f"{prefix}{start}\n{table}\n{end}{suffix}"
    return rendered


def generate_manuscript(path: Path = MANUSCRIPT_PATH, *, check: bool = False) -> bool:
    current = path.read_text(encoding="utf-8")
    rendered = render_manuscript(current)
    matches = current == rendered
    if check:
        return matches
    path.write_text(rendered, encoding="utf-8", newline="\n")
    return matches


def generate_assets(*, check: bool = False) -> bool:
    manuscript_matches = generate_manuscript(check=check)
    expected_outputs = {
        TABLES_PATH: render_generated_tables(),
        MANIFEST_PATH: render_source_manifest(),
    }
    expected_outputs.update(
        {GENERATED_ROOT / filename: content for filename, content in render_figures().items()}
    )
    output_matches = all(
        path.is_file() and path.read_text(encoding="utf-8") == expected
        for path, expected in expected_outputs.items()
    )
    if not check:
        GENERATED_ROOT.mkdir(parents=True, exist_ok=True)
        for path, expected in expected_outputs.items():
            path.write_text(expected, encoding="utf-8", newline="\n")
    return manuscript_matches and output_matches


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when generated manuscript tables differ from committed evidence",
    )
    arguments = parser.parse_args(argv)
    matches = generate_assets(check=arguments.check)
    if arguments.check and not matches:
        print("paper generated assets are stale; run this module without --check")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
