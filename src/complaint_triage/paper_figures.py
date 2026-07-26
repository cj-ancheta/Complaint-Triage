# ruff: noqa: E501
"""Render deterministic, aggregate-only SVG figures for the research paper."""

from __future__ import annotations

import html
import json
import math
from pathlib import Path
from typing import Any

from complaint_triage.real_extraction import PROJECT_ROOT

EVALUATION_ROOT = PROJECT_ROOT / "data" / "evaluations" / "cfpb"
SPLIT_PATH = (
    PROJECT_ROOT
    / "data/manifests/cfpb/splits"
    / "cfpb-run-20260722T130728Z-2b7815d4c850-split-1.0.0.json"
)
QA_EVIDENCE_PATH = PROJECT_ROOT / "docs/qa/qa_evidence.json"
QA_FINDINGS_PATH = PROJECT_ROOT / "docs/qa/qa_findings.json"

NAVY = "#1B365D"
BLUE = "#0072B2"
ORANGE = "#D55E00"
TEAL = "#009E73"
GREY = "#6B7280"
LIGHT = "#E5E7EB"
INK = "#111827"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _report(directory: str) -> dict[str, Any]:
    paths = sorted((EVALUATION_ROOT / directory).glob("*.json"))
    if len(paths) != 1:
        raise RuntimeError(f"expected one {directory} report, found {len(paths)}")
    return _load(paths[0])


def _text(x: float, y: float, value: str, *, size: int = 14, **attributes: str) -> str:
    fill = attributes.pop("fill", INK)
    extra = " ".join(
        f'{key.replace("_", "-")}="{html.escape(str(item))}"' for key, item in attributes.items()
    )
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" '
        f'font-family="Arial, sans-serif" fill="{fill}" {extra}>{html.escape(value)}</text>'
    )


def _svg(width: int, height: int, title: str, description: str, body: list[str]) -> str:
    return "\n".join(
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img">',
            f"<title>{html.escape(title)}</title>",
            f"<desc>{html.escape(description)}</desc>",
            '<rect width="100%" height="100%" fill="white"/>',
            *body,
            "</svg>",
            "",
        )
    )


def render_pipeline() -> str:
    labels = (
        "16 source shards",
        "979,995 staged",
        "979,194 English",
        "561,342 canonical",
        "394,564 train",
        "80,992 validation",
        "85,786 sealed test",
    )
    body = [_text(40, 42, "F1. Governed evidence pipeline", size=24, font_weight="bold")]
    body.append(_text(40, 70, "Aggregate lineage only; validation-only study", size=14, fill=GREY))
    box_width = 170
    gap = 22
    y = 120
    for index, label in enumerate(labels):
        x = 30 + index * (box_width + gap)
        fill = "#F3F4F6" if index < 6 else "#FFF4E6"
        stroke = NAVY if index < 6 else ORANGE
        body.append(
            f'<rect x="{x}" y="{y}" width="{box_width}" height="80" rx="10" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
        )
        body.append(_text(x + box_width / 2, y + 46, label, size=14, text_anchor="middle"))
        if index < len(labels) - 1:
            arrow_x = x + box_width
            body.append(
                f'<line x1="{arrow_x + 3}" y1="{y + 40}" x2="{arrow_x + gap - 5}" '
                f'y2="{y + 40}" stroke="{GREY}" stroke-width="2"/>'
            )
            body.append(
                f'<path d="M {arrow_x + gap - 10} {y + 34} L {arrow_x + gap - 3} '
                f'{y + 40} L {arrow_x + gap - 10} {y + 46}" fill="none" '
                f'stroke="{GREY}" stroke-width="2"/>'
            )
    body.append(
        _text(40, 250, "417,852 duplicate-related exclusions occur before the split.", size=15)
    )
    body.append(
        _text(
            40,
            278,
            "The sealed test is described by count only; no performance is reported.",
            size=15,
            fill=ORANGE,
        )
    )
    return _svg(
        1380,
        320,
        "Governed evidence pipeline",
        "Cohort and split lineage with a sealed test boundary.",
        body,
    )


