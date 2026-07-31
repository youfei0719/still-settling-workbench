from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

os.environ.setdefault("WORKBENCH_LLM_MODE", "offline")
os.environ.setdefault("WORKBENCH_SKILL_EVAL_FIXTURES", "1")

from app.script_workbench import (  # noqa: E402
    AnalyzeTextRequest,
    GenerateHotspotRequest,
    GeneratedScriptUpdateRequest,
    LinkTaskRequest,
    TemplateReviewUpdateRequest,
    create_link_task,
    create_text_analysis,
    generate_hotspot,
    match_templates,
    risk_check,
    update_generated_script,
    update_template_review,
    enable_offline_evaluation_templates,
)


DEFAULT_DATA = ROOT / "evals" / "workbench" / "acceptance_samples.json"
DEFAULT_REPORT = ROOT / "evals" / "workbench" / "acceptance-report.json"


def load_data(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_text_sample(sample: dict[str, Any]) -> dict[str, Any]:
    result = create_text_analysis(
        AnalyzeTextRequest(
            title=str(sample["title"]),
            content=str(sample["content"]),
            input_type=sample.get("input_type") or "text",
        )
    )
    checks = {
        "has_hook": bool(result.analysis.hook),
        "has_conflict": bool(result.analysis.conflict),
        "structure_clear": len(result.analysis.structure) >= 5,
        "template_suggested": bool(result.preset_draft.skeleton),
        "shootable_preview": len(result.generated_preview.spoken_script) >= 120
        and len(result.generated_preview.shot_suggestions) >= 3
        and len(result.generated_preview.subtitle_rhythm) >= 2,
        "export_ready": result.export_markdown.startswith("# ") and bool(result.export_json),
    }
    return {"title": sample["title"], "passed": all(checks.values()), "checks": checks}


def verify_hotspot(item: dict[str, Any]) -> dict[str, Any]:
    result = generate_hotspot(
        GenerateHotspotRequest(
            hotspot=str(item["hotspot"]),
            account_type=str(item.get("account_type") or "娱乐吃瓜号"),
            duration_seconds=int(item.get("duration_seconds") or 45),
            tone=str(item.get("tone") or "克制犀利但不造谣"),
            goal=str(item.get("goal") or "引发评论区讨论事实和态度"),
            template_id=str(item.get("template_id") or "tpl_reversal"),
        )
    )
    angles = {script.content_angle for script in result.scripts}
    checks = {
        "brief_has_angles": bool(result.brief.event_summary) and len(result.brief.angles) >= 3,
        "matched_template": bool(result.matched_templates),
        "three_versions": len(result.scripts) >= 3,
        "different_angles": len(angles) >= 3,
        "shootable": all(
            len(script.spoken_script) >= 120
            and len(script.shot_suggestions) >= 3
            and len(script.subtitle_rhythm) >= 2
            for script in result.scripts
        ),
    }
    return {"hotspot": item["hotspot"], "passed": all(checks.values()), "checks": checks}


def verify_risk(item: dict[str, Any]) -> dict[str, Any]:
    result = risk_check(str(item["content"]))
    passed = not result.passed and result.level in {"medium", "high"} and bool(result.items)
    return {"name": item["name"], "passed": passed, "level": result.level, "labels": [risk.label for risk in result.items]}


def verify_template_asset() -> dict[str, Any]:
    updated = update_template_review(
        "tpl_reversal",
        TemplateReviewUpdateRequest(
            quality_score=64,
            applicable_scenes=["公开回应复盘"],
            unsuitable_scenes=["未经证实爆料"],
            disabled_reason="验收临时禁用。",
            last_review_note="人工复盘确认模板边界。",
        ),
    )
    matched = match_templates("娱乐吃瓜号", "某明星公开回应后粉丝和路人产生争议")
    checks = {
        "review_saved": updated.quality_score == 64 and "公开回应复盘" in updated.applicable_scenes,
        "boundary_saved": "未经证实爆料" in updated.unsuitable_scenes and bool(updated.disabled_reason),
        "disabled_not_matched": updated.id not in {template.id for template in matched},
    }
    return {"passed": all(checks.values()), "checks": checks}


def verify_script_edit_and_export() -> dict[str, Any]:
    generated = generate_hotspot(
        GenerateHotspotRequest(
            hotspot="某品牌公开回应后，评论区围绕态度和补救动作持续讨论",
            account_type="商业分析号",
            duration_seconds=45,
            tone="克制、有信息增量",
            goal="导出给剪辑团队试拍",
            template_id="tpl_context",
        )
    )
    source = generated.scripts[0]
    updated = update_generated_script(
        source.id,
        GeneratedScriptUpdateRequest(
            title=f"{source.title}｜审核版",
            spoken_script=f"{source.spoken_script}\n补充：只使用公开可验证信息。",
            shot_suggestions=[*source.shot_suggestions, "结尾保留两秒评论引导画面。"],
            subtitle_rhythm=[*source.subtitle_rhythm, "结尾 CTA 单独上屏。"],
            comment_cta="你觉得最应被讨论的是回应速度，还是补救动作？",
            production_status="review_ready",
            version_label="v2-review",
            editor_note="验收确认可编辑、可保存、可导出。",
        ),
    )
    checks = {
        "saved": updated.title.endswith("审核版") and updated.production_status == "review_ready",
        "versioned": updated.version_label == "v2-review" and len(updated.version_history) >= 1,
        "production_fields": len(updated.shot_suggestions) >= 4 and len(updated.subtitle_rhythm) >= 3,
        "risk_rechecked": updated.risk_check.level != "high",
    }
    return {"passed": all(checks.values()), "checks": checks}


def verify_link_fallback() -> dict[str, Any]:
    previous = os.environ.get("WORKBENCH_DOUYIN_DOWNLOADER_MODE")
    os.environ["WORKBENCH_DOUYIN_DOWNLOADER_MODE"] = "off"
    try:
        result = create_link_task(LinkTaskRequest(url="https://v.douyin.com/acceptance-fallback/"))
    finally:
        if previous is None:
            os.environ.pop("WORKBENCH_DOUYIN_DOWNLOADER_MODE", None)
        else:
            os.environ["WORKBENCH_DOUYIN_DOWNLOADER_MODE"] = previous
    checks = {
        "fallback_returned": result.parser_status == "skipped",
        "explains_reason": result.parser_error_code == "downloader_disabled" and bool(result.parser_action_items),
        "offers_inputs": {"上传视频文件", "上传字幕文件", "粘贴转写文本"}.issubset(set(result.fallback_inputs)),
    }
    return {"passed": all(checks.values()), "checks": checks}


def verify_link_error_classification() -> dict[str, Any]:
    from app.script_workbench import classify_douyin_download_error

    error_code, title, _, actions = classify_douyin_download_error(
        "Cookies may be invalid or incomplete; Empty 200 response for /aweme/v1/web/aweme/detail/ (anti-bot)"
    )
    checks = {
        "anti_bot_is_transient_public_access": error_code == "public_access_unavailable",
        "title_is_clear": title == "公开链接暂时不可用",
        "does_not_require_login": any("不需要登录" in item for item in actions),
    }
    return {"passed": all(checks.values()), "checks": checks}


def verify_external_link_gate_without_cookie() -> dict[str, Any]:
    from app.script_workbench import external_link_gate

    result = external_link_gate("https://v.douyin.com/acceptance-public/", run_link=False)
    checks = {
        "ready_without_cookie": result["ready_to_test"] is True,
        "does_not_preblock_cookie": result["status"] == "ready",
        "cookie_state_visible": result["cookie_configured"] is False,
        "explains_login_free_retry": any("免登录" in item for item in result["action_items"]),
    }
    return {"passed": all(checks.values()), "checks": checks}


def verify_share_text_link_input() -> dict[str, Any]:
    from app.script_workbench import normalize_douyin_url_input

    share_text = (
        "5.12 B@G.Iv ZMJ:/ 05/21 :7pm 品牌最好的宣传，其实早在行动里了"
        "# 奢侈品 # 时尚 # gucci # 肖战 # 宋威龙  https://v.douyin.com/gk_7aLCc3SU/ "
        "复制此链接，打开Dou音搜索，直接观看视频！"
    )
    normalized = normalize_douyin_url_input(share_text)
    previous = os.environ.get("WORKBENCH_DOUYIN_DOWNLOADER_MODE")
    os.environ["WORKBENCH_DOUYIN_DOWNLOADER_MODE"] = "off"
    try:
        result = create_link_task(LinkTaskRequest(url=share_text))
    finally:
        if previous is None:
            os.environ.pop("WORKBENCH_DOUYIN_DOWNLOADER_MODE", None)
        else:
            os.environ["WORKBENCH_DOUYIN_DOWNLOADER_MODE"] = previous
    checks = {
        "url_extracted": normalized == "https://v.douyin.com/gk_7aLCc3SU/",
        "source_uses_extracted_url": result.source_video.url == "https://v.douyin.com/gk_7aLCc3SU/",
        "fallback_still_available": result.parser_status == "skipped" and bool(result.fallback_inputs),
    }
    return {"passed": all(checks.values()), "checks": checks, "normalized": normalized}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the Douyin script workbench v1 core loop.")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    enable_offline_evaluation_templates()

    data = load_data(args.data)
    text_results = [verify_text_sample(sample) for sample in data["text_samples"]]
    hotspot_results = [verify_hotspot(item) for item in data["hotspots"]]
    risk_results = [verify_risk(item) for item in data["risk_cases"]]
    template_asset = verify_template_asset()
    script_edit = verify_script_edit_and_export()
    link_fallback = verify_link_fallback()
    link_error_classification = verify_link_error_classification()
    external_link_gate_without_cookie = verify_external_link_gate_without_cookie()
    share_text_link = verify_share_text_link_input()

    text_passed = sum(item["passed"] for item in text_results)
    hotspot_passed = sum(item["passed"] for item in hotspot_results)
    risk_passed = sum(item["passed"] for item in risk_results)
    report = {
        "passed": text_passed / max(1, len(text_results)) >= 0.8
        and hotspot_passed == len(hotspot_results)
        and risk_passed == len(risk_results)
        and template_asset["passed"]
        and script_edit["passed"]
        and link_fallback["passed"]
        and link_error_classification["passed"]
        and external_link_gate_without_cookie["passed"]
        and share_text_link["passed"],
        "summary": {
            "text": f"{text_passed}/{len(text_results)}",
            "hotspots": f"{hotspot_passed}/{len(hotspot_results)}",
            "risk": f"{risk_passed}/{len(risk_results)}",
            "template_asset": template_asset["passed"],
            "script_edit": script_edit["passed"],
            "link_fallback": link_fallback["passed"],
            "link_error_classification": link_error_classification["passed"],
            "external_link_gate_without_cookie": external_link_gate_without_cookie["passed"],
            "share_text_link": share_text_link["passed"],
        },
        "text_results": text_results,
        "hotspot_results": hotspot_results,
        "risk_results": risk_results,
        "template_asset": template_asset,
        "script_edit": script_edit,
        "link_fallback": link_fallback,
        "link_error_classification": link_error_classification,
        "external_link_gate_without_cookie": external_link_gate_without_cookie,
        "share_text_link": share_text_link,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        "workbench_acceptance "
        f"passed={report['passed']} text={report['summary']['text']} "
        f"hotspots={report['summary']['hotspots']} risk={report['summary']['risk']} "
        f"template_asset={template_asset['passed']} script_edit={script_edit['passed']} "
        f"link_fallback={link_fallback['passed']} link_error_classification={link_error_classification['passed']} "
        f"external_link_gate_without_cookie={external_link_gate_without_cookie['passed']} "
        f"share_text_link={share_text_link['passed']} "
        f"report={args.report}"
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
