from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


def write_result(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Isolated workbench ASR/OCR worker.")
    parser.add_argument("--kind", choices=["asr", "ocr", "warmup-asr", "warmup-ocr"], required=True)
    parser.add_argument("--input", action="append", default=[])
    parser.add_argument("--hotword", action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        from app.script_workbench import (
            get_funasr_model,
            get_paddle_ocr_model,
            run_paddle_ocr,
            transcribe_audio,
        )

        if args.kind == "asr":
            if not args.input:
                raise ValueError("ASR worker requires an audio input.")
            result = transcribe_audio(Path(args.input[0]), hotwords=args.hotword)
            payload = result.model_dump(mode="json")
        elif args.kind == "ocr":
            result = run_paddle_ocr([Path(value) for value in args.input])
            payload = result.model_dump(mode="json")
        elif args.kind == "warmup-asr":
            get_funasr_model()
            payload = {"status": "completed", "message": "FunASR 模型加载验证完成。"}
        else:
            get_paddle_ocr_model()
            payload = {"status": "completed", "message": "PaddleOCR 模型加载验证完成。"}
    except Exception as exc:
        write_result(args.output, {"error": f"{type(exc).__name__}: {exc}"})
        return 1

    write_result(args.output, payload)
    return 0


if __name__ == "__main__":
    exit_code = main()
    # Native model libraries can crash during Python interpreter teardown on macOS.
    # The structured result is flushed first, then the worker exits without teardown.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(exit_code)
