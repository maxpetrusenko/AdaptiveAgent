"""Static HTML reports for benchmark JSON artifacts."""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import json
from html import escape
from pathlib import Path
from typing import Any


def _pct(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    return f"{float(value) * 100:.1f}%"


def _num(value: float | int | None, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.{digits}f}"


def _card(title: str, value: str, subtitle: str = "") -> str:
    subtitle_html = f"<div class='subtitle'>{escape(subtitle)}</div>" if subtitle else ""
    return (
        "<section class='card'>"
        f"<div class='label'>{escape(title)}</div>"
        f"<div class='value'>{escape(value)}</div>"
        f"{subtitle_html}"
        "</section>"
    )


def _table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{escape(header)}</th>" for header in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _bar_chart(
    title: str,
    labels: list[str],
    values: list[float],
    *,
    height: int = 220,
    percent: bool = True,
) -> str:
    if not labels:
        return ""

    width = 760
    margin_left = 120
    margin_right = 24
    margin_top = 28
    margin_bottom = 42
    chart_width = width - margin_left - margin_right
    chart_height = height - margin_top - margin_bottom
    max_value = max(max(values), 1.0 if percent else 1.0)
    bar_gap = 12
    bar_height = max(18, (chart_height - bar_gap * (len(labels) - 1)) / max(len(labels), 1))

    bars: list[str] = []
    for idx, (label, value) in enumerate(zip(labels, values, strict=True)):
        y = margin_top + idx * (bar_height + bar_gap)
        bar_width = 0 if max_value == 0 else chart_width * (value / max_value)
        label_text = _pct(value) if percent else _num(value)
        bars.append(
            f"<text x='12' y='{y + bar_height * 0.72:.1f}' class='axis-label'>{escape(label)}</text>"
            f"<rect x='{margin_left}' y='{y:.1f}' width='{bar_width:.1f}' height='{bar_height:.1f}' rx='8' class='bar'/>"
            f"<text x='{margin_left + bar_width + 8:.1f}' y='{y + bar_height * 0.72:.1f}' class='bar-value'>{escape(label_text)}</text>"
        )

    return (
        "<section class='panel'>"
        f"<h2>{escape(title)}</h2>"
        f"<svg viewBox='0 0 {width} {height}' class='chart'>" + "".join(bars) + "</svg></section>"
    )


def _line_chart(
    title: str,
    labels: list[str],
    values: list[float],
    *,
    height: int = 260,
    percent: bool = True,
) -> str:
    if not labels or not values:
        return ""

    width = 760
    margin_left = 52
    margin_right = 20
    margin_top = 20
    margin_bottom = 44
    chart_width = width - margin_left - margin_right
    chart_height = height - margin_top - margin_bottom
    max_value = max(max(values), 1.0 if percent else 1.0)
    step_x = chart_width / max(len(values) - 1, 1)

    points: list[tuple[float, float]] = []
    for idx, value in enumerate(values):
        x = margin_left + idx * step_x
        y = (
            margin_top
            + chart_height
            - (0 if max_value == 0 else chart_height * (value / max_value))
        )
        points.append((x, y))

    path = " ".join(
        (f"M {x:.1f} {y:.1f}" if idx == 0 else f"L {x:.1f} {y:.1f}")
        for idx, (x, y) in enumerate(points)
    )
    dots = "".join(
        f"<circle cx='{x:.1f}' cy='{y:.1f}' r='5' class='dot'/>"
        f"<text x='{x:.1f}' y='{y - 10:.1f}' text-anchor='middle' class='bar-value'>{escape(_pct(values[idx]) if percent else _num(values[idx]))}</text>"
        f"<text x='{x:.1f}' y='{height - 14:.1f}' text-anchor='middle' class='axis-label'>{escape(labels[idx])}</text>"
        for idx, (x, y) in enumerate(points)
    )
    grid = "".join(
        f"<line x1='{margin_left}' y1='{margin_top + chart_height * frac:.1f}' x2='{width - margin_right}' y2='{margin_top + chart_height * frac:.1f}' class='grid'/>"
        for frac in (0, 0.25, 0.5, 0.75, 1)
    )
    return (
        "<section class='panel'>"
        f"<h2>{escape(title)}</h2>"
        f"<svg viewBox='0 0 {width} {height}' class='chart'>"
        f"{grid}<path d='{path}' class='line'/>"
        f"{dots}</svg></section>"
    )