def _short_label(label: str) -> str:
    replacements = {
        "Checking or savings account": "Checking/savings",
        "Credit card": "Credit card",
        "Credit reporting or other personal consumer reports": "Credit reporting",
        "Debt collection": "Debt collection",
        "Debt or credit management": "Debt/credit management",
        "Money transfer, virtual currency, or money service": "Money transfer",
        "Mortgage": "Mortgage",
        "Payday loan, title loan, personal loan, or advance loan": "Payday/title/personal",
        "Prepaid card": "Prepaid card",
        "Student loan": "Student loan",
        "Vehicle loan or lease": "Vehicle loan/lease",
    }
    return replacements[label]


def render_class_support() -> str:
    split = _load(SPLIT_PATH)["class_counts_by_split"]
    labels = list(split["train"])
    width, height = 1200, 620
    left, top, plot_width = 270, 95, 760
    row_height = 43
    maximum = max(split["train"].values())
    body = [_text(35, 40, "F2. Training and validation class support", size=24, font_weight="bold")]
    body.append(_text(35, 68, "Log10 bar length; exact counts shown", size=14, fill=GREY))
    body.append(f'<rect x="850" y="28" width="14" height="14" fill="{BLUE}"/>')
    body.append(_text(870, 40, "Train", size=13))
    body.append(f'<rect x="940" y="28" width="14" height="14" fill="{ORANGE}"/>')
    body.append(_text(960, 40, "Validation", size=13))
    for index, label in enumerate(labels):
        y = top + index * row_height
        train = split["train"][label]
        validation = split["validation"][label]
        train_width = math.log10(train + 1) / math.log10(maximum + 1) * plot_width
        validation_width = math.log10(validation + 1) / math.log10(maximum + 1) * plot_width
        body.append(_text(left - 12, y + 15, _short_label(label), size=13, text_anchor="end"))
        body.append(
            f'<rect x="{left}" y="{y}" width="{train_width:.1f}" height="14" fill="{BLUE}"/>'
        )
        body.append(
            f'<rect x="{left}" y="{y + 18}" width="{validation_width:.1f}" height="14" fill="{ORANGE}"/>'
        )
        body.append(_text(left + train_width + 7, y + 12, f"{train:,}", size=11))
        body.append(_text(left + validation_width + 7, y + 30, f"{validation:,}", size=11))
    body.append(
        _text(
            35,
            height - 25,
            "Validation-only cohort; class support is not demographic evidence.",
            size=13,
            fill=GREY,
        )
    )
    return _svg(
        width,
        height,
        "Class support",
        "Log-scale training and validation support for eleven product classes.",
        body,
    )


def render_f1_delta() -> str:
    entries = _report("model-comparison")["comparison"]["per_class"]
    width, height = 1200, 600
    center, top, scale = 650, 85, 2500
    row_height = 42
    body = [_text(35, 40, "F3. Per-class MiniLM minus TF-IDF F1", size=24, font_weight="bold")]
    body.append(
        _text(
            35, 68, "Positive values favor MiniLM; orange marks the TF-IDF win", size=14, fill=GREY
        )
    )
    body.append(
        f'<line x1="{center}" y1="{top - 15}" x2="{center}" y2="{top + len(entries) * row_height}" stroke="{INK}"/>'
    )
    for index, entry in enumerate(entries):
        y = top + index * row_height
        delta = entry["delta_transformer_minus_baseline"]["f1"]
        bar_width = abs(delta) * scale
        x = center if delta >= 0 else center - bar_width
        color = BLUE if delta >= 0 else ORANGE
        body.append(
            _text(center - 25, y + 14, _short_label(entry["label"]), size=13, text_anchor="end")
        )
        body.append(
            f'<rect x="{x:.1f}" y="{y}" width="{bar_width:.1f}" height="18" fill="{color}"/>'
        )
        label_x = center + bar_width + 8 if delta >= 0 else center - bar_width - 8
        anchor = "start" if delta >= 0 else "end"
        body.append(_text(label_x, y + 14, f"{delta:+.4f}", size=12, text_anchor=anchor))
    body.append(
        _text(
            35,
            height - 22,
            "Validation-only differences; no inferential significance test was predeclared.",
            size=13,
            fill=GREY,
        )
    )
    return _svg(
        width,
        height,
        "Per-class F1 differences",
        "Zero-centered per-class validation F1 differences.",
        body,
    )


