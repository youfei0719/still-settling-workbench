from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
REPORT_PATH = ROOT / "evals" / "workbench" / "status-report.json"
MARKDOWN_PATH = ROOT / "evals" / "workbench" / "status-report.md"

API_HEALTH_URL = "http://127.0.0.1:8000/api/v1/script-workbench/overview"
FRONTEND_HEALTH_URL = "http://127.0.0.1:5173/"
LOCAL_OPENER = build_opener(ProxyHandler({}))

sys.path.insert(0, str(BACKEND))

from app.script_workbench import (  # noqa: E402
    capabilities,
    external_link_gate,
    external_llm_gate,
    human_review_gate,
)


def http_health(url: str) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": "douyin-script-workbench-status"})
    try:
        with LOCAL_OPENER.open(request, timeout=3) as response:
            status_code = getattr(response, "status", 0)
            return {"healthy": 200 <= status_code < 400, "status_code": status_code, "url": url}
    except (OSError, URLError) as exc:
        return {"healthy": False, "status_code": None, "url": url, "error": str(exc)[:160]}


def http_json(url: str) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": "douyin-script-workbench-status"})
    try:
        with LOCAL_OPENER.open(request, timeout=90) as response:
            status_code = getattr(response, "status", 0)
            payload = json.loads(response.read().decode("utf-8"))
            if isinstance(payload, dict):
                payload["_http_status_code"] = status_code
                return payload
            return {"_http_status_code": status_code, "_error": "JSON root is not an object."}
    except (OSError, URLError, json.JSONDecodeError) as exc:
        return {"_error": str(exc)[:220]}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "path": str(path)}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"exists": True, "path": str(path), "valid": False, "error": str(exc)}
    if isinstance(payload, dict):
        payload.setdefault("exists", True)
        payload.setdefault("path", str(path))
        payload.setdefault("valid", True)
        return payload
    return {"exists": True, "path": str(path), "valid": False, "error": "JSON root is not an object."}


def report_passed(report: dict[str, Any]) -> bool:
    if not report.get("exists"):
        return False
    if "passed" in report:
        return bool(report["passed"])
    return False


def dependency_baseline_ready(report: dict[str, Any]) -> bool:
    if not report.get("exists"):
        return False
    if "baseline_ready" in report:
        return bool(report["baseline_ready"])
    summary = report.get("summary")
    if isinstance(summary, dict) and "baseline_ready" in summary:
        return bool(summary["baseline_ready"])
    return report_passed(report)


