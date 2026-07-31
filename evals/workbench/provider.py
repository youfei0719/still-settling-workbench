from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

os.environ.setdefault("WORKBENCH_LLM_MODE", "offline")
os.environ.setdefault("WORKBENCH_SKILL_EVAL_FIXTURES", "1")

from app.script_workbench import (  # noqa: E402
    AnalyzeTextRequest,
    GenerateHotspotRequest,
    create_text_analysis,
    generate_hotspot,
    enable_offline_evaluation_templates,
    risk_check,
)


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2)


def _load_payload(prompt: str, context: dict[str, Any]) -> dict[str, Any]:
    try:
        return json.loads(prompt)
    except json.JSONDecodeError:
        return dict(context.get("vars") or {})


def _run_analysis(payload: dict[str, Any]) -> dict[str, Any]:
    result = create_text_analysis(
        AnalyzeTextRequest(
            title=payload.get("title") or "Promptfoo 分析样本",
            content=payload.get("content") or "",
            input_type=payload.get("input_type") or "text",
        )
    )
    return {
        "task": "analysis",
        "account_type": result.analysis.account_type,
        "hook": result.analysis.hook,
        "conflict": result.analysis.conflict,
        "structure_count": len(result.analysis.structure),
        "template_name": result.preset_draft.name,
        "template_skeleton_count": len(result.preset_draft.skeleton),
        "risk_level": result.risk_check.level,
        "risk_passed": result.risk_check.passed,
        "export_has_markdown": result.export_markdown.startswith("# "),
    }


def _run_hotspot(payload: dict[str, Any]) -> dict[str, Any]:
    result = generate_hotspot(
        GenerateHotspotRequest(
            hotspot=payload.get("hotspot") or "",
            account_type=payload.get("account_type") or "娱乐吃瓜号",
            template_id=payload.get("template_id") or None,
            duration_seconds=int(payload.get("duration_seconds") or 45),
            tone=payload.get("tone") or "犀利但不造谣",
            goal=payload.get("goal") or "引发评论",
        )
    )
    return {
        "task": "hotspot",
        "brief_angles_count": len(result.brief.angles),
        "matched_templates_count": len(result.matched_templates),
        "scripts_count": len(result.scripts),
        "script_angles": [script.content_angle for script in result.scripts],
        "script_titles": [script.title for script in result.scripts],
        "risk_levels": [script.risk_check.level for script in result.scripts],
    }


def _run_risk(payload: dict[str, Any]) -> dict[str, Any]:
    result = risk_check(payload.get("content") or "")
    return {
        "task": "risk",
        "risk_passed": result.passed,
        "risk_level": result.level,
        "labels": [item.label for item in result.items],
        "rewrites": [item.rewrite for item in result.items],
    }


def call_api(prompt: str, options: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    enable_offline_evaluation_templates()
    payload = _load_payload(prompt, context)
    task = payload.get("task")

    if task == "analysis":
        output = _run_analysis(payload)
    elif task == "hotspot":
        output = _run_hotspot(payload)
    elif task == "risk":
        output = _run_risk(payload)
    else:
        return {"output": "", "error": f"Unknown workbench eval task: {task!r}"}

    return {"output": _json(output)}