def render_reliability() -> str:
    evaluation = _report("calibration")["results"]["calibration_evaluation"]
    width, height = 820, 720
    left, top, size = 100, 90, 540
    body = [
        _text(
            35, 40, "F4. October reliability before and after scaling", size=24, font_weight="bold"
        )
    ]
    body.append(
        _text(35, 68, "Equal-width bins; empty bins are omitted from lines", size=14, fill=GREY)
    )
    for tick in range(0, 11, 2):
        value = tick / 10
        x = left + value * size
        y = top + size - value * size
        body.append(f'<line x1="{x}" y1="{top}" x2="{x}" y2="{top + size}" stroke="{LIGHT}"/>')
        body.append(f'<line x1="{left}" y1="{y}" x2="{left + size}" y2="{y}" stroke="{LIGHT}"/>')
        body.append(_text(x, top + size + 25, f"{value:.1f}", size=12, text_anchor="middle"))
        body.append(_text(left - 12, y + 4, f"{value:.1f}", size=12, text_anchor="end"))
    body.append(
        f'<line x1="{left}" y1="{top + size}" x2="{left + size}" y2="{top}" stroke="{GREY}" stroke-dasharray="6 5"/>'
    )
    for name, color in (("before", ORANGE), ("after", BLUE)):
        points = []
        for item in evaluation[name]["equal_width_reliability_bins"]:
            if item["record_count"]:
                x = left + item["mean_confidence"] * size
                y = top + size - item["accuracy"] * size
                points.append((x, y))
        body.append(
            f'<polyline points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in points)}" fill="none" stroke="{color}" stroke-width="3"/>'
        )
        for x, y in points:
            body.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{color}"/>')
    body.append(
        _text(left + size / 2, height - 35, "Mean confidence", size=14, text_anchor="middle")
    )
    body.append(
        _text(
            24,
            top + size / 2,
            "Observed accuracy",
            size=14,
            transform=f"rotate(-90 24 {top + size / 2})",
            text_anchor="middle",
        )
    )
    body.append(f'<line x1="670" y1="120" x2="700" y2="120" stroke="{ORANGE}" stroke-width="3"/>')
    body.append(_text(710, 125, "Before", size=13))
    body.append(f'<line x1="670" y1="150" x2="700" y2="150" stroke="{BLUE}" stroke-width="3"/>')
    body.append(_text(710, 155, "After", size=13))
    body.append(
        _text(
            35,
            height - 10,
            "Validation-only; lower ECE does not establish classwise calibration.",
            size=13,
            fill=GREY,
        )
    )
    return _svg(
        width,
        height,
        "October reliability",
        "Before and after temperature scaling reliability curves.",
        body,
    )