def _render_compare_report(name: str, report: dict[str, Any]) -> str:
    leaderboard = report.get("leaderboard") or sorted(
        report.get("systems", []),
        key=lambda item: (-item.get("pass_rate_mean", 0.0), item.get("avg_latency_ms_mean", 0.0)),
    )
    labels = [item["system"] for item in leaderboard]
    values = [float(item.get("pass_rate_mean", 0.0)) for item in leaderboard]
    pairwise = report.get("pairwise", {})
    pair_labels = list(pairwise.keys())
    pair_values = [float(pairwise[name].get("pass_rate_delta_mean", 0.0)) for name in pair_labels]

    trajectory_summary = report.get("trajectory", {}).get("summary", {})
    initial_pass = float(trajectory_summary.get("initial", {}).get("pass_rate", 0.0))
    cycles = trajectory_summary.get("cycles", [])
    trajectory_labels = ["initial", *[f"cycle {cycle['cycle']}" for cycle in cycles]]
    trajectory_values = [
        initial_pass,
        *[float(cycle["eval_pass_rate"]["mean"]) for cycle in cycles],
    ]

    cards = [
        _card("systems", str(len(leaderboard))),
        _card("train cases", str(report.get("config", {}).get("train_case_count", 0))),
        _card("eval cases", str(report.get("config", {}).get("eval_case_count", 0))),
        _card(
            "adaptive final",
            _pct(
                next(
                    (
                        item.get("pass_rate_mean")
                        for item in leaderboard
                        if item["system"] == "adaptive_agent"
                    ),
                    0.0,
                )
            ),
        ),
    ]

    leader_rows = [
        [
            escape(str(idx + 1)),
            escape(item["system"]),
            escape(_pct(item.get("pass_rate_mean"))),
            escape(_num(item.get("avg_latency_ms_mean"), 0)),
            escape(_num(item.get("hallucination_failures_mean", 0.0), 1)),
        ]
        for idx, item in enumerate(leaderboard)
    ]
    pair_rows = [
        [
            escape(name),
            escape(_pct(delta.get("pass_rate_delta_mean"))),
            escape(str(delta.get("wins", 0))),
            escape(str(delta.get("losses", 0))),
            escape(str(delta.get("ties", 0))),
            escape(_num(delta.get("sign_test", {}).get("p_value"), 3)),
        ]
        for name, delta in pairwise.items()
    ]

    judge = report.get("judge_calibration") or {}
    hardening = (report.get("hardening") or {}).get("hardening_checks", {})
    extra = []
    if judge:
        extra.append(
            _table(
                ["judge", "accuracy", "precision", "recall", "support"],
                [
                    [
                        "pass/fail",
                        _num(judge.get("pass_fail", {}).get("accuracy")),
                        _num(judge.get("pass_fail", {}).get("precision")),
                        _num(judge.get("pass_fail", {}).get("recall")),
                        str(judge.get("pass_fail", {}).get("support", judge.get("case_count", 0))),
                    ],
                    [
                        "hallucination",
                        _num(judge.get("hallucination", {}).get("accuracy")),
                        _num(judge.get("hallucination", {}).get("precision")),
                        _num(judge.get("hallucination", {}).get("recall")),
                        str(
                            judge.get("hallucination", {}).get(
                                "support", judge.get("case_count", 0)
                            )
                        ),
                    ],
                ],
            )
        )
    if hardening:
        extra.append(
            _table(
                ["check", "observed", "status"],
                [
                    [
                        "null_agent",
                        _pct(hardening.get("null_agent", {}).get("observed_pass_rate")),
                        "sound" if hardening.get("null_agent", {}).get("sound") else "failed",
                    ],
                    [
                        "judge_bias_agent",
                        _pct(hardening.get("judge_bias_agent", {}).get("observed_pass_rate")),
                        "sound"
                        if hardening.get("judge_bias_agent", {}).get("sound")
                        else "compromisable",
                    ],
                    [
                        "evaluator_isolation",
                        "shared process"
                        if hardening.get("evaluator_isolation", {}).get(
                            "agent_and_evaluator_share_process"
                        )
                        else "isolated",
                        "documented",
                    ],
                ],
            )
        )

    return _page(
        title=f"{name} • comparative benchmark",
        summary="Comparative benchmark with adaptive trajectory, pairwise deltas, judge calibration, and hardening checks.",
        cards="".join(cards),
        sections="".join(
            [
                _bar_chart("Leaderboard pass rate", labels, values),
                _bar_chart("Adaptive pairwise delta", pair_labels, pair_values),
                _line_chart("Adaptive trajectory", trajectory_labels, trajectory_values),
                _table(
                    ["rank", "system", "pass rate", "latency ms", "hallucinations"],
                    leader_rows,
                ),
                _table(
                    ["baseline", "delta", "wins", "losses", "ties", "sign test p"],
                    pair_rows,
                )
                if pair_rows
                else "",
                *extra,
            ]
        ),
    )


