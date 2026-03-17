"""
Single entry point for reproducible project runs.

Examples:
  python run_pipeline.py track1
  python run_pipeline.py track2
  python run_pipeline.py strict-eval
  python run_pipeline.py track3-eval --n 25 --seed 42 --compare
  python run_pipeline.py app
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=True)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run Track 1/2/3 pipelines")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("track1", help="Run deterministic BM25 baseline and save outputs")

    p_t2 = sub.add_parser("track2", help="Build KG + evaluate BM25 vs KG expansion")
    p_t2.add_argument(
        "--skip-model-install",
        action="store_true",
        help="Do not run scripts/install_scispacy.py before Track 2",
    )

    sub.add_parser("strict-eval", help="Run strict evaluation protocol")

    p_t3 = sub.add_parser("track3-eval", help="Run Track 3 eval harness")
    p_t3.add_argument("--n", type=int, default=25, help="Number of sampled questions")
    p_t3.add_argument("--seed", type=int, default=42, help="Sampling seed")
    p_t3.add_argument(
        "--compare",
        action="store_true",
        help="Also run baseline compare section in eval report",
    )
    p_t3.add_argument(
        "--dataset",
        default="pubmedqa",
        help="Dataset to evaluate: pubmedqa (default), medquad, archehr_qa, mimic3, mimic4",
    )
    p_t3.add_argument(
        "--csv-path",
        default=None,
        help="Path to a local CSV file for the dataset (optional; "
             "falls back to HuggingFace auto-download when omitted)",
    )
    p_t3.add_argument(
        "--retriever",
        default=None,
        choices=["bm25", "semantic", "hybrid"],
        help="Retrieval strategy (default: dataset's recommended retriever)",
    )

    sub.add_parser("app", help="Launch Streamlit app")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    py = sys.executable
    try:
        if args.cmd == "track1":
            _run([py, "scripts/run_track1.py"])
            return 0

        if args.cmd == "track2":
            if not args.skip_model_install:
                _run([py, "scripts/install_scispacy.py"])
            _run([py, "track2_build_kg.py"])
            return 0

        if args.cmd == "strict-eval":
            _run([py, "scripts/strict_eval.py"])
            return 0

        if args.cmd == "track3-eval":
            cmd = [py, "eval_harness.py", "--n", str(args.n), "--seed", str(args.seed)]
            if args.compare:
                cmd.append("--compare")
            if args.dataset != "pubmedqa":
                cmd += ["--dataset", args.dataset]
            if args.csv_path:
                cmd += ["--csv-path", args.csv_path]
            if args.retriever:
                cmd += ["--retriever", args.retriever]
            _run(cmd)
            return 0

        if args.cmd == "app":
            _run([py, "-m", "streamlit", "run", "app.py"])
            return 0
    except subprocess.CalledProcessError as exc:
        cmd_str = " ".join(str(p) for p in exc.cmd)
        print(f"Command failed with exit code {exc.returncode}: {cmd_str}")
        return exc.returncode or 1

    raise ValueError(f"Unknown command: {args.cmd}")


if __name__ == "__main__":
    raise SystemExit(main())