def render_risk_coverage() -> str:
    thresholds = _report("abstention")["thresholds"]
    width, height = 900, 650
    left, top, plot_w, plot_h = 100, 80, 650, 460
    x_min, x_max = 0.5, 1.0
    y_min, y_max = 0.88, 0.99
    body = [_text(35, 40, "F5. Coverage and selective accuracy", size=24, font_weight="bold")]
    body.append(
        _text(
            35,
            66,
            "X markers: ten ineligible candidates; grey circle: no-abstention reference",
            size=14,
            fill=GREY,
        )
    )
    body.append(
        f'<rect x="{left}" y="{top}" width="{plot_w}" height="{plot_h}" fill="none" stroke="{INK}"/>'
    )
    for entry in thresholds:
        coverage = entry["coverage"]
        accuracy = entry["selective_accuracy"]
        x = left + (coverage - x_min) / (x_max - x_min) * plot_w
        y = top + plot_h - (accuracy - y_min) / (y_max - y_min) * plot_h
        if entry["role"] == "candidate":
            body.append(
                f'<line x1="{x - 6:.1f}" y1="{y - 6:.1f}" x2="{x + 6:.1f}" y2="{y + 6:.1f}" stroke="{ORANGE}" stroke-width="3"/>'
            )
            body.append(
                f'<line x1="{x - 6:.1f}" y1="{y + 6:.1f}" x2="{x + 6:.1f}" y2="{y - 6:.1f}" stroke="{ORANGE}" stroke-width="3"/>'
            )
            point_label = f"{entry['threshold']:.2f}"
        else:
            body.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="{GREY}"/>')
            point_label = "reference"
        body.append(_text(x + 8, y - 8, point_label, size=11))
    for tick in range(5, 11):
        value = tick / 10
        x = left + (value - x_min) / (x_max - x_min) * plot_w
        body.append(_text(x, top + plot_h + 24, f"{value:.1f}", size=12, text_anchor="middle"))
    for value in (0.88, 0.90, 0.92, 0.94, 0.96, 0.98):
        y = top + plot_h - (value - y_min) / (y_max - y_min) * plot_h
        body.append(_text(left - 12, y + 4, f"{value:.2f}", size=12, text_anchor="end"))
        body.append(f'<line x1="{left}" y1="{y}" x2="{left + plot_w}" y2="{y}" stroke="{LIGHT}"/>')
    body.append(_text(left + plot_w / 2, height - 50, "Coverage", size=14, text_anchor="middle"))
    body.append(
        _text(
            24,
            top + plot_h / 2,
            "Selective accuracy",
            size=14,
            transform=f"rotate(-90 24 {top + plot_h / 2})",
            text_anchor="middle",
        )
    )
    body.append(
        _text(
            35,
            height - 14,
            "Validation-only: no threshold passed every global and class-aware gate.",
            size=13,
            fill=ORANGE,
        )
    )
    return _svg(
        width,
        height,
        "Risk coverage curve",
        "Coverage and selective accuracy for ten ineligible thresholds.",
        body,
    )


def render_qa_timeline() -> str:
    evidence = _load(QA_EVIDENCE_PATH)
    findings = _load(QA_FINDINGS_PATH)
    width, height = 1100, 350
    body = [
        _text(35, 40, "F6. Repository QA remediation and acceptance", size=24, font_weight="bold")
    ]
    stages = (
        (140, "Audit frozen", evidence["audit_date"], evidence["audited_commit"][:7]),
        (550, "13 findings resolved", "3 high / 7 medium / 3 low", "119 checks replayed"),
        (960, "Evidence accepted", evidence["accepted_date"], evidence["accepted_commit"][:7]),
    )
    body.append(
        f'<line x1="{stages[0][0]}" y1="160" x2="{stages[-1][0]}" y2="160" stroke="{NAVY}" stroke-width="4"/>'
    )
    for index, (x, label, detail, identifier) in enumerate(stages):
        color = TEAL if index == 2 else BLUE
        body.append(
            f'<circle cx="{x}" cy="160" r="18" fill="{color}" stroke="white" stroke-width="4"/>'
        )
        body.append(_text(x, 115, label, size=16, text_anchor="middle", font_weight="bold"))
        body.append(_text(x, 205, detail, size=14, text_anchor="middle"))
        body.append(_text(x, 230, identifier, size=13, text_anchor="middle", fill=GREY))
    body.append(
        _text(
            35,
            292,
            f"Accepted status: {findings['status']}; repository conclusion: {evidence['conclusion']}.",
            size=15,
        )
    )
    body.append(
        _text(
            35,
            322,
            "Software assurance increases evidence traceability; it does not prove model validity.",
            size=13,
            fill=GREY,
        )
    )
    return _svg(
        width,
        height,
        "QA remediation timeline",
        "Audit, remediation, and accepted evidence milestones.",
        body,
    )


