"""
Comparison tables from the benchmark results of two versions.

Reads ``RESULTS/v3.0.1/*.json`` and ``RESULTS/head/*.json`` written by
``micro.py`` and ``RESULTS/e2e.json`` written by ``e2e.py``, and prints
Markdown tables with the ratio of the current tree to the baseline.
Regressions beyond ``--threshold`` and per-attempt costs above
``--attempt-cost`` microseconds are flagged.
"""

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

FAMILIES = ["draw", "shrink", "attempts", "fork", "memory", "probe"]


def _load(results: Path, label: str) -> dict[str, dict[str, dict[str, Any]]]:
    """Results by family and case name for one version."""
    loaded: dict[str, dict[str, dict[str, Any]]] = {}
    for family in FAMILIES:
        path = results / label / f"{family}.json"
        if not path.exists():
            continue
        payload = json.loads(path.read_text())
        loaded[family] = {r["name"]: r for r in payload["results"]}
    return loaded


def _fmt(value: float, metric: str) -> str:
    if metric == "per_second":
        return f"{value:,.0f}"
    if metric == "seconds":
        return f"{value * 1e6:,.0f} us"
    if metric == "nanoseconds":
        return f"{value:,.0f} ns"
    if metric == "kibibytes":
        return f"{value:,.0f} KiB"
    if metric in ("frames", "children"):
        return f"{value:.0f}"
    return f"{value:.3g}"


def _flag(ratio: float, better: str, threshold: float) -> str:
    worse = (
        ratio < 1 - threshold if better == "higher" else ratio > 1 + threshold
    )
    improved = (
        ratio > 1 + threshold if better == "higher" else ratio < 1 - threshold
    )
    if worse:
        return "REGRESSION"
    if improved:
        return "improved"
    return ""


def _family_table(
    family: str,
    baseline: dict[str, dict[str, Any]],
    head: dict[str, dict[str, Any]],
    threshold: float,
    attempt_cost: float,
) -> list[str]:
    lines = [
        f"### {family}",
        "",
        "| case | metric | v3.0.1 | HEAD | HEAD/v3.0.1 | note |",
        "|---|---|---:|---:|---:|---|",
    ]
    for name in head:
        h = head[name]
        b = baseline.get(name)
        if b is None:
            lines.append(
                f"| {name} | {h['metric']} | n/a | "
                f"{_fmt(h['value'], h['metric'])} | | |"
            )
            continue
        if "error" in b["details"] or "error" in h["details"]:
            lines.append(
                f"| {name} | {h['metric']} | "
                f"{b['details'].get('error') or _fmt(b['value'], b['metric'])}"
                f" | {h['details'].get('error') or _fmt(h['value'], h['metric'])}"
                " | | |"
            )
            continue
        ratio = h["value"] / b["value"] if b["value"] else float("inf")
        note = _flag(ratio, h["better"], threshold)
        if family == "attempts":
            cost = h["details"]["microseconds_per_attempt"]
            if cost > attempt_cost:
                note = f"{note} {cost:.1f} us/attempt".strip()
        if family == "draw" and "mean_children" in h["details"]:
            note = (
                f"{note} children/draw v3 "
                f"{b['details'].get('mean_children', 0):.1f}, "
                f"HEAD {h['details']['mean_children']:.1f}"
            ).strip()
        lines.append(
            f"| {name} | {h['metric']} | {_fmt(b['value'], b['metric'])} | "
            f"{_fmt(h['value'], h['metric'])} | {ratio:.2f} | {note} |"
        )
    lines.append("")
    if family == "shrink":
        lines += [
            "| case | start | v3.0.1 reached | v3.0.1 evals | "
            "HEAD reached | HEAD evals | HEAD us/eval |",
            "|---|---|---|---:|---|---:|---:|",
        ]
        for name in head:
            h = head[name]["details"]
            b = baseline.get(name, {}).get("details", {})
            lines.append(
                f"| {name} | {h['start']} | {b.get('reached', 'n/a')} | "
                f"{b.get('evaluations', 'n/a')} | {h['reached']} | "
                f"{h['evaluations']} | "
                f"{h['microseconds_per_evaluation']:.1f} |"
            )
        lines.append("")
    return lines


def _e2e_tables(path: Path) -> list[str]:
    payload = json.loads(path.read_text())
    runs = payload["runs"]
    lines = [
        "### end to end",
        "",
        f"Budget {payload['budget']} s, seed {payload['seed']}.",
        "",
        "| version | suite | properties | total attempts | min | median | "
        "max | at limit | wall s | reported s |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for run in runs:
        attempts = [p["attempts"] for p in run["properties"]]
        at_limit = sum(
            1
            for p in run["properties"]
            if p["attempt_limit"] is not None
            and p["attempts"] >= p["attempt_limit"]
        )
        lines.append(
            f"| {run['label']} | {run['suite']} | {len(attempts)} | "
            f"{sum(attempts):,} | {min(attempts)} | "
            f"{statistics.median(attempts):.0f} | {max(attempts)} | "
            f"{at_limit} | {run['wall_seconds']:.1f} | "
            f"{run['reported_total']:.1f} |"
        )
    lines.append("")
    by_key = {(r["label"], r["suite"]): r for r in runs}
    base = by_key.get(("v3.0.1", "synthetic"))
    head = by_key.get(("head", "synthetic"))
    if base is not None and head is not None:
        lines += [
            "Synthetic suite, attempts per property:",
            "",
            "| property | limit | v3.0.1 | HEAD | HEAD/v3.0.1 |",
            "|---|---:|---:|---:|---:|",
        ]
        base_by_name = {p["name"]: p for p in base["properties"]}
        for p in head["properties"]:
            b = base_by_name.get(p["name"])
            if b is None:
                continue
            ratio = p["attempts"] / b["attempts"] if b["attempts"] else 0.0
            lines.append(
                f"| {p['name']} | {p['attempt_limit']} | {b['attempts']} | "
                f"{p['attempts']} | {ratio:.2f} |"
            )
        lines.append("")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--threshold", type=float, default=0.20)
    parser.add_argument("--attempt-cost", type=float, default=50.0)
    args = parser.parse_args()
    baseline = _load(args.results, "v3.0.1")
    head = _load(args.results, "head")
    lines: list[str] = []
    for family in FAMILIES:
        if family in head:
            lines += _family_table(
                family,
                baseline.get(family, {}),
                head[family],
                args.threshold,
                args.attempt_cost,
            )
    e2e = args.results / "e2e.json"
    if e2e.exists():
        lines += _e2e_tables(e2e)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
