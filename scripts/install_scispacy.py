"""
Install SciSpacy dependencies and model for Track 2.

Usage:
  python scripts/install_scispacy.py
  python scripts/install_scispacy.py --model sci_sm
  python scripts/install_scispacy.py --skip-base
"""

from __future__ import annotations

import argparse
import subprocess
import sys

BC5CDR_URL = (
    "https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.4/"
    "en_ner_bc5cdr_md-0.5.4.tar.gz"
)
SCISM_URL = (
    "https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.4/"
    "en_core_sci_sm-0.5.4.tar.gz"
)

MODEL_TO_URL = {
    "bc5cdr": BC5CDR_URL,
    "sci_sm": SCISM_URL,
}


def _run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)


def _pip_install(*packages: str) -> None:
    _ensure_pip()
    _run([sys.executable, "-m", "pip", "install", *packages])


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Install SciSpacy and model for Track 2")
    p.add_argument(
        "--model",
        choices=("bc5cdr", "sci_sm"),
        default="bc5cdr",
        help="Preferred model to install (default: bc5cdr)",
    )
    p.add_argument(
        "--skip-base",
        action="store_true",
        help="Skip base dependency install (numpy/spacy/scispacy)",
    )
    return p.parse_args()


def _ensure_pip() -> None:
    """Some uv-created envs do not include pip; bootstrap it when missing."""
    probe = subprocess.run(
        [sys.executable, "-m", "pip", "--version"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if probe.returncode == 0:
        return
    cmd = [sys.executable, "-m", "ensurepip", "--upgrade"]
    print("+", " ".join(cmd))
    boot = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if boot.returncode != 0:
        raise subprocess.CalledProcessError(
            boot.returncode,
            cmd,
            output=boot.stdout,
            stderr=boot.stderr,
        )


def _install_model_with_fallback(preferred: str) -> str:
    first = MODEL_TO_URL[preferred]
    try:
        _pip_install(first)
        return preferred
    except subprocess.CalledProcessError:
        if preferred == "sci_sm":
            raise

    print("Preferred model install failed, trying fallback model: sci_sm")
    _pip_install(MODEL_TO_URL["sci_sm"])
    return "sci_sm"


def main() -> int:
    args = _parse_args()

    try:
        if not args.skip_base:
            # Keep these pinned to avoid numpy/spacy/scispacy incompatibilities.
            _pip_install("numpy==1.26.4", "spacy==3.7.5", "scispacy==0.5.4")
    except subprocess.CalledProcessError as exc:
        print("Base dependency installation failed (numpy/spacy/scispacy).")
        print("Check permissions and Python environment, then retry.")
        if exc.stderr:
            first = exc.stderr.strip().splitlines()[:3]
            if first:
                print("Installer error:")
                for line in first:
                    print(f"  {line}")
        return 1

    try:
        installed_model = _install_model_with_fallback(args.model)
    except subprocess.CalledProcessError:
        print("Model installation failed. Install manually and rerun Track 2.")
        return 2

    print(f"SciSpacy setup complete. Installed model: {installed_model}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