def render_causal_dag() -> str:
    width, height = 1280, 670
    body = [
        _text(
            35,
            40,
            "F7. Prospective causal DAG for AI-assisted complaint triage",
            size=24,
            font_weight="bold",
        ),
        _text(
            35,
            68,
            "Design blueprint only; no causal effect has been estimated",
            size=14,
            fill=ORANGE,
        ),
        '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,6 L9,3 z" fill="#6B7280"/></marker></defs>',
    ]

    def node(
        x: int,
        y: int,
        label: str,
        detail: str,
        *,
        fill: str,
        stroke: str,
        width_: int = 210,
    ) -> None:
        body.append(
            f'<rect x="{x}" y="{y}" width="{width_}" height="78" rx="10" fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
        )
        body.append(
            _text(x + width_ / 2, y + 31, label, size=15, text_anchor="middle", font_weight="bold")
        )
        body.append(_text(x + width_ / 2, y + 56, detail, size=12, text_anchor="middle", fill=GREY))

    def arrow(x1: int, y1: int, x2: int, y2: int, *, dashed: bool = False) -> None:
        dash = ' stroke-dasharray="7 5"' if dashed else ""
        body.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{GREY}" stroke-width="2" marker-end="url(#arrow)"{dash}/>'
        )

    node(
        40,
        130,
        "Randomized assignment A",
        "manual-only vs suggestion",
        fill="#E8F4FA",
        stroke=BLUE,
        width_=230,
    )
    node(
        355,
        130,
        "Suggestion exposure S",
        "visible, missing, or failed",
        fill="#E8F4FA",
        stroke=BLUE,
        width_=230,
    )
    node(
        690,
        130,
        "Reviewer response M",
        "accept, correct, escalate",
        fill="#FFF4E6",
        stroke=ORANGE,
        width_=230,
    )
    node(
        1030,
        95,
        "Correct final route Y",
        "independent adjudication",
        fill="#E8F7F1",
        stroke=TEAL,
        width_=220,
    )
    node(
        1030,
        205,
        "Active review time T",
        "queue delay excluded",
        fill="#E8F7F1",
        stroke=TEAL,
        width_=220,
    )

    node(
        170,
        390,
        "Case factors C",
        "true route and complexity",
        fill="#F3F4F6",
        stroke=NAVY,
        width_=230,
    )
    node(
        525,
        390,
        "Reviewer factors E",
        "experience and workload",
        fill="#F3F4F6",
        stroke=NAVY,
        width_=230,
    )
    node(
        870,
        390,
        "Calendar/team block W",
        "case mix and queue context",
        fill="#F3F4F6",
        stroke=NAVY,
        width_=245,
    )

    arrow(270, 169, 355, 169)
    arrow(585, 169, 690, 169)
    arrow(920, 153, 1030, 134)
    arrow(920, 185, 1030, 237)
    arrow(400, 390, 440, 208)
    arrow(400, 429, 690, 208)
    arrow(400, 430, 1030, 144)
    arrow(755, 390, 790, 208)
    arrow(755, 430, 1030, 244)
    arrow(995, 390, 1080, 283)
    arrow(995, 390, 1135, 173)
    arrow(930, 390, 270, 208, dashed=True)

    body.append(_text(35, 535, "Interpretation", size=17, font_weight="bold"))
    body.append(
        _text(
            35,
            565,
            "Solid arrows are hypothesized causal paths; the dashed arrow marks stratified assignment by calendar/team block.",
            size=14,
        )
    )
    body.append(
        _text(
            35,
            594,
            "M is post-assignment: do not adjust for acceptance or override in the primary intention-to-treat total-effect analysis.",
            size=14,
            fill=ORANGE,
        )
    )
    body.append(
        _text(
            35,
            623,
            "Randomization addresses assignment confounding in expectation; interference, attrition, and outcome validity still require design controls.",
            size=14,
            fill=GREY,
        )
    )

    return _svg(
        width,
        height,
        "Prospective causal DAG for AI-assisted complaint triage",
        "Randomized suggestion access affects reviewer response, route correctness, and review time, with baseline case, reviewer, and calendar factors shown explicitly.",
        body,
    )


def render_figures() -> dict[str, str]:
    return {
        "f1-governed-pipeline.svg": render_pipeline(),
        "f2-class-support.svg": render_class_support(),
        "f3-per-class-f1-delta.svg": render_f1_delta(),
        "f4-october-reliability.svg": render_reliability(),
        "f5-risk-coverage.svg": render_risk_coverage(),
        "f6-qa-timeline.svg": render_qa_timeline(),
        "f7-causal-dag.svg": render_causal_dag(),
    }