def build_status(args: argparse.Namespace) -> dict[str, Any]:
    reports = {
        "acceptance": read_json(ROOT / "evals" / "workbench" / "acceptance-report.json"),
        "dependencies": read_json(ROOT / "evals" / "workbench" / "dependency-report.json"),
        "llm_smoke": read_json(ROOT / "evals" / "workbench" / "llm-smoke-report.json"),
        "video_smoke": read_json(ROOT / "evals" / "workbench" / "video-smoke-report.json"),
    }

    code_ready = (
        report_passed(reports["acceptance"])
        and dependency_baseline_ready(reports["dependencies"])
        and report_passed(reports["llm_smoke"])
    )
    video_ready = report_passed(reports["video_smoke"])
    services = {
        "api": http_health(API_HEALTH_URL),
        "frontend": http_health(FRONTEND_HEALTH_URL),
    }
    backend_gate_report: dict[str, Any] = {}
    if services["api"]["healthy"]:
        params = {
            key: value
            for key, value in {
                "link": args.link,
                "run_link": "true" if args.run_link else None,
                "expect_model": "true" if args.expect_model else None,
            }.items()
            if value
        }
        query = urlencode(params)
        backend_gate_report = http_json(
            f"http://127.0.0.1:8000/api/v1/script-workbench/external-gates{f'?{query}' if query else ''}"
        )

    if {"link_gate", "llm_gate", "human_review_gate"}.issubset(backend_gate_report):
        link_gate = backend_gate_report["link_gate"]
        llm_gate = backend_gate_report["llm_gate"]
        human_gate = backend_gate_report["human_review_gate"]
    else:
        link_gate = external_link_gate(args.link, args.run_link)
        llm_gate = external_llm_gate(args.expect_model)
        human_gate = human_review_gate(args.human_review_file)
    backend_capabilities = http_json("http://127.0.0.1:8000/api/v1/script-workbench/capabilities") if services["api"]["healthy"] else {}
    capability_status = backend_capabilities if isinstance(backend_capabilities.get("items"), list) else capabilities().model_dump(mode="json")
    external_ready = bool(link_gate["passed"] and llm_gate["passed"] and human_gate["passed"])

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "passed": bool(code_ready and video_ready and external_ready),
        "code_ready": code_ready,
        "video_ready": video_ready,
        "external_ready": external_ready,
        "services": services,
        "capabilities": capability_status,
        "reports": reports,
        "external_gates": {
            "link_gate": link_gate,
            "llm_gate": llm_gate,
            "human_review_gate": human_gate,
            "source": "backend_api" if {"link_gate", "llm_gate", "human_review_gate"}.issubset(backend_gate_report) else "local_cli",
        },
        "remaining": [
            item
            for item in [
                None if link_gate["passed"] else "链接入口不可用；需要配置下载器或提供可解析抖音链接。",
                None if llm_gate["passed"] else "配置真实 LLM API Key/API Base 后执行真实模型 smoke。",
                None if human_gate["passed"] else f"完成 10 条脚本人工复核；当前通过 {human_gate.get('passed_count', 0)}/10。",
            ]
            if item is not None
        ],
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    gates = report["external_gates"]
    link_gate = gates["link_gate"]
    llm_gate = gates["llm_gate"]
    human_gate = gates["human_review_gate"]
    lines = [
        "# 依旧沉淀 v1 状态报告",
        "",
        f"- 生成时间：`{report['generated_at']}`",
        f"- 代码闭环：`{'ready' if report['code_ready'] else 'not_ready'}`",
        f"- 视频模型链路：`{'ready' if report['video_ready'] else 'not_ready'}`",
        f"- 外部门禁：`{'ready' if report['external_ready'] else 'not_ready'}`",
        "",
        "## 服务状态",
        "",
        "| 服务 | 状态 | 地址 |",
        "| --- | --- | --- |",
        f"| API | {'healthy' if report['services']['api']['healthy'] else 'not healthy'} | `{report['services']['api']['url']}` |",
        f"| 前端 | {'healthy' if report['services']['frontend']['healthy'] else 'not healthy'} | `{report['services']['frontend']['url']}` |",
        "",
        "## 验收输入快照",
        "",
        "| 项目 | 当前值 |",
        "| --- | --- |",
        f"| 已解析抖音链接 | `{link_gate.get('normalized_link') or '未提供'}` |",
        f"| 链接解析链路 | `{', '.join(link_gate.get('resolver_chain') or []) or 'missing'}` |",
        f"| yt-dlp | `{'configured' if link_gate.get('yt_dlp_configured') else 'missing'}` |",
        f"| douyin-downloader | `{'configured' if link_gate.get('douyin_downloader_configured') else 'missing'}` |",
        "| 抖音链接提取 | `免登录，不读取浏览器会话` |",
        f"| LLM 模式 | `{llm_gate.get('mode', 'offline')}` |",
        f"| LLM 模型 | `{llm_gate.get('model', '')}` |",
        f"| LLM API Key | `{'configured' if llm_gate.get('api_key_configured') else 'missing'}` |",
        f"| 人工复核 | `{human_gate.get('passed_count', 0)}/{human_gate.get('required_count', 10)}` |",
        "",
        "## 外部门禁",
        "",
        "| 门禁 | 状态 | 通过 |",
        "| --- | --- | --- |",
        f"| 真实抖音链接 | `{link_gate['status']}` | `{link_gate['passed']}` |",
        f"| 真实 LLM | `{llm_gate['status']}` | `{llm_gate['passed']}` |",
        f"| 人工质量复核 | `{human_gate['status']}` | `{human_gate['passed']}` |",
        "",
        "## 剩余动作",
        "",
    ]
    if report["remaining"]:
        lines.extend(f"- {item}" for item in report["remaining"])
    else:
        lines.append("- 无。")
    lines.extend(
        [
            "",
            "## 最终验收命令",
            "",
            "```bash",
            "npm run verify:workbench:final -- --link '粘贴授权抖音分享文案或链接'",
            "```",
            "",
            "## 安全输入说明",
            "",
            "- 抖音公开链接提取不读取浏览器 Cookie。",
            "- API Key 只通过本机页面或当前 shell 环境传入，不要写入仓库文件。",
            "- 报告只展示配置状态和脱敏提示，不输出明文密钥。",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize current Douyin script workbench v1 status.")
    parser.add_argument("--link", help="Authorized Douyin link or share text for external gate summary.")
    parser.add_argument("--run-link", action="store_true", help="Run real douyin-downloader link validation.")
    parser.add_argument("--expect-model", action="store_true", help="Require real model smoke for LLM gate.")
    parser.add_argument("--human-review-file", type=Path, help="Human review JSON file.")
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    parser.add_argument("--markdown", type=Path, default=MARKDOWN_PATH)
    args = parser.parse_args()

    report = build_status(args)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(report, args.markdown)
    print(
        "workbench_status "
        f"passed={report['passed']} "
        f"code={report['code_ready']} "
        f"video={report['video_ready']} "
        f"external={report['external_ready']} "
        f"api={'healthy' if report['services']['api']['healthy'] else 'not_healthy'} "
        f"frontend={'healthy' if report['services']['frontend']['healthy'] else 'not_healthy'} "
        f"report={args.report} "
        f"markdown={args.markdown}"
    )


if __name__ == "__main__":
    main()
