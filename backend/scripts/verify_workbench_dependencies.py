from __future__ import annotations

import argparse
import importlib
import json
import os
import shutil
import subprocess
import sys
import warnings
from importlib.util import find_spec
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
REPORT_PATH = ROOT / "evals" / "workbench" / "dependency-report.json"

sys.path.insert(0, str(BACKEND))
os.environ.setdefault("WORKBENCH_LLM_MODE", "offline")
os.environ.setdefault("WORKBENCH_DB_MODE", "off")
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")

from app.script_workbench import (  # noqa: E402
    asr_mode,
    douyin_downloader_command,
    douyin_downloader_mode,
    media_root,
    model_worker_python,
    ocr_mode,
)


def command_status(name: str, label: str, required: bool, install_hint: str) -> dict[str, Any]:
    path = shutil.which(name)
    if not path:
        return {
            "key": name,
            "label": label,
            "required": required,
            "available": False,
            "status": "missing" if required else "reserved",
            "detail": f"PATH 中未找到 {name}。",
            "install_hint": install_hint,
        }

    version = ""
    try:
        result = subprocess.run(
            [path, "-version"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        version = (result.stdout or result.stderr).splitlines()[0].strip()
    except Exception as exc:  # pragma: no cover - environment-specific
        version = f"版本探测失败：{exc}"

    return {
        "key": name,
        "label": label,
        "required": required,
        "available": True,
        "status": "ready",
        "detail": f"{path}；{version}" if version else path,
        "install_hint": install_hint,
    }


def module_status(
    module_name: str,
    label: str,
    required: bool,
    install_hint: str,
    mode: str | None = None,
    import_checks: list[str] | None = None,
) -> dict[str, Any]:
    available = find_spec(module_name) is not None
    if available:
        status = "ready"
        detail = f"Python 模块 {module_name} 可导入。"
    elif required:
        status = "missing"
        detail = f"Python 模块 {module_name} 不可导入。"
    else:
        status = "reserved"
        detail = f"Python 模块 {module_name} 暂未安装；当前作为可选能力保留。"

    if available and import_checks:
        try:
            for check in import_checks:
                module_path, _, attribute = check.partition(":")
                imported = importlib.import_module(module_path)
                if attribute:
                    getattr(imported, attribute)
            detail = f"{detail} 运行入口深导入通过。"
        except Exception as exc:
            available = False
            status = "missing" if required else "reserved"
            detail = f"Python 模块 {module_name} 已安装，但运行入口导入失败：{exc}"

    if mode:
        detail = f"{detail} 当前模式：{mode}。"

    return {
        "key": module_name,
        "label": label,
        "required": required,
        "available": available,
        "status": status,
        "detail": detail,
        "install_hint": install_hint,
    }


def model_worker_module_status(
    module_name: str,
    label: str,
    required: bool,
    install_hint: str,
    mode: str,
    import_checks: list[str],
) -> dict[str, Any]:
    executable = model_worker_python(module_name)
    available = executable is not None
    status = "ready" if available else ("missing" if required else "reserved")
    if available:
        detail = f"模型工作进程 Python 可导入 {module_name}：{executable}。"
        try:
            check_code = (
                "import importlib, sys; "
                "checks = sys.argv[1:]; "
                "\nfor check in checks:\n"
                "    module_path, _, attribute = check.partition(':')\n"
                "    imported = importlib.import_module(module_path)\n"
                "    if attribute:\n"
                "        getattr(imported, attribute)\n"
            )
            completed = subprocess.run(
                [executable, "-c", check_code, *import_checks],
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )
            if completed.returncode == 0:
                detail = f"{detail} 运行入口深导入通过。"
            else:
                available = False
                status = "missing" if required else "reserved"
                detail = f"模型工作进程 Python 已找到 {module_name}，但运行入口导入失败：{(completed.stderr or completed.stdout).strip()[:180]}"
        except Exception as exc:
            available = False
            status = "missing" if required else "reserved"
            detail = f"模型工作进程 Python 探测失败：{exc}"
    else:
        detail = f"模型工作进程 Python 未找到可导入 {module_name} 的环境。"

    return {
        "key": module_name,
        "label": label,
        "required": required,
        "available": available,
        "status": status,
        "detail": f"{detail} 当前模式：{mode}。",
        "install_hint": install_hint,
    }


def media_dir_status() -> dict[str, Any]:
    root = media_root()
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".dependency-check"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return {
            "key": "media_dir",
            "label": "媒体临时目录",
            "required": True,
            "available": True,
            "status": "ready",
            "detail": f"{root} 可写。",
            "install_hint": "设置 WORKBENCH_MEDIA_DIR 到有读写权限的本地目录。",
        }
    except Exception as exc:
        return {
            "key": "media_dir",
            "label": "媒体临时目录",
            "required": True,
            "available": False,
            "status": "missing",
            "detail": f"{root} 不可写：{exc}",
            "install_hint": "设置 WORKBENCH_MEDIA_DIR 到有读写权限的本地目录。",
        }


def douyin_downloader_status() -> dict[str, Any]:
    root = media_root()
    config_path = root / "dependency-check-douyin.yml"
    output_dir = root / "dependency-check-douyin"
    command, cwd, message = douyin_downloader_command(
        config_path,
        "https://v.douyin.com/dependency-check/",
        output_dir,
    )
    available = command is not None and douyin_downloader_mode() != "off"
    detail = message
    if command:
        cwd_text = f"；工作目录：{cwd}" if cwd else ""
        detail = f"{message} 命令已生成：{' '.join(command[:3])}...{cwd_text}"
        if command[1:2] and command[1].endswith("run.py"):
            probe_command = command[:2] + ["--help"]
        else:
            probe_command = command[:1] + ["--help"]
        try:
            completed = subprocess.run(
                probe_command,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            if completed.returncode == 0:
                detail = f"{detail} CLI help 探测通过。"
            else:
                available = False
                detail = f"{detail} CLI help 探测失败：{(completed.stderr or completed.stdout).strip()[:180]}"
        except Exception as exc:
            available = False
            detail = f"{detail} CLI help 探测失败：{exc}"
    if douyin_downloader_mode() == "off":
        detail = "WORKBENCH_DOUYIN_DOWNLOADER_MODE=off，链接解析已关闭。"

    return {
        "key": "douyin_downloader",
        "label": "douyin-downloader",
        "required": False,
        "available": available,
        "status": "ready" if available else "reserved",
        "detail": detail,
        "install_hint": "clone jiji262/douyin-downloader 后设置 WORKBENCH_DOUYIN_DOWNLOADER_DIR，或设置 WORKBENCH_DOUYIN_DOWNLOADER_CMD。",
    }


def build_report() -> dict[str, Any]:
    components = [
        command_status("ffmpeg", "FFmpeg", True, "brew install ffmpeg"),
        command_status("ffprobe", "FFprobe", False, "brew install ffmpeg"),
        media_dir_status(),
        model_worker_module_status(
            "funasr",
            "FunASR",
            False,
            "创建独立模型环境并设置 WORKBENCH_MODEL_WORKER_PYTHON，例如 .venv-model/bin/python。",
            asr_mode(),
            ["funasr:AutoModel"],
        ),
        model_worker_module_status(
            "paddleocr",
            "PaddleOCR",
            False,
            "创建独立模型环境并设置 WORKBENCH_MODEL_WORKER_PYTHON，例如 .venv-model/bin/python。",
            ocr_mode(),
            ["paddle", "paddleocr:PaddleOCR"],
        ),
        module_status("litellm", "LiteLLM", False, "python3 -m pip install litellm", import_checks=["litellm"]),
        module_status("instructor", "Instructor", False, "python3 -m pip install instructor", import_checks=["instructor"]),
        douyin_downloader_status(),
    ]
    required_components = [item for item in components if item["required"]]
    baseline_ready = all(item["available"] for item in required_components)
    optional_ready = sum(1 for item in components if not item["required"] and item["available"])
    return {
        "passed": baseline_ready,
        "summary": {
            "baseline_ready": baseline_ready,
            "required_ready": sum(1 for item in required_components if item["available"]),
            "required_total": len(required_components),
            "optional_ready": optional_ready,
            "optional_total": len(components) - len(required_components),
        },
        "components": components,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify local dependencies for Douyin script workbench.")
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    parser.add_argument("--strict", action="store_true", help="Fail when baseline dependencies are unavailable.")
    args = parser.parse_args()

    report = build_report()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = report["summary"]
    print(
        "workbench_dependencies "
        f"baseline_ready={summary['baseline_ready']} "
        f"required={summary['required_ready']}/{summary['required_total']} "
        f"optional={summary['optional_ready']}/{summary['optional_total']} "
        f"report={args.report}"
    )
    for item in report["components"]:
        print(f"- {item['label']}: {item['status']} | {item['detail']}")

    if args.strict and not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
