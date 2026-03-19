"""
eval_compare_modes.py – Run all 4 retrieval modes across all 3 datasets
and produce a side-by-side comparison Markdown report.

Modes compared
--------------
  bm25        – Basic BM25 retrieval only
  bm25+kg     – BM25 + Knowledge-Graph query expansion
  bm25+ce     – BM25 + Cross-encoder reranking
  bm25+kg+ce  – BM25 + KG expansion + Cross-encoder reranking

Usage
-----
    # All 3 datasets, 25 questions each
    python eval_compare_modes.py

    # Specific dataset only
    python eval_compare_modes.py --dataset pubmedqa

    # Fewer questions (faster)
    python eval_compare_modes.py --n 10

    # ArchEHR needs local CSV path
    python eval_compare_modes.py --archehr-csv-path data/archehr_qa

    # Skip a mode
    python eval_compare_modes.py --skip-modes bm25+kg,bm25+kg+ce
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent

MODES = ["bm25", "bm25+kg", "bm25+ce", "bm25+kg+ce"]

DATASETS = [
    {"name": "pubmedqa",   "csv_path": None},
    {"name": "medquad",    "csv_path": None},
    {"name": "archehr_qa", "csv_path": None},
]

MODE_LABELS = {
    "bm25":       "Basic BM25",
    "bm25+kg":    "BM25 + KG",
    "bm25+ce":    "BM25 + CE",
    "bm25+kg+ce": "BM25 + KG + CE",
}


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Compare 4 retrieval modes across datasets")
    p.add_argument("--n",    type=int, default=25, help="Questions per run (default: 25)")
    p.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    p.add_argument(
        "--dataset",
        default=None,
        choices=["pubmedqa", "medquad", "archehr_qa"],
        help="Run only this dataset (default: all three)",
    )
    p.add_argument(
        "--archehr-csv-path",
        default=None,
        help="Local CSV path for ArchEHR-QA (required if --dataset includes archehr_qa)",
    )
    p.add_argument(
        "--medquad-csv-path",
        default=None,
        help="Local CSV path for MedQuAD (optional)",
    )
    p.add_argument(
        "--skip-modes",
        default="",
        help="Comma-separated modes to skip, e.g. 'bm25+kg,bm25+kg+ce'",
    )
    p.add_argument(
        "--output",
        default="retriever_mode_comparison.md",
        help="Output comparison report filename (default: retriever_mode_comparison.md)",
    )
    return p.parse_args()


def _run_eval(dataset: str, mode: str, n: int, seed: int, csv_path: str | None) -> dict | None:
    """Invoke eval_harness.py for one (dataset, mode) pair. Returns parsed summary or None."""
    mode_slug = mode.replace("+", "_")
    report_file = HERE / f"{dataset}_{mode_slug}_eval_report.md"

    cmd = [
        sys.executable, str(HERE / "eval_harness.py"),
        "--dataset", dataset,
        "--mode",    mode,
        "--n",       str(n),
        "--seed",    str(seed),
        "--output",  str(report_file),
    ]
    if csv_path:
        cmd += ["--csv-path", csv_path]

    print(f"  Running: {dataset} / {mode} ...", flush=True)
    t0 = time.perf_counter()
    result = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = time.perf_counter() - t0

    if result.returncode != 0:
        print(f"  ERROR ({dataset}/{mode}):\n{result.stderr[-800:]}")
        return None

    print(f"  Done in {elapsed:.0f}s -> {report_file.name}")
    return _parse_report(report_file)


def _parse_report(path: Path) -> dict | None:
    """Extract summary metrics from a Markdown report file."""
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")

    def _grab(label: str) -> str | None:
        m = re.search(rf"\|\s*{re.escape(label)}\s*\|\s*([^\|]+)\s*\|", text)
        return m.group(1).strip() if m else None

    def _flt(s: str | None) -> float | None:
        if s is None:
            return None
        try:
            return float(s.rstrip("%")) / (100 if "%" in s else 1)
        except (TypeError, ValueError):
            return None

    n_q_m = re.search(r"Questions evaluated:\*\*\s*(\d+)", text)
    n_questions = int(n_q_m.group(1)) if n_q_m else None

    return {
        "faithfulness":     _flt(_grab("Faithfulness (mean)")),
        "answer_relevancy": _flt(_grab("Answer Relevancy (mean)")),
        "factuality":       _flt(_grab("Factuality (mean)")),
        "safety_rate":      _flt(_grab("Safety Rate")),
        "mean_latency":     _flt(_grab("Mean Latency (s)")),
        "corrections":      _grab("Corrections Applied"),
        "n_questions":      n_questions,
        "report_file":      path.name,
    }


def _fmt(v: float | None, pct: bool = False) -> str:
    if v is None:
        return "N/A"
    if pct:
        return f"{v * 100:.1f}%"
    return f"{v:.3f}"


def _winner_marker(values: list[float | None]) -> list[str]:
    """Return a marker for each value: '**' if best, '' otherwise."""
    clean = [(i, v) for i, v in enumerate(values) if v is not None]
    if not clean:
        return [""] * len(values)
    best_i, best_v = max(clean, key=lambda x: x[1])
    return ["**" if i == best_i else "" for i in range(len(values))]


def _build_comparison_report(
    results: dict[tuple[str, str], dict | None],
    datasets: list[str],
    modes: list[str],
    n: int,
    seed: int,
    date_str: str,
) -> str:
    lines: list[str] = [
        "# Retrieval Mode Comparison Report",
        "",
        f"**Questions per run:** {n}  |  **Seed:** {seed}  |  **Date:** {date_str}",
        "",
        "## Modes Compared",
        "",
        "| Mode | Description |",
        "|------|-------------|",
        "| `bm25` | Basic BM25 keyword retrieval only |",
        "| `bm25+kg` | BM25 + Knowledge Graph query expansion (SciSpacy NER + co-occurrence) |",
        "| `bm25+ce` | BM25 + Cross-encoder reranking (ms-marco-MiniLM-L-6-v2) |",
        "| `bm25+kg+ce` | BM25 + KG expansion + Cross-encoder reranking (full pipeline) |",
        "",
    ]

    for dataset in datasets:
        lines += [
            f"---",
            "",
            f"## Dataset: `{dataset}`",
            "",
        ]

        # Header row
        mode_headers = "  |  ".join(f"**{MODE_LABELS[m]}**" for m in modes)
        lines += [
            f"| Metric | {mode_headers} |",
            "|--------|" + "------|" * len(modes),
        ]

        metrics = [
            ("Faithfulness", "faithfulness", False),
            ("Answer Relevancy", "answer_relevancy", False),
            ("Factuality", "factuality", False),
            ("Safety Rate", "safety_rate", True),
            ("Mean Latency (s)", "mean_latency", False),
            ("Corrections", "corrections", None),
        ]

        for label, key, pct in metrics:
            row_vals = [results.get((dataset, m), {}) or {} for m in modes]
            if pct is None:
                cells = [rv.get(key, "N/A") or "N/A" for rv in row_vals]
                lines.append(f"| {label} | " + " | ".join(str(c) for c in cells) + " |")
            else:
                raw_vals = [rv.get(key) for rv in row_vals]
                markers = _winner_marker(raw_vals)
                cells = [f"{markers[i]}{_fmt(v, pct=pct)}{markers[i]}"
                         for i, v in enumerate(raw_vals)]
                lines.append(f"| {label} | " + " | ".join(cells) + " |")

        lines.append("")

        # Per-metric winner summary
        lines += ["### Winner by Metric", ""]
        for label, key, pct in metrics:
            if pct is None:
                continue
            raw_vals = [(m, (results.get((dataset, m), {}) or {}).get(key)) for m in modes]
            valid = [(m, v) for m, v in raw_vals if v is not None]
            if not valid:
                continue
            best_mode, best_val = max(valid, key=lambda x: x[1])
            lines.append(f"- **{label}**: `{best_mode}` ({_fmt(best_val, pct=pct)})")
        lines.append("")

        # Delta table: improvement over baseline BM25
        if "bm25" in modes:
            lines += ["### Delta vs Baseline BM25", ""]
            delta_metrics = [
                ("Faithfulness", "faithfulness"),
                ("Answer Relevancy", "answer_relevancy"),
                ("Factuality", "factuality"),
            ]
            baseline = results.get((dataset, "bm25"), {}) or {}
            non_bm25 = [m for m in modes if m != "bm25"]
            if non_bm25:
                header_cols = " | ".join(f"`{m}`" for m in non_bm25)
                lines += [
                    f"| Metric | {header_cols} |",
                    "|--------|" + "------|" * len(non_bm25),
                ]
                for label, key in delta_metrics:
                    bl_v = baseline.get(key)
                    cells = []
                    for m in non_bm25:
                        v = (results.get((dataset, m), {}) or {}).get(key)
                        if bl_v is None or v is None:
                            cells.append("N/A")
                        else:
                            delta = v - bl_v
                            sign = "+" if delta >= 0 else ""
                            cells.append(f"{sign}{delta:.3f}")
                    lines.append(f"| {label} | " + " | ".join(cells) + " |")
                lines.append("")

    # Overall cross-dataset summary
    lines += [
        "---",
        "",
        "## Overall Cross-Dataset Summary",
        "",
        "Average across all datasets per mode:",
        "",
        "| Mode | Avg Faithfulness | Avg Answer Relevancy | Avg Factuality | Avg Safety Rate |",
        "|------|-----------------|---------------------|----------------|-----------------|",
    ]

    for mode in modes:
        vals: dict[str, list[float]] = {
            "faithfulness": [], "answer_relevancy": [], "factuality": [], "safety_rate": []
        }
        for dataset in datasets:
            r = results.get((dataset, mode), {}) or {}
            for k in vals:
                v = r.get(k)
                if v is not None:
                    vals[k].append(v)

        def _avg(lst: list[float]) -> float | None:
            return sum(lst) / len(lst) if lst else None

        lines.append(
            f"| `{mode}` "
            f"| {_fmt(_avg(vals['faithfulness']))} "
            f"| {_fmt(_avg(vals['answer_relevancy']))} "
            f"| {_fmt(_avg(vals['factuality']))} "
            f"| {_fmt(_avg(vals['safety_rate']), pct=True)} |"
        )

    lines.append("")
    lines.append("---")
    lines.append("*Bold values indicate best score per metric per dataset.*")
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    args = _parse_args()

    skip_modes = {m.strip() for m in args.skip_modes.split(",") if m.strip()}
    active_modes = [m for m in MODES if m not in skip_modes]

    datasets_to_run = DATASETS
    if args.dataset:
        datasets_to_run = [d for d in DATASETS if d["name"] == args.dataset]

    # Wire in CSV paths from CLI
    for d in datasets_to_run:
        if d["name"] == "archehr_qa" and args.archehr_csv_path:
            d["csv_path"] = args.archehr_csv_path
        if d["name"] == "medquad" and args.medquad_csv_path:
            d["csv_path"] = args.medquad_csv_path

    total = len(datasets_to_run) * len(active_modes)
    print(f"Running {total} eval jobs ({len(datasets_to_run)} datasets x {len(active_modes)} modes) ...")
    print(f"  Modes:    {active_modes}")
    print(f"  Datasets: {[d['name'] for d in datasets_to_run]}")
    print(f"  N={args.n}  seed={args.seed}")
    print()

    results: dict[tuple[str, str], dict | None] = {}
    job_num = 0
    for ds in datasets_to_run:
        for mode in active_modes:
            job_num += 1
            # Check if report already exists from a previous run — skip re-running
            mode_slug = mode.replace("+", "_")
            existing_report = HERE / f"{ds['name']}_{mode_slug}_eval_report.md"
            if existing_report.exists():
                print(f"[{job_num}/{total}] {ds['name']} / {mode}  (cached -> {existing_report.name})")
                results[(ds["name"], mode)] = _parse_report(existing_report)
                continue

            print(f"[{job_num}/{total}] {ds['name']} / {mode}")
            r = _run_eval(
                dataset=ds["name"],
                mode=mode,
                n=args.n,
                seed=args.seed,
                csv_path=ds["csv_path"],
            )
            results[(ds["name"], mode)] = r
            print()

    # Build comparison report
    active_dataset_names = [d["name"] for d in datasets_to_run]
    report_text = _build_comparison_report(
        results=results,
        datasets=active_dataset_names,
        modes=active_modes,
        n=args.n,
        seed=args.seed,
        date_str=time.strftime("%Y-%m-%d"),
    )

    output_path = HERE / args.output
    output_path.write_text(report_text, encoding="utf-8")
    print(f"Comparison report written -> {output_path}")

    # Also print a quick summary table to stdout
    print()
    print("=== QUICK SUMMARY (avg across datasets) ===")
    print(f"{'Mode':<16}  {'Faithfulness':>12}  {'Relevancy':>10}  {'Factuality':>10}  {'Safety':>8}")
    print("-" * 64)
    for mode in active_modes:
        f_vals, r_vals, fact_vals, s_vals = [], [], [], []
        for ds in datasets_to_run:
            rv = results.get((ds["name"], mode), {}) or {}
            if rv.get("faithfulness") is not None:
                f_vals.append(rv["faithfulness"])
            if rv.get("answer_relevancy") is not None:
                r_vals.append(rv["answer_relevancy"])
            if rv.get("factuality") is not None:
                fact_vals.append(rv["factuality"])
            if rv.get("safety_rate") is not None:
                s_vals.append(rv["safety_rate"])

        avg_f    = sum(f_vals) / len(f_vals) if f_vals else None
        avg_r    = sum(r_vals) / len(r_vals) if r_vals else None
        avg_fact = sum(fact_vals) / len(fact_vals) if fact_vals else None
        avg_s    = sum(s_vals) / len(s_vals) if s_vals else None

        print(
            f"{mode:<16}  "
            f"{_fmt(avg_f):>12}  "
            f"{_fmt(avg_r):>10}  "
            f"{_fmt(avg_fact):>10}  "
            f"{_fmt(avg_s, pct=True):>8}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