def _render_run_report(name: str, report: dict[str, Any]) -> str:
    baseline = report.get("baseline", {})
    post = report.get("post_adaptation", {})
    adaptation = report.get("adaptation", {})
    baseline_runs = baseline.get("runs", [])
    post_runs = post.get("runs", [])
    run_labels = [f"baseline {idx + 1}" for idx in range(len(baseline_runs))] + [
        f"post {idx + 1}" for idx in range(len(post_runs))
    ]
    run_values = [float(run.get("pass_rate", 0.0)) for run in baseline_runs] + [
        float(run.get("pass_rate", 0.0)) for run in post_runs
    ]

    cards = [
        _card(
            "baseline mean",
            _pct(baseline.get("mean_pass_rate")),
            f"std {_pct(baseline.get('std_pass_rate'))}",
        ),
        _card(
            "post mean", _pct(post.get("mean_pass_rate")), f"std {_pct(post.get('std_pass_rate'))}"
        ),
        _card("delta", _pct(report.get("delta", {}).get("mean_pass_rate_delta"))),
        _card(
            "accepted",
            "yes" if adaptation.get("accepted") else "no",
            f"prompt {report.get('baseline_prompt_version')} → {report.get('final_prompt_version')}",
        ),
    ]
    rows = [
        [
            escape("baseline"),
            escape(run.get("run_id", "")),
            escape(_pct(run.get("pass_rate"))),
            escape(str(run.get("hallucination_failures", 0))),
            escape(str(run.get("protected_failures", 0))),
        ]
        for run in baseline_runs
    ] + [
        [
            escape("post"),
            escape(run.get("run_id", "")),
            escape(_pct(run.get("pass_rate"))),
            escape(str(run.get("hallucination_failures", 0))),
            escape(str(run.get("protected_failures", 0))),
        ]
        for run in post_runs
    ]
    return _page(
        title=f"{name} • adaptation benchmark",
        summary="Before/after adaptation benchmark with repeated eval runs.",
        cards="".join(cards),
        sections="".join(
            [
                _bar_chart(
                    "Mean pass rate",
                    ["baseline", "post"],
                    [
                        float(baseline.get("mean_pass_rate", 0.0)),
                        float(post.get("mean_pass_rate", 0.0)),
                    ],
                ),
                _line_chart("Per run pass rate", run_labels, run_values),
                _table(
                    ["phase", "run id", "pass rate", "hallucinations", "protected failures"],
                    rows,
                ),
            ]
        ),
    )


