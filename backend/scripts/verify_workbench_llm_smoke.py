from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
REPORT_PATH = ROOT / "evals" / "workbench" / "llm-smoke-report.json"

sys.path.insert(0, str(BACKEND))
os.environ.setdefault("WORKBENCH_DB_MODE", "off")

from app.script_workbench import Transcript  # noqa: E402
from app.workbench_llm import (  # noqa: E402
    LLMRuntimeConfig,
    analyze_transcript_structured,
    generate_hotspot_structured,
    get_llm_config,
)


def configure_api_key_alias() -> None:
    api_key = os.getenv("WORKBENCH_LLM_API_KEY")
    if api_key and not os.getenv("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = api_key


def has_model_credentials(config: LLMRuntimeConfig) -> bool:
    if config.mode == "offline":
        return False
    if config.api_base:
        return bool(os.getenv("OPENAI_API_KEY") or os.getenv("WORKBENCH_LLM_API_KEY"))
    return bool(os.getenv("OPENAI_API_KEY") or os.getenv("WORKBENCH_LLM_API_KEY"))


def sample_transcript() -> Transcript:
    text = (
        "你以为这只是一个普通明星回应吗？真正值得看的不是谁赢了，"
        "而是这次公开表达里哪些信息被放大了。我们只看公开信息，"
        "先整理时间线，再看粉丝和路人的不同情绪，最后回到一个问题："
        "一次回应到底是在解释事实，还是在管理大家的期待？"
    )
    return Transcript(
        id="llm_smoke_transcript",
        source_video_id="llm_smoke_source",
        asr_text=text,
        ocr_text="",
        content_text=text,
        timestamps=[],
        confidence=0.92,
        source="smoke",
    )


def validate_analysis() -> dict[str, Any]:
    result = analyze_transcript_structured(sample_transcript())
    analysis = result.analysis
    passed = (
        len(analysis.hook) >= 4
        and len(analysis.conflict) >= 4
        and len(analysis.structure) >= 3
        and len(analysis.emotion_curve) >= 3
        and bool(analysis.ending_cta)
    )
    return {
        "passed": passed,
        "used_model": result.status.used_model,
        "mode": result.status.mode,
        "model": result.status.model,
        "error": result.status.error,
        "fields": {
            "hook": analysis.hook,
            "structure_count": len(analysis.structure),
            "emotion_count": len(analysis.emotion_curve),
            "account_type": analysis.account_type,
            "template": analysis.reusable_template,
        },
    }


def validate_hotspot() -> dict[str, Any]:
    result = generate_hotspot_structured(
        hotspot="某明星公开回应后，粉丝和路人围绕态度产生争议",
        account_type="娱乐吃瓜号",
        duration_seconds=45,
        tone="克制、有信息增量，不编造细节",
        goal="引发评论",
        template_id=None,
    )
    passed = (
        bool(result.brief.event_summary)
        and len(result.brief.no_go_zones) >= 2
        and len(result.scripts) >= 3
        and all(script.title and script.spoken_script and script.risk_check for script in result.scripts)
    )
    return {
        "passed": passed,
        "used_model": result.status.used_model,
        "mode": result.status.mode,
        "model": result.status.model,
        "error": result.status.error,
        "fields": {
            "script_count": len(result.scripts),
            "matched_template_count": len(result.matched_templates),
            "first_title": result.scripts[0].title if result.scripts else None,
            "risk_count": len(result.scripts[0].risk_check.items) if result.scripts else 0,
        },
    }


def build_report(expect_model: bool) -> dict[str, Any]:
    configure_api_key_alias()
    config = get_llm_config()
    credentials_present = has_model_credentials(config)
    original_mode = os.getenv("WORKBENCH_LLM_MODE")
    should_skip_model = config.mode != "offline" and not credentials_present
    if should_skip_model:
        os.environ["WORKBENCH_LLM_MODE"] = "offline"
    try:
        analysis = validate_analysis()
        hotspot = validate_hotspot()
    finally:
        if should_skip_model:
            if original_mode is None:
                os.environ.pop("WORKBENCH_LLM_MODE", None)
            else:
                os.environ["WORKBENCH_LLM_MODE"] = original_mode
    used_model = analysis["used_model"] or hotspot["used_model"]
    schema_passed = analysis["passed"] and hotspot["passed"]
    model_requirement_passed = used_model if expect_model else True
    status = "model_used" if used_model else "fallback_or_offline"
    if config.mode != "offline" and not credentials_present:
        status = "skipped_no_credentials"

    return {
        "passed": schema_passed and model_requirement_passed,
        "status": status,
        "config": config.model_dump(),
        "credentials_present": credentials_present,
        "expect_model": expect_model,
        "analysis": analysis,
        "hotspot": hotspot,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test LiteLLM/Instructor structured output.")
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    parser.add_argument(
        "--expect-model",
        action="store_true",
        help="Fail unless the smoke test actually uses a model instead of fallback/offline output.",
    )
    args = parser.parse_args()

    report = build_report(expect_model=args.expect_model)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        "workbench_llm_smoke "
        f"passed={report['passed']} "
        f"status={report['status']} "
        f"mode={report['config']['mode']} "
        f"model={report['config']['model']} "
        f"analysis_model={report['analysis']['used_model']} "
        f"hotspot_model={report['hotspot']['used_model']} "
        f"report={args.report}"
    )
    if not report["passed"]:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
