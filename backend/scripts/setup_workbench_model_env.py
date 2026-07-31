from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_VENV = ROOT / ".venv-model"
DEFAULT_PACKAGES = [
    "funasr",
    "paddleocr",
    "paddlepaddle",
    "torch",
    "torchaudio",
]


def run(command: list[str], timeout: int | None = None) -> None:
    print("$ " + " ".join(command))
    completed = subprocess.run(command, cwd=ROOT, timeout=timeout, check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the isolated ASR/OCR model environment.")
    parser.add_argument("--python", default="3.11", help="Python version managed by uv.")
    parser.add_argument("--venv", type=Path, default=DEFAULT_VENV, help="Virtualenv path.")
    parser.add_argument("--skip-python-install", action="store_true", help="Assume the Python version already exists.")
    parser.add_argument("--package", action="append", default=[], help="Extra package to install.")
    args = parser.parse_args()

    uv = shutil.which("uv")
    if uv is None:
        raise SystemExit("uv is required. Install uv first, then rerun this script.")

    venv = args.venv if args.venv.is_absolute() else ROOT / args.venv
    packages = [*DEFAULT_PACKAGES, *args.package]

    if not args.skip_python_install:
        run([uv, "python", "install", args.python])
    run([uv, "venv", str(venv), "--python", args.python])
    run([uv, "pip", "install", "--python", str(venv / "bin" / "python"), *packages], timeout=900)

    print("")
    print("Model environment ready.")
    print(f"Set WORKBENCH_MODEL_WORKER_PYTHON={venv / 'bin' / 'python'}")


if __name__ == "__main__":
    main()