def _render_judge_report(name: str, report: dict[str, Any]) -> str:
    cards = [
        _card("cases", str(report.get("case_count", 0))),
        _card("pass/fail accuracy", _num(report.get("pass_fail", {}).get("accuracy"))),
        _card("hallucination accuracy", _num(report.get("hallucination", {}).get("accuracy"))),
        _card("case accuracy", _num(report.get("case_accuracy"))),
    ]
    return _page(
        title=f"{name} • judge calibration",
        summary="Human-labeled calibration set for pass/fail and hallucination judges.",
        cards="".join(cards),
        sections=_table(
            ["judge", "accuracy", "precision", "recall", "support"],
            [
                [
                    "pass/fail",
                    _num(report.get("pass_fail", {}).get("accuracy")),
                    _num(report.get("pass_fail", {}).get("precision")),
                    _num(report.get("pass_fail", {}).get("recall")),
                    str(report.get("pass_fail", {}).get("support", 0)),
                ],
                [
                    "hallucination",
                    _num(report.get("hallucination", {}).get("accuracy")),
                    _num(report.get("hallucination", {}).get("precision")),
                    _num(report.get("hallucination", {}).get("recall")),
                    str(report.get("hallucination", {}).get("support", 0)),
                ],
            ],
        ),
    )


def _render_adversarial_report(name: str, report: dict[str, Any]) -> str:
    checks = report.get("hardening_checks", {})
    cards = [
        _card("cases", str(report.get("suite", {}).get("case_count", 0))),
        _card("null agent", _pct(checks.get("null_agent", {}).get("observed_pass_rate"))),
        _card("judge bias", _pct(checks.get("judge_bias_agent", {}).get("observed_pass_rate"))),
        _card(
            "comparison",
            _pct(checks.get("comparison", {}).get("bias_minus_null")),
            "bias minus null",
        ),
    ]
    return _page(
        title=f"{name} • adversarial benchmark",
        summary="Harness soundness checks for null outputs and judge-bias prompt injection.",
        cards="".join(cards),
        sections="".join(
            [
                _bar_chart(
                    "Adversarial pass rates",
                    ["null_agent", "judge_bias_agent"],
                    [
                        float(checks.get("null_agent", {}).get("observed_pass_rate", 0.0)),
                        float(checks.get("judge_bias_agent", {}).get("observed_pass_rate", 0.0)),
                    ],
                ),
                _table(
                    ["check", "observed", "status"],
                    [
                        [
                            "null_agent",
                            _pct(checks.get("null_agent", {}).get("observed_pass_rate")),
                            "sound" if checks.get("null_agent", {}).get("sound") else "failed",
                        ],
                        [
                            "judge_bias_agent",
                            _pct(checks.get("judge_bias_agent", {}).get("observed_pass_rate")),
                            "sound"
                            if checks.get("judge_bias_agent", {}).get("sound")
                            else "compromisable",
                        ],
                    ],
                ),
            ]
        ),
    )


def _page(*, title: str, summary: str, cards: str, sections: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    :root {{
      --bg: #f3efe7;
      --panel: #fffaf2;
      --ink: #1f1b16;
      --muted: #6b6257;
      --accent: #b04a1f;
      --accent-soft: #f0d3c2;
      --grid: #d8c9bb;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Georgia, "Iowan Old Style", serif;
      background:
        radial-gradient(circle at top left, rgba(176,74,31,0.14), transparent 28%),
        linear-gradient(180deg, #f8f2ea, var(--bg));
      color: var(--ink);
    }}
    .wrap {{ max-width: 1120px; margin: 0 auto; padding: 40px 24px 80px; }}
    h1, h2 {{ margin: 0; font-weight: 600; }}
    h1 {{ font-size: 40px; line-height: 1.05; letter-spacing: -0.03em; }}
    h2 {{ font-size: 22px; margin-bottom: 16px; }}
    p {{ color: var(--muted); font-size: 17px; line-height: 1.5; }}
    .hero {{ display: grid; gap: 14px; margin-bottom: 28px; }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 14px;
      margin: 28px 0 34px;
    }}
    .card, .panel {{
      background: color-mix(in srgb, var(--panel) 92%, white 8%);
      border: 1px solid rgba(31,27,22,0.08);
      border-radius: 18px;
      box-shadow: 0 12px 36px rgba(58, 44, 33, 0.08);
    }}
    .card {{ padding: 18px; }}
    .panel {{ padding: 18px 18px 10px; margin-bottom: 18px; }}
    .label {{ text-transform: uppercase; letter-spacing: 0.12em; font-size: 11px; color: var(--muted); }}
    .value {{ font-size: 34px; margin-top: 10px; }}
    .subtitle {{ margin-top: 6px; color: var(--muted); font-size: 13px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    th, td {{ text-align: left; padding: 11px 10px; border-top: 1px solid rgba(31,27,22,0.08); }}
    th {{ font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); border-top: 0; }}
    .chart {{ width: 100%; height: auto; display: block; }}
    .bar {{ fill: var(--accent); opacity: 0.86; }}
    .bar-value {{ fill: var(--ink); font-size: 12px; }}
    .axis-label {{ fill: var(--muted); font-size: 12px; }}
    .grid {{ stroke: var(--grid); stroke-width: 1; }}
    .line {{ fill: none; stroke: var(--accent); stroke-width: 4; stroke-linecap: round; stroke-linejoin: round; }}
    .dot {{ fill: var(--accent); }}
    .footer {{ margin-top: 30px; color: var(--muted); font-size: 13px; }}
    a {{ color: var(--accent); }}
  </style>
</head>
<body>
  <main class="wrap">
    <header class="hero">
      <h1>{escape(title)}</h1>
      <p>{escape(summary)}</p>
    </header>
    <section class="cards">{cards}</section>
    {sections}
    <div class="footer">Generated from benchmark JSON.</div>
  </main>
</body>
</html>
"""


def render_report(name: str, report: dict[str, Any]) -> str:
    if "baseline" in report and "post_adaptation" in report:
        return _render_run_report(name, report)
    if "leaderboard" in report or ("systems" in report and "pairwise" in report):
        return _render_compare_report(name, report)
    if "hardening_checks" in report and "systems" in report:
        return _render_adversarial_report(name, report)
    if "pass_fail" in report and "hallucination" in report:
        return _render_judge_report(name, report)
    return _page(
        title=f"{name} • raw benchmark",
        summary="Unknown benchmark schema. Raw JSON shown below.",
        cards="",
        sections=f"<section class='panel'><pre>{escape(json.dumps(report, indent=2))}</pre></section>",
    )


def render_report_file(json_path: Path) -> Path:
    report = json.loads(json_path.read_text(encoding="utf-8"))
    html = render_report(json_path.stem, report)
    html_path = json_path.with_suffix(".html")
    html_path.write_text(html, encoding="utf-8")
    return html_path


def render_report_directory(directory: Path) -> list[Path]:
    html_paths = [render_report_file(path) for path in sorted(directory.glob("*.json"))]
    rows = [
        [
            f"<a href='{escape(path.name)}'>{escape(path.name)}</a>",
            escape(path.with_suffix(".json").name),
        ]
        for path in html_paths
    ]
    index_html = _page(
        title="Benchmark Reports",
        summary="Static HTML views for every benchmark JSON artifact in this directory.",
        cards=_card("reports", str(len(html_paths))),
        sections=_table(["html", "source json"], rows),
    )
    index_path = directory / "index.html"
    index_path.write_text(index_html, encoding="utf-8")
    return [*html_paths, index_path]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render benchmark JSON artifacts to HTML")
    parser.add_argument(
        "--dir",
        type=Path,
        default=Path("benchmark-results"),
        help="Directory containing benchmark JSON files",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Render one benchmark JSON file instead of the whole directory",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.input is not None:
        output = render_report_file(args.input)
        print(output)
        return 0

    outputs = render_report_directory(args.dir)
    for output in outputs:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
