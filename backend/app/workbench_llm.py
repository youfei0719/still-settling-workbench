from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal, Optional, TypeVar
from urllib.parse import urlparse

from pydantic import BaseModel, Field, ValidationError

from app.script_workbench import (
    DraftDiagnosis,
    DraftInputRequest,
    FactSource,
    FactVerification,
    GeneratedScript,
    HotspotBrief,
    ScriptAnalysis,
    ScriptSegment,
    SkillMatch,
    TemplatePattern,
    Transcript,
    build_script,
    match_templates,
    pick_account_type,
    pick_template,
    pick_template_by_id,
    risk_check,
    split_sentences,
)

ModelMode = Literal["offline", "optional", "required"]
T = TypeVar("T", bound=BaseModel)


class LLMRuntimeConfig(BaseModel):
    mode: ModelMode = "offline"
    model: str = "openai/gpt-4.1-mini"
    api_base: Optional[str] = None
    temperature: float = 0.2
    max_retries: int = 1
    timeout_seconds: float = 60


class LLMCallStatus(BaseModel):
    used_model: bool
    mode: ModelMode
    model: str
    error: Optional[str] = None


class StructuredAnalysisOutput(BaseModel):
    hook: str
    conflict: str
    structure: list[ScriptSegment] = Field(min_length=3)
    emotion_curve: list[str] = Field(min_length=3)
    reversal: str
    ending_cta: str
    account_type: str
    reusable_template: str
    template_suggestions: list[str] = Field(default_factory=list)
    content_angle: str


class StructuredHotspotOutput(BaseModel):
    brief: HotspotBrief
    scripts: list[GeneratedScript] = Field(min_length=3, max_length=5)


class StructuredAnalysisResult(BaseModel):
    analysis: StructuredAnalysisOutput
    status: LLMCallStatus


class StructuredSkillDraftOutput(BaseModel):
    name: str = Field(min_length=4, max_length=12)
    solves_problems: list[str] = Field(min_length=2, max_length=6)
    match_signals: list[str] = Field(min_length=4, max_length=12)
    writing_tasks: list[str] = Field(min_length=3, max_length=8)
    applicable_scenes: list[str] = Field(min_length=5, max_length=10)
    unsuitable_scenes: list[str] = Field(min_length=2, max_length=6)
    skeleton: list[str] = Field(min_length=3, max_length=8)
    hook_formula: str
    emotion_rhythm: str
    ending_formula: str
    risk_boundary: str
    borrowable_moves: list[str] = Field(min_length=3, max_length=8)


class StructuredTranscriptCorrection(BaseModel):
    original: str = Field(min_length=1, max_length=30)
    corrected: str = Field(min_length=1, max_length=30)
    reason: str = Field(min_length=2, max_length=120)
    confidence: int = Field(ge=0, le=100)


class StructuredTranscriptCorrectionOutput(BaseModel):
    corrections: list[StructuredTranscriptCorrection] = Field(
        default_factory=list, max_length=20
    )
    unresolved_fragments: list[str] = Field(default_factory=list, max_length=8)


class StructuredSkillChoice(BaseModel):
    skill_id: str
    match_score: int = Field(ge=0, le=100)
    reason: str
    apply_plan: list[str] = Field(min_length=2, max_length=6)


class StructuredSkillRanking(BaseModel):
    matches: list[StructuredSkillChoice] = Field(min_length=1, max_length=3)


class StructuredSkillCoverage(BaseModel):
    step: str = Field(min_length=2, max_length=100)
    evidence: str = Field(min_length=4, max_length=180)


class StructuredRewriteVariant(BaseModel):
    content_angle: str = Field(min_length=2, max_length=12)
    positioning: str = Field(min_length=8, max_length=100)
    difference_from_others: str = Field(min_length=8, max_length=100)
    title: str = Field(min_length=4, max_length=60)
    spoken_script: str = Field(min_length=80, max_length=1200)
    shot_suggestions: list[str] = Field(min_length=2, max_length=4)
    subtitle_rhythm: list[str] = Field(min_length=2, max_length=4)
    comment_cta: str = Field(min_length=4, max_length=100)
    skill_application: list[str] = Field(min_length=2, max_length=4)
    skill_coverage: list[StructuredSkillCoverage] = Field(min_length=3, max_length=8)


class StructuredDraftRewriteOutput(BaseModel):
    variants: list[StructuredRewriteVariant] = Field(min_length=3, max_length=3)


class StructuredRecommendedDraftOutput(BaseModel):
    matches: list[StructuredSkillChoice] = Field(min_length=1, max_length=3)
    draft: StructuredRewriteVariant


def _structure_workspace_text(
    *,
    payload: DraftInputRequest,
    skill: TemplatePattern,
    draft: StructuredRewriteVariant,
    fact_verification: FactVerification,
) -> str:
    facts = [
        item.strip()
        for item in fact_verification.verified_facts[:4]
        if item.strip()
    ]
    if not facts and fact_verification.summary:
        facts = [fact_verification.summary.strip()]

    coverage = [
        f"{index}. {item.step.strip()}：{item.evidence.strip()}"
        for index, item in enumerate(draft.skill_coverage, start=1)
        if item.step.strip() and item.evidence.strip()
    ]
    if not coverage:
        coverage = [
            f"{index}. {step}"
            for index, step in enumerate(skill.skeleton, start=1)
            if step.strip()
        ]

    fact_lines = "\n".join(f"- {item}" for item in facts[:4]) or "- 暂无可直接展开的细节，请先补充可核实素材。"
    structure_lines = "\n".join(f"- {item}" for item in coverage[:6])
    application_lines = "\n".join(
        f"- {item.strip()}" for item in draft.skill_application[:4] if item.strip()
    )
    if not application_lines:
        application_lines = f"- 开头参考：{skill.hook_formula}\n- 情绪节奏：{skill.emotion_rhythm}\n- 收束方式：{skill.ending_formula}"

    return (
        "【写作结构工作稿】\n"
        "这不是 AI 成稿。请按下面结构逐段填写，必要时选中某一段继续让 Codex 局部补素材或改表达。\n\n"
        f"【中心判断】\n建议先写清一个可争辩判断：{draft.positioning.strip()}\n"
        "你来填写：\n\n\n"
        f"【可用事实素材】\n{fact_lines}\n\n"
        f"【采用 Skill】{skill.name}\n"
        f"结构骨架：{' -> '.join(skill.skeleton)}\n\n"
        "【段落 1：开头钩子】\n"
        f"写作建议：用「{skill.hook_formula}」做停留点，少交代前情，直接把观众带到中心判断。\n"
        "你来填写：\n\n\n"
        "【段落 2：事实支撑】\n"
        "写作建议：只选 1-2 个已核实事实写透，不堆信息；每个事实后面补一句它为什么支撑中心判断。\n"
        "你来填写：\n\n\n"
        "【段落 3：结构推进】\n"
        f"写作建议：按 Skill 顺序推进，不混用多个结构。\n{structure_lines}\n"
        "你来填写：\n\n\n"
        "【段落 4：情绪和观点升维】\n"
        f"写作建议：情绪节奏保持「{skill.emotion_rhythm}」，把个案落到观众能代入的处境或选择。\n"
        f"{application_lines}\n"
        "你来填写：\n\n\n"
        "【段落 5：结尾互动】\n"
        f"写作建议：用「{skill.ending_formula}」收束，再抛一个能让评论区接话的问题。\n"
        f"建议互动问题：{draft.comment_cta.strip()}\n"
        "你来填写："
    )


class StructuredRewriteWorkflowOutput(BaseModel):
    fact_verification: StructuredFactVerificationOutput
    matches: list[StructuredSkillChoice] = Field(default_factory=list, max_length=3)
    variants: list[StructuredRewriteVariant] = Field(default_factory=list, max_length=3)


class StructuredFactSource(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    url: str = Field(min_length=8, max_length=500)
    publisher: str = Field(default="", max_length=100)
    published_at: Optional[str] = Field(default=None, max_length=50)


class StructuredFactVerificationOutput(BaseModel):
    verdict: str = Field(min_length=2, max_length=30)
    core_event_verified: bool = False
    claim: str = Field(min_length=2, max_length=240)
    summary: str = Field(min_length=8, max_length=800)
    verified_facts: list[str] = Field(default_factory=list, max_length=10)
    corrections: list[str] = Field(default_factory=list, max_length=6)
    sources: list[StructuredFactSource] = Field(default_factory=list, max_length=8)


class StructuredSelectionRewriteOutput(BaseModel):
    replacement: str = Field(min_length=2, max_length=1600)
    change_summary: str = Field(min_length=2, max_length=160)
    supporting_facts: list[str] = Field(default_factory=list, max_length=6)
    sources: list[StructuredFactSource] = Field(default_factory=list, max_length=6)


class StructuredRewriteSuggestion(BaseModel):
    id: str = Field(min_length=2, max_length=40)
    label: str = Field(min_length=2, max_length=18)
    instruction: str = Field(min_length=4, max_length=180)
    reason: str = Field(min_length=4, max_length=160)
    evidence_needed: bool = False


class StructuredRewriteSuggestionOutput(BaseModel):
    suggestions: list[StructuredRewriteSuggestion] = Field(min_length=3, max_length=5)


ActivityCallback = Callable[[dict[str, str]], None]


class StructuredHotspotResult(BaseModel):
    brief: HotspotBrief
    scripts: list[GeneratedScript]
    matched_templates: list[TemplatePattern]
    status: LLMCallStatus


def get_llm_config() -> LLMRuntimeConfig:
    mode = os.getenv("WORKBENCH_LLM_MODE", "offline").strip().lower()
    if mode not in {"offline", "optional", "required"}:
        mode = "offline"
    return LLMRuntimeConfig(
        mode=mode,  # type: ignore[arg-type]
        model=os.getenv("WORKBENCH_LLM_MODEL", "openai/gpt-4.1-mini"),
        api_base=os.getenv("WORKBENCH_LLM_API_BASE") or None,
        temperature=float(os.getenv("WORKBENCH_LLM_TEMPERATURE", "0.2")),
        max_retries=int(os.getenv("WORKBENCH_LLM_MAX_RETRIES", "1")),
        timeout_seconds=float(os.getenv("WORKBENCH_LLM_TIMEOUT_SECONDS", "60")),
    )


def disabled_status(config: LLMRuntimeConfig) -> LLMCallStatus:
    return LLMCallStatus(
        used_model=False,
        mode=config.mode,
        model=config.model,
        error="LLM disabled; using deterministic fallback.",
    )


def fallback_status(config: LLMRuntimeConfig, error: Exception | str) -> LLMCallStatus:
    return LLMCallStatus(
        used_model=False,
        mode=config.mode,
        model=config.model,
        error=str(error),
    )


def success_status(config: LLMRuntimeConfig) -> LLMCallStatus:
    return LLMCallStatus(used_model=True, mode=config.mode, model=config.model)


def parse_model_json(content: str) -> dict:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end >= start:
        cleaned = cleaned[start : end + 1]
    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise ValueError("Structured model output must be a JSON object.")
    return parsed


def raw_json_completion(
    response_model: type[T],
    messages: list[dict[str, str]],
    config: LLMRuntimeConfig,
    api_key: Optional[str],
    litellm: object,
) -> T:
    schema = response_model.model_json_schema()
    json_messages = [
        *messages,
        {
            "role": "user",
            "content": (
                "请只输出一个合法 JSON 对象，不要使用 Markdown 代码块。"
                f"JSON 必须符合这个 schema：{json.dumps(schema, ensure_ascii=False)}"
            ),
        },
    ]
    kwargs: dict[str, object] = {
        "model": config.model,
        "messages": json_messages,
        "temperature": config.temperature,
        "timeout": config.timeout_seconds,
        "response_format": {"type": "json_object"},
    }
    if config.api_base:
        kwargs["api_base"] = config.api_base
    if api_key:
        kwargs["api_key"] = api_key
    try:
        response = litellm.completion(**kwargs)
    except Exception:
        kwargs.pop("response_format", None)
        response = litellm.completion(**kwargs)
    content = response.choices[0].message.content or ""
    return response_model.model_validate(parse_model_json(content))


def _codex_event_activity(
    event: dict[str, object], phase: str
) -> Optional[dict[str, str]]:
    event_type = str(event.get("type") or "")
    if event_type == "error":
        message = str(event.get("message") or "")
        if "Reconnecting" in message:
            return {
                "phase": phase,
                "kind": "status",
                "title": "Codex 正在重新连接",
                "detail": "当前步骤会自动继续，无需重复提交。",
                "status": "active",
            }
        return None
    if event_type not in {"item.started", "item.completed"}:
        return None
    raw_item = event.get("item")
    if not isinstance(raw_item, dict):
        return None
    item_type = str(raw_item.get("type") or "")
    status = "active" if event_type == "item.started" else "completed"
    if item_type == "web_search":
        query_value = raw_item.get("query") or raw_item.get("text")
        query_text = str(query_value or "").strip()
        return {
            "phase": phase,
            "kind": "search",
            "title": "正在检索公开来源" if status == "active" else "网页检索已完成",
            "detail": query_text[:180] or "Codex 已执行一轮公开网页检索。",
            "status": status,
        }
    if item_type in {"mcp_tool_call", "tool_call"}:
        tool_name = str(raw_item.get("tool") or raw_item.get("name") or "")
        item_text = json.dumps(raw_item, ensure_ascii=False, default=str)
        urls = re.findall(r"https?://[^\s\"'<>]+", item_text)
        if not urls and not any(
            marker in tool_name.lower() for marker in ["browser", "search", "web"]
        ):
            return None
        host = urlparse(urls[0]).netloc if urls else ""
        return {
            "phase": phase,
            "kind": "source",
            "title": "正在打开来源" if status == "active" else "来源页面已读取",
            "detail": host or "Codex 正在读取公开页面内容。",
            "status": status,
        }
    return None


def codex_cli_structured_completion(
    response_model: type[T],
    messages: list[dict[str, str]],
    config: LLMRuntimeConfig,
    api_key: str,
    allow_web_search: bool = False,
    activity_callback: Optional[ActivityCallback] = None,
    activity_phase: str = "writing",
    heartbeat_title: Optional[str] = None,
    process_timeout_seconds: Optional[float] = None,
) -> T:
    """Use Codex's Responses transport for relays that restrict generic HTTP clients."""
    codex_binary = shutil.which(os.getenv("WORKBENCH_CODEX_BINARY", "codex"))
    if not codex_binary:
        raise RuntimeError("Codex CLI is not installed or is not available on PATH.")
    if not config.api_base:
        raise RuntimeError("Codex CLI transport requires WORKBENCH_LLM_API_BASE.")

    model = config.model.removeprefix("openai/")
    prompt_parts = [
        f"{message['role'].upper()}:\n{message['content']}" for message in messages
    ]
    tool_instruction = (
        "Use browser or web tools to inspect current public sources before answering. "
        if allow_web_search
        else "Do not call tools. "
    )
    prompt_parts.append(
        "Return only the JSON object required by the output schema. "
        f"{tool_instruction}Do not include Markdown fences.\n"
        f"Output schema: {json.dumps(response_model.model_json_schema(), ensure_ascii=False)}"
    )
    prompt = "\n\n".join(prompt_parts)

    with tempfile.TemporaryDirectory(prefix="douyin-workbench-codex-") as temp_dir:
        temp_path = Path(temp_dir)
        auth_path = temp_path / "auth.json"
        output_path = temp_path / "output.json"
        auth_path.write_text(
            json.dumps({"OPENAI_API_KEY": api_key}),
            encoding="utf-8",
        )
        auth_path.chmod(0o600)
        # Each call uses an ephemeral CODEX_HOME. Disable the unrelated plugin catalog
        # so headless generation does not cold-sync the curated Git repository.
        command = [
            codex_binary,
            "exec",
            "--json",
            "--ignore-user-config",
            "--ignore-rules",
            "--disable",
            "plugins",
            "--skip-git-repo-check",
            "--ephemeral",
            "--sandbox",
            "read-only",
            "--color",
            "never",
            "-C",
            temp_dir,
            "-m",
            model,
            "-c",
            'model_provider="OpenAI"',
            "-c",
            'model_providers.OpenAI.name="OpenAI"',
            "-c",
            f"model_providers.OpenAI.base_url={json.dumps(config.api_base)}",
            "-c",
            'model_providers.OpenAI.wire_api="responses"',
            "-c",
            "model_providers.OpenAI.requires_openai_auth=true",
            "--output-last-message",
            str(output_path),
            "-",
        ]
        if allow_web_search:
            command[command.index("--color") : command.index("--color")] = [
                "--enable",
                "browser_use",
            ]
        environment = os.environ.copy()
        environment["CODEX_HOME"] = temp_dir
        environment["OPENAI_API_KEY"] = api_key
        minimum_timeout = 90.0 if allow_web_search else 180.0
        process_timeout = process_timeout_seconds or max(
            minimum_timeout,
            config.timeout_seconds + (30.0 if allow_web_search else 60.0),
        )
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=environment,
        )
        assert process.stdin is not None
        assert process.stdout is not None
        assert process.stderr is not None
        stdout_queue: queue.Queue[Optional[str]] = queue.Queue()
        stderr_lines: list[str] = []

        def read_stdout() -> None:
            for line in process.stdout:
                stdout_queue.put(line)
            stdout_queue.put(None)

        def read_stderr() -> None:
            stderr_lines.extend(process.stderr.readlines())

        stdout_thread = threading.Thread(target=read_stdout, daemon=True)
        stderr_thread = threading.Thread(target=read_stderr, daemon=True)
        stdout_thread.start()
        stderr_thread.start()
        process.stdin.write(prompt)
        process.stdin.close()

        deadline = time.monotonic() + process_timeout
        started_at = time.monotonic()
        last_heartbeat = started_at
        stdout_done = False
        while not stdout_done or process.poll() is None:
            now = time.monotonic()
            if now >= deadline:
                process.kill()
                process.wait(timeout=5)
                raise RuntimeError(
                    f"Codex 在 {round(process_timeout)} 秒内未完成当前阶段。"
                )
            if activity_callback is not None and now - last_heartbeat >= 15:
                elapsed = round(now - started_at)
                waiting_titles = {
                    "research": "等待联网核验返回",
                    "skill_match": "等待 Skill 匹配与结构返回",
                    "writing": "等待 Codex 返回文本结构",
                    "quality": "等待质量检查完成",
                }
                activity_callback(
                    {
                        "phase": activity_phase,
                        "kind": "status",
                        "title": heartbeat_title
                        or waiting_titles.get(
                            activity_phase, "等待 Codex 返回当前任务"
                        ),
                        "detail": f"已等待 {elapsed} 秒；最近的真实动作保留在下方记录中。",
                        "status": "active",
                    }
                )
                last_heartbeat = now
            try:
                line = stdout_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if line is None:
                stdout_done = True
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if activity_callback is not None and isinstance(event, dict):
                activity = _codex_event_activity(event, activity_phase)
                if activity is not None:
                    activity_callback(activity)

        return_code = process.wait(timeout=5)
        stdout_thread.join(timeout=1)
        stderr_thread.join(timeout=1)
        if return_code != 0 or not output_path.exists():
            error = ("".join(stderr_lines) or "Codex CLI call failed.")[-2000:]
            safe_error = error.replace(api_key, "<redacted>")
            if "git sync failed for curated plugin sync" in safe_error:
                raise RuntimeError(
                    "Codex 插件目录同步失败。请重启工作台以加载无插件冷启动配置。"
                )
            if "responses_retry" in safe_error:
                raise RuntimeError("Codex 模型服务连接重试后仍未返回结果。")
            raise RuntimeError(safe_error)
        return response_model.model_validate(
            parse_model_json(output_path.read_text(encoding="utf-8"))
        )


def structured_completion(
    response_model: type[T],
    messages: list[dict[str, str]],
    config: LLMRuntimeConfig,
    allow_web_search: bool = False,
    activity_callback: Optional[ActivityCallback] = None,
    activity_phase: str = "writing",
    heartbeat_title: Optional[str] = None,
    process_timeout_seconds: Optional[float] = None,
) -> T:
    api_key = os.getenv("WORKBENCH_LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if os.getenv("WORKBENCH_LLM_TRANSPORT", "litellm").strip().lower() == "codex_cli":
        if not api_key:
            raise RuntimeError("Codex CLI transport requires WORKBENCH_LLM_API_KEY.")
        return codex_cli_structured_completion(
            response_model,
            messages,
            config,
            api_key,
            allow_web_search=allow_web_search,
            activity_callback=activity_callback,
            activity_phase=activity_phase,
            heartbeat_title=heartbeat_title,
            process_timeout_seconds=process_timeout_seconds,
        )

    if allow_web_search:
        raise RuntimeError("联网事实核验要求 WORKBENCH_LLM_TRANSPORT=codex_cli。")

    import instructor
    import litellm

    kwargs: dict[str, object] = {
        "model": config.model,
        "messages": messages,
        "temperature": config.temperature,
        "response_model": response_model,
        "max_retries": config.max_retries,
        "timeout": config.timeout_seconds,
    }
    if config.api_base:
        kwargs["api_base"] = config.api_base
    if api_key:
        if not os.getenv("OPENAI_API_KEY"):
            os.environ["OPENAI_API_KEY"] = api_key
            os.environ["WORKBENCH_MANAGED_OPENAI_API_KEY"] = "1"
        kwargs["api_key"] = api_key

    # OpenAI-compatible relay services vary in how they expose tool calls.
    # JSON mode plus Pydantic validation is the most portable structured path.
    if config.api_base:
        return raw_json_completion(response_model, messages, config, api_key, litellm)

    client = instructor.from_litellm(litellm.completion)
    try:
        return client.chat.completions.create(**kwargs)
    except Exception:
        return raw_json_completion(response_model, messages, config, api_key, litellm)


def deterministic_analysis(transcript: Transcript) -> StructuredAnalysisOutput:
    sentences = split_sentences(transcript.content_text)
    hook = sentences[0][:80]
    conflict = next(
        (
            sentence
            for sentence in sentences
            if any(
                word in sentence
                for word in ["不是", "问题", "争议", "反转", "离谱", "为什么"]
            )
        ),
        sentences[min(1, len(sentences) - 1)][:90],
    )
    account_type = pick_account_type(transcript.content_text)
    template = pick_template(account_type)
    return StructuredAnalysisOutput(
        hook=hook,
        conflict=conflict,
        structure=[
            ScriptSegment(name="开头钩子", start="00:00", duration="3s", summary=hook),
            ScriptSegment(
                name="痛点引入", start="00:03", duration="6s", summary=conflict
            ),
            ScriptSegment(
                name="信息推进",
                start="00:09",
                duration="18s",
                summary="用 2-3 个信息点解释事件或观点，避免纯复述。",
            ),
            ScriptSegment(
                name="观点升维",
                start="00:27",
                duration="10s",
                summary="从事件本身上升到关系、传播或大众情绪。",
            ),
            ScriptSegment(
                name="结尾引导",
                start="00:37",
                duration="5s",
                summary=template.ending_formula,
            ),
        ],
        emotion_curve=["好奇", "共鸣", "紧张", "判断", "互动"],
        reversal="将事件从表层信息转向背后的传播逻辑或情绪结构。",
        ending_cta=template.ending_formula,
        account_type=account_type,
        reusable_template=template.name,
        template_suggestions=[template.name, "反差对比型", "背景拆解型"],
        content_angle="用公开信息提炼一个可讨论角度，而不是复述原事件。",
    )


def analyze_transcript_structured(transcript: Transcript) -> StructuredAnalysisResult:
    config = get_llm_config()
    if config.mode == "offline":
        return StructuredAnalysisResult(
            analysis=deterministic_analysis(transcript),
            status=disabled_status(config),
        )

    messages = [
        {
            "role": "system",
            "content": (
                "你是短视频脚本结构分析器。只分析结构和表达策略，不逐句仿写。"
                "输出必须符合 schema，不生成谣言、隐私、人身攻击或高敏内容。"
            ),
        },
        {
            "role": "user",
            "content": (
                "请分析以下抖音短视频文本，提取钩子、冲突、结构段、情绪曲线、"
                "反转/升维、结尾 CTA、账号类型、模板建议和可复用内容角度。\n\n"
                f"{transcript.content_text}"
            ),
        },
    ]
    try:
        output = structured_completion(StructuredAnalysisOutput, messages, config)
        return StructuredAnalysisResult(analysis=output, status=success_status(config))
    except (ValidationError, Exception) as exc:
        if config.mode == "required":
            raise
        return StructuredAnalysisResult(
            analysis=deterministic_analysis(transcript),
            status=fallback_status(config, exc),
        )


def correct_transcript_structured(
    transcript: str,
    context_text: str,
    context_terms: list[str],
    ocr_text: str,
) -> Optional[StructuredTranscriptCorrectionOutput]:
    config = get_llm_config()
    if config.mode == "offline":
        return None

    messages = [
        {
            "role": "system",
            "content": (
                "你是中文短视频语音转写校对器。只允许修正同音错字、人名专名、"
                "明显重复词和语音识别残片；不得改写、概括、润色、删减事实或补充原稿没有的信息。"
                "分享文案和 OCR 只作为校正证据，不能拼接进正文。无法确认时保留原文并放入"
                "unresolved_fragments。不要返回整篇稿件，只返回逐处 corrections。每项修改必须"
                "给出原文中实际存在且只出现一次的短片段、校正后文字、证据理由和置信度。"
                "如果错词在原稿中出现多次，original 必须带上足够的前后文以唯一定位，不能只返回单个词。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"原始语音转写：\n{transcript}\n\n"
                f"用户粘贴的分享文案：\n{context_text[:800]}\n\n"
                f"分享文案提取词：{json.dumps(context_terms, ensure_ascii=False)}\n"
                f"画面文字证据：{ocr_text[:500]}\n\n"
                "请只输出需要修改的短片段列表。重点核对人名、品牌名、作品名、数字、"
                "连续重复字和不通顺的 ASR 片段；不要复述完整稿件，不要改变句子结构和写作风格。"
            ),
        },
    ]
    try:
        return structured_completion(
            StructuredTranscriptCorrectionOutput, messages, config
        )
    except (ValidationError, Exception):
        if config.mode == "required":
            raise
        return None


def extract_skill_draft_structured(
    source_title: str,
    transcript: Transcript,
    analysis: ScriptAnalysis,
) -> Optional[StructuredSkillDraftOutput]:
    """Use the configured model to generalize one source into a cross-topic writing capability."""
    config = get_llm_config()
    if config.mode == "offline":
        return None
    analysis_context = json.dumps(analysis.model_dump(mode="json"), ensure_ascii=False)
    messages = [
        {
            "role": "system",
            "content": (
                "你是短视频运营团队的写作 Skill 架构师。你的任务不是总结视频讲了什么，"
                "而是抽象它如何写：它解决哪类稿件问题、依靠哪些结构信号、怎样跨题材复用。"
                "适用场景必须写成结构适用条件，而不是行业或题材清单；例如“已有明确结果但缺少解释路径”、"
                "“观众容易先入为主，需要用反常识重组认知”。不得写电商、职场、品牌、客服、作品等具体领域。"
                "只学习结构，不仿写原句。"
                "name、applicable_scenes、solves_problems、borrowable_moves 不得复述来源视频主题、人物、事件、标题或价值观，"
                "必须站在长期可复用结构能力角度输出：结构亮点、结构适用条件、写作缺口、迁移方法和风险边界。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"来源标题：{source_title}\n"
                f"结构分析：{analysis_context}\n"
                f"真实视频稿件：{transcript.content_text}\n\n"
                "请提炼一个可长期复用的写作 Skill。name 使用 6-12 个汉字的结构能力短名，"
                "必须只描述写法，不得出现来源人物、题材、事件、价值观或内容主题词；"
                "优先使用“钩子方式 + 推进/收束方式”的组合，例如“命题钩子·多例递进”、"
                "“反差钩子·转折升维”、“背景拆解·因果推进”。"
                "solves_problems 写运营人员会遇到的稿件问题；match_signals 写系统看到什么稿件特征时"
                "可辅助判断，但不得把它们当成必须逐字出现的关键词；writing_tasks 写结构能力标签；"
                "applicable_scenes 至少写 5 条结构条件，不要写行业、题材或相似案例；"
                "每条都必须回答“什么样的稿件结构缺口适合用这套写法”。skeleton 和公式必须可直接指导重构。"
                "borrowable_moves 必须写成可迁移写法动作，例如“用微小细节承接宏大命题”、"
                "“先压低认知，再用细节完成翻转”、“把公共事实转成普通人能感知的情绪入口”；"
                "不要写“适用于某个来源人物/事件/视频”的一次性描述。"
            ),
        },
    ]
    try:
        return structured_completion(StructuredSkillDraftOutput, messages, config)
    except (ValidationError, Exception):
        if config.mode == "required":
            raise
        return None


def rank_writing_skills_structured(
    payload: DraftInputRequest,
    candidates: list[TemplatePattern],
    activity_callback: Optional[ActivityCallback] = None,
) -> Optional[list[SkillMatch]]:
    config = get_llm_config()
    if config.mode == "offline" or not candidates:
        return None
    candidate_context = [
        {
            "id": skill.id,
            "name": skill.name,
            "solves_problems": skill.solves_problems,
            "match_signals": skill.match_signals,
            "applicable_scenes": skill.applicable_scenes,
            "skeleton": skill.skeleton,
            "hook_formula": skill.hook_formula,
            "emotion_rhythm": skill.emotion_rhythm,
            "risk_boundary": skill.risk_boundary,
        }
        for skill in candidates[:20]
    ]
    messages = [
        {
            "role": "system",
            "content": (
                "你是短视频稿件重构编辑。请按稿件的写作缺口和结构潜力匹配 Skill，"
                "不要只按明星、品牌等主题词匹配。优先判断开头、信息推进、冲突、情绪、"
                "观点升维和结尾互动分别需要什么。对于只有主题或简短想法的输入，不要求稿件"
                "已经具备 Skill 的结构信号；应判断这个 Skill 能否把现有素材补成完整稿，并说明"
                "还需要补充什么事实或案例。match_signals 只是辅助证据，不是关键词门槛。"
                "只允许返回候选列表中存在的 skill_id。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"稿件标题：{payload.title}\n稿件类型：{payload.input_type}\n"
                f"稿件内容：{payload.content}\n目标：{payload.goal}\n"
                f"候选 Skill：{json.dumps(candidate_context, ensure_ascii=False)}\n"
                "选择最适合的 1-3 个 Skill，说明为什么匹配以及具体如何应用。"
            ),
        },
    ]
    try:
        output = structured_completion(
            StructuredSkillRanking,
            messages,
            config,
            activity_callback=activity_callback,
            activity_phase="skill_match",
        )
    except (ValidationError, Exception):
        if config.mode == "required":
            raise
        return None
    by_id = {skill.id: skill for skill in candidates}
    matches: list[SkillMatch] = []
    for choice in output.matches:
        skill = by_id.get(choice.skill_id)
        if skill is None:
            continue
        matches.append(
            SkillMatch(
                skill=skill,
                match_score=choice.match_score,
                reason=choice.reason,
                apply_plan=choice.apply_plan,
            )
        )
    return matches or None


MAJOR_FACT_TERMS = [
    "去世",
    "死亡",
    "病逝",
    "被捕",
    "离婚",
    "封杀",
    "官宣",
    "失联",
    "辞职",
]

_FACT_VERIFICATION_CACHE: dict[str, tuple[float, FactVerification]] = {}
_FACT_VERIFICATION_CACHE_LOCK = threading.Lock()


def _fact_verification_cache_key(payload: DraftInputRequest) -> str:
    normalized_input = re.sub(
        r"\s+", " ", f"{payload.title} {payload.content}"
    ).strip().lower()
    return f"{datetime.now(timezone.utc).date().isoformat()}:{normalized_input}"


def _fact_verification_cache_ttl() -> float:
    raw_value = os.getenv("WORKBENCH_FACT_CACHE_TTL_SECONDS", "1800")
    try:
        return max(0.0, float(raw_value))
    except ValueError:
        return 1800.0


def _read_cached_fact_verification(
    payload: DraftInputRequest,
) -> Optional[FactVerification]:
    ttl = _fact_verification_cache_ttl()
    if ttl <= 0:
        return None
    cache_key = _fact_verification_cache_key(payload)
    now = time.monotonic()
    with _FACT_VERIFICATION_CACHE_LOCK:
        cached = _FACT_VERIFICATION_CACHE.get(cache_key)
        if cached is None:
            return None
        cached_at, verification = cached
        if now - cached_at > ttl:
            _FACT_VERIFICATION_CACHE.pop(cache_key, None)
            return None
        return verification.model_copy(deep=True)


def _store_fact_verification_cache(
    payload: DraftInputRequest,
    verification: FactVerification,
) -> None:
    if verification.verdict != "verified" or len(verification.sources) < 2:
        return
    now = time.monotonic()
    cache_key = _fact_verification_cache_key(payload)
    with _FACT_VERIFICATION_CACHE_LOCK:
        if len(_FACT_VERIFICATION_CACHE) >= 128:
            oldest_key = min(
                _FACT_VERIFICATION_CACHE,
                key=lambda key: _FACT_VERIFICATION_CACHE[key][0],
            )
            _FACT_VERIFICATION_CACHE.pop(oldest_key, None)
        _FACT_VERIFICATION_CACHE[cache_key] = (
            now,
            verification.model_copy(deep=True),
        )


def fact_verification_required(payload: DraftInputRequest) -> bool:
    text = f"{payload.title} {payload.content}"
    return any(term in text for term in MAJOR_FACT_TERMS)


def verify_major_claim_structured(
    payload: DraftInputRequest,
    activity_callback: Optional[ActivityCallback] = None,
) -> FactVerification:
    if not fact_verification_required(payload):
        return FactVerification(required=False, verdict="not_required")

    cached_verification = _read_cached_fact_verification(payload)
    if cached_verification is not None:
        if activity_callback is not None:
            activity_callback(
                {
                    "phase": "research",
                    "kind": "check",
                    "title": "已复用近期事实核验",
                    "detail": (
                        f"同一输入已由 {len(cached_verification.sources)} 个来源确认，"
                        "直接进入 Skill 匹配与结构生成。"
                    ),
                    "status": "completed",
                }
            )
        return cached_verification

    config = get_llm_config()
    claim = payload.title.strip() or payload.content.strip()[:180]
    if config.mode == "offline":
        return FactVerification(
            required=True,
            verdict="failed",
            claim=claim,
            summary="Codex 联网核验未启用，无法安全生成涉及重大事实的稿件。",
            checked_at=datetime.now(timezone.utc),
        )

    messages = [
        {
            "role": "system",
            "content": (
                "你是新闻事实核验编辑。必须实际使用浏览器或网页工具访问当前公开来源，"
                "不能凭训练记忆判断。优先查当事人、机构、出版社、政府或主流媒体的原始页面；"
                "搜索结果摘要不能单独作为证据。至少交叉核对两个相互独立的可靠来源。"
                "这是快速事实与创作证据门禁：最多执行3次网页检索、打开4个页面。"
                "一旦一个原始/官方来源和一个独立主流媒体对核心事件主体、事件和日期给出一致"
                "确认，就停止事件扩搜。若用户明确要求从人物处境、人生选择或作品细节切入，"
                "此后只允许再打开1个权威人物资料、出版社访谈或正式作品介绍页，补足与创作"
                "目标直接相关的证据；不得继续为奖项、销量、作品列表或同义关键词扩搜。"
                "只记录页面明确支持的事实，不推测，不补写。先提取事件主体，再使用主体的"
                "原文姓名和事件的原文关键词做精确检索；涉及日本人物去世时，至少使用一组"
                "日文讣告关键词和一组出版社关键词，并优先打开"
                "当天官方公告和新闻结果。不能只搜索人物主页、作品页或新书页。"
                "‘没有搜到讣告’不等于事件不实；预定出版、新书宣传、库存销售和历史页面"
                "也不能证明人物仍在世。只有事件日期之后的当事人直接活动、官方辟谣或其他"
                "直接权威证据才能返回 refuted；既无正面确认也无直接反证时必须返回 uncertain。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"当前日期：{datetime.now(timezone.utc).date().isoformat()}\n"
                f"待核验输入：{payload.title}\n{payload.content}\n\n"
                "请核验其中涉及去世、被捕、婚姻、官方变动等重大事实。"
                "verdict 只能表达 confirmed、refuted 或 uncertain。verdict 和 core_event_verified"
                "判断的是‘去世/被捕/离婚等核心事件是否发生’，不是用户口语中的‘今天’是否等于"
                "实际发生日期；如果核心事件已发生但日期表述不准，仍返回 confirmed 和 true，"
                "并把准确日期写入 corrections。"
                "如果 confirmed，整理 3-8 条已打开页面直接支持的 verified_facts。除了事件"
                "事实，优先提取一个人生选择、一个创作节点，以及与用户意图最相关的一到两条"
                "作品人物处境或选择。没有页面支持就留空，绝不根据书名或训练记忆补情节。"
                "sources 返回实际打开过的页面 URL、标题、发布者和日期，至少 2 个。"
            ),
        },
    ]
    try:
        output = structured_completion(
            StructuredFactVerificationOutput,
            messages,
            config,
            allow_web_search=True,
            activity_callback=activity_callback,
            activity_phase="research",
        )
    except (ValidationError, Exception) as exc:
        if config.mode == "required":
            raise
        error_message = str(exc)
        if any(
            marker in error_message
            for marker in [
                "WORKBENCH_LLM_TRANSPORT=codex_cli",
                "Codex CLI transport requires WORKBENCH_LLM_API_KEY",
            ]
        ):
            summary = (
                "Codex 联网服务配置未加载，已停止生成。"
                "请重启本地工作台服务后再试。"
            )
        else:
            summary = f"Codex 联网核验失败：{error_message[:240]}"
        return FactVerification(
            required=True,
            verdict="failed",
            claim=claim,
            summary=summary,
            checked_at=datetime.now(timezone.utc),
        )

    verdict_value = output.verdict.strip().lower()
    if output.core_event_verified or verdict_value in {
        "confirmed",
        "true",
        "verified",
        "yes",
        "属实",
    }:
        verdict: Literal["verified", "refuted", "uncertain"] = "verified"
    elif verdict_value in {"refuted", "false", "incorrect", "no", "不实"}:
        verdict = "refuted"
    else:
        verdict = "uncertain"

    sources: list[FactSource] = []
    seen_urls: set[str] = set()
    for source in output.sources:
        url = source.url.strip()
        if not url.startswith(("https://", "http://")) or url in seen_urls:
            continue
        seen_urls.add(url)
        sources.append(
            FactSource(
                title=source.title.strip(),
                url=url,
                publisher=source.publisher.strip(),
                published_at=source.published_at,
            )
        )
    if verdict == "verified" and len(sources) < 2:
        verdict = "uncertain"

    if activity_callback is not None:
        for source in sources[:5]:
            activity_callback(
                {
                    "phase": "research",
                    "kind": "source",
                    "title": "已采纳可靠来源",
                    "detail": f"{source.publisher or source.title} · {source.title}",
                    "status": "completed",
                }
            )
        activity_callback(
            {
                "phase": "research",
                "kind": "check",
                "title": "事实证据包已整理",
                "detail": f"确认 {len(output.verified_facts)} 条可写事实，{len(sources)} 个来源。",
                "status": "completed",
            }
        )

    verification = FactVerification(
        required=True,
        verdict=verdict,
        claim=output.claim.strip() or claim,
        summary=output.summary.strip(),
        verified_facts=[item.strip() for item in output.verified_facts if item.strip()][
            :8
        ],
        corrections=[item.strip() for item in output.corrections if item.strip()][:6],
        sources=sources[:8],
        checked_at=datetime.now(timezone.utc),
    )
    _store_fact_verification_cache(payload, verification)
    return verification


def select_skill_and_generate_recommended_draft_structured(
    payload: DraftInputRequest,
    diagnosis: DraftDiagnosis,
    candidates: list[TemplatePattern],
    fact_verification: FactVerification,
    activity_callback: Optional[ActivityCallback] = None,
) -> tuple[list[SkillMatch], list[GeneratedScript], LLMCallStatus]:
    """Select the best Skill and return a fillable writing structure."""
    config = get_llm_config()
    if config.mode == "offline" or not candidates:
        return [], [], disabled_status(config)

    target_min_chars = max(100, min(900, round(payload.duration_seconds * 4.5)))
    target_max_chars = max(
        target_min_chars + 30,
        min(1100, round(payload.duration_seconds * 5.3)),
    )
    candidate_context = [
        {
            "id": skill.id,
            "name": skill.name,
            "solves_problems": skill.solves_problems,
            "match_signals": skill.match_signals,
            "applicable_scenes": skill.applicable_scenes,
            "skeleton": skill.skeleton,
            "hook_formula": skill.hook_formula,
            "emotion_rhythm": skill.emotion_rhythm,
            "ending_formula": skill.ending_formula,
            "risk_boundary": skill.risk_boundary,
        }
        for skill in candidates[:20]
    ]
    fact_context = {
        "verdict": fact_verification.verdict,
        "summary": fact_verification.summary,
        "verified_facts": fact_verification.verified_facts,
        "corrections": fact_verification.corrections,
        "sources": [
            source.model_dump(mode="json") for source in fact_verification.sources
        ],
    }
    diagnosis_context = {
        "strengths": diagnosis.strengths,
        "problems": diagnosis.problems,
        "rewrite_goals": diagnosis.rewrite_goals,
        "no_go_zones": diagnosis.no_go_zones,
    }
    messages = [
        {
            "role": "system",
            "content": (
                "你是资深短视频主编。先按稿件缺口和结构潜力从候选中选择最适合的 Writing Skill，"
                "再使用 matches[0] 设计一份可填写的文本结构。不要按人物、作品、品牌等主题词机械匹配，"
                "也不要混用多个 Skill 的骨架。"
                "不要直接替用户写完整口播成稿；draft 字段只用于承载结构设计、段落目标、"
                "写作建议、可用素材和互动问题。spoken_script 可以写结构说明，但不得写成"
                "可直接发布的完整稿。热点受众通常已知道核心事件，除非日期是论点，否则"
                "开头建议少交代前情，立即进入观众不知道的新细节、冲突或判断。"
                "结构必须形成一个具体、可争辩的中心判断，并按主 Skill 的 skeleton 顺序推进。"
                "每个事实都要说明它如何支撑判断，不能用书目、册数、销量、奖项数量冒充深度。"
                "只能使用事实证据包明确支持的经历、情节、数字和作品标题。禁止把外文作品标题"
                "字面翻译成中文；证据包没有可靠中文译名时，保留来源原名或改用其他证据。"
                "如果证据包不足以支撑用户想要的作品细节，不得编造；应选择现有证据能写透的"
                "切口，并在 positioning 中明确用户应补哪类内容。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"输入类型：{payload.input_type}\n标题：{payload.title}\n"
                f"用户素材与创作意图：{payload.content}\n账号：{payload.account_type}\n"
                f"目标时长：约 {payload.duration_seconds} 秒，建议参考 {target_min_chars}-"
                f"{target_max_chars} 字；丰满、自然和证据完整优先，允许合理超出或低于。\n"
                f"语气：{payload.tone}\n传播目标：{payload.goal}\n"
                f"稿件诊断：{json.dumps(diagnosis_context, ensure_ascii=False)}\n"
                f"事实与创作证据包：{json.dumps(fact_context, ensure_ascii=False)}\n"
                f"候选 Writing Skill：{json.dumps(candidate_context, ensure_ascii=False)}\n\n"
                "matches 返回最适合的1-3个候选，只允许使用候选中的 skill_id。draft 必须严格"
                "使用 matches[0]；content_angle 用2-6个字命名这次结构切口。skill_application"
                "写2-4条具体写作建议，skill_coverage 按 skeleton 顺序写明每一步用户应填写"
                "什么内容。spoken_script 不要写成最终稿，只写结构说明。"
            ),
        },
    ]
    try:
        output = structured_completion(
            StructuredRecommendedDraftOutput,
            messages,
            config,
            activity_callback=activity_callback,
            activity_phase="skill_match",
            heartbeat_title="等待 Skill 匹配与结构设计",
            process_timeout_seconds=120.0,
        )
    except (ValidationError, Exception) as exc:
        if config.mode == "required":
            raise
        return [], [], fallback_status(config, exc)

    by_id = {skill.id: skill for skill in candidates}
    matches: list[SkillMatch] = []
    for choice in output.matches:
        skill = by_id.get(choice.skill_id)
        if skill is None:
            continue
        matches.append(
            SkillMatch(
                skill=skill,
                match_score=choice.match_score,
                reason=choice.reason.strip(),
                apply_plan=[item.strip() for item in choice.apply_plan if item.strip()],
            )
        )
    if not matches:
        error = RuntimeError("Codex 未返回可用的 Writing Skill 选择。")
        return [], [], fallback_status(config, error)

    primary_match = matches[0]
    draft = output.draft
    spoken_script = _structure_workspace_text(
        payload=payload,
        skill=primary_match.skill,
        draft=draft,
        fact_verification=fact_verification,
    )
    script = GeneratedScript(
        id=f"script_{os.urandom(5).hex()}",
        title=draft.title.strip(),
        account_type=payload.account_type,
        content_angle=draft.content_angle.strip(),
        duration_seconds=payload.duration_seconds,
        spoken_script=spoken_script,
        shot_suggestions=draft.shot_suggestions,
        subtitle_rhythm=draft.subtitle_rhythm,
        comment_cta=draft.comment_cta,
        risk_check=risk_check(f"{draft.title} {spoken_script} {draft.comment_cta}"),
        template_used=primary_match.skill.name,
        preset_application=[
            f"结构重点：{draft.positioning}",
            f"填写策略：{draft.difference_from_others}",
            *[f"写作建议：{item}" for item in draft.skill_application],
            *[
                f"结构填写：{item.step}｜{item.evidence}"
                for item in draft.skill_coverage
            ],
        ],
        version_label="V1",
    )
    if activity_callback is not None:
        activity_callback(
            {
                "phase": "skill_match",
                "kind": "skill",
                "title": f"已选用「{primary_match.skill.name}」",
                "detail": primary_match.reason,
                "status": "completed",
            }
        )
        activity_callback(
            {
                "phase": "writing",
                "kind": "draft",
                "title": "文本结构已完成",
                "detail": f"{len(draft.skill_coverage)} 个填写段落 · {script.title}",
                "status": "completed",
            }
        )
    return matches, [script], success_status(config)


def generate_rewrite_workflow_structured(
    payload: DraftInputRequest,
    diagnosis: DraftDiagnosis,
    candidates: list[TemplatePattern],
    activity_callback: Optional[ActivityCallback] = None,
) -> tuple[FactVerification, list[SkillMatch], list[GeneratedScript], LLMCallStatus]:
    """Verify, select a Skill, and draft a fillable structure in one Codex run."""
    config = get_llm_config()
    requires_fact_verification = fact_verification_required(payload)
    claim = payload.title.strip() or payload.content.strip()[:180]
    if config.mode == "offline" or not candidates:
        fact_verification = (
            FactVerification(
                required=True,
                verdict="failed",
                claim=claim,
                summary="Codex 联网核验未启用，无法安全生成涉及重大事实的稿件。",
                checked_at=datetime.now(timezone.utc),
            )
            if requires_fact_verification
            else FactVerification(required=False, verdict="not_required")
        )
        return fact_verification, [], [], disabled_status(config)

    target_min_chars = max(100, min(900, round(payload.duration_seconds * 4.5)))
    target_max_chars = max(
        target_min_chars + 30,
        min(1100, round(payload.duration_seconds * 5.3)),
    )
    candidate_context = [
        {
            "id": skill.id,
            "name": skill.name,
            "solves_problems": skill.solves_problems,
            "match_signals": skill.match_signals,
            "applicable_scenes": skill.applicable_scenes,
            "skeleton": skill.skeleton,
            "hook_formula": skill.hook_formula,
            "emotion_rhythm": skill.emotion_rhythm,
            "ending_formula": skill.ending_formula,
            "risk_boundary": skill.risk_boundary,
        }
        for skill in candidates[:20]
    ]
    diagnosis_context = {
        "strengths": diagnosis.strengths,
        "problems": diagnosis.problems,
        "rewrite_goals": diagnosis.rewrite_goals,
        "no_go_zones": diagnosis.no_go_zones,
    }
    research_instruction = (
        "必须实际使用浏览器或网页工具核验重大事实，不能凭训练记忆。先用一个官方或原始来源"
        "和一个独立主流媒体交叉确认主体、事件和日期；搜索摘要不能单独作为证据。随后根据"
        "用户的创作目标，最多再打开两个权威人物资料、出版社、正式访谈或作品介绍页面，"
        "补足能推进人物处境、选择与后果的创作证据。整个任务最多4次检索、打开4个页面，"
        "证据够用立即停止。"
        if requires_fact_verification
        else "当前输入不需要专项联网事实门禁，不调用工具。"
    )
    messages = [
        {
            "role": "system",
            "content": (
                "你是资深短视频主编，同时负责事实核验、Writing Skill 路由和文本结构设计。必须在一次"
                "任务里完成三件事：先建立可追溯证据包，再按写作缺口选择 Skill，最后设计三个"
                "真正不同的可填写文本结构。不得把任何一步伪装成已完成。"
                f"{research_instruction}"
                "若重大事实未被两个独立可靠来源确认，fact_verification 返回 refuted 或 uncertain，"
                "matches 和 variants 必须为空；不得生成半信半疑的结构。若已确认，verdict 返回"
                "confirmed，core_event_verified 返回 true。verified_facts 只收录打开页面直接支持的"
                "事实，优先包括一个人生选择、一个创作节点和两条与用户角度直接相关的作品处境或"
                "人物选择；每条都要能被 sources 中的页面追溯。"
                "选择 Skill 时按稿件缺口与结构潜力判断，不按人物、品牌等关键词判断。matches[0]"
                "必须是三版共同使用的主 Skill，后续候选只用于解释备选，不得混用骨架。"
                "variants 不是最终成稿，只用于承载结构切口、段落目标、写作建议、可用素材和互动问题。"
                "三个结构的开头策略、证据顺序、情绪曲线、中心判断和结尾至少三项不同。热点受众通常已知道事件，除非"
                "日期本身是论点，否则开头最多用一个短分句交代前情，立即进入新细节、冲突或判断。"
                "每版按口播逻辑设计3-5个自然段的填写框架。具体作品只能使用证据包支持的"
                "常用标题和情节；禁止把外文书名字面翻译成中文，禁止编造人物困境。没有可靠中文"
                "译名就保留来源原名或换用别的证据。册数、销量、奖项数量不能代替情绪与洞察，"
                "除非本版论点正是创作规模。每个事实都要说明它如何支撑本版判断。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"当前日期：{datetime.now(timezone.utc).date().isoformat()}\n"
                f"输入类型：{payload.input_type}\n标题：{payload.title}\n"
                f"用户素材与创作意图：{payload.content}\n账号：{payload.account_type}\n"
                f"目标时长：约 {payload.duration_seconds} 秒，建议参考 {target_min_chars}-"
                f"{target_max_chars} 字；丰满、自然和证据完整优先，允许合理超出或低于。\n"
                f"语气：{payload.tone}\n传播目标：{payload.goal}\n"
                f"稿件诊断：{json.dumps(diagnosis_context, ensure_ascii=False)}\n"
                f"候选 Writing Skill：{json.dumps(candidate_context, ensure_ascii=False)}\n\n"
                "fact_verification.sources 只返回实际打开过的 URL、标题、发布者和日期。"
                "如果用户口语中的‘今天’与实际日期不一致，但核心事件成立，仍返回 confirmed，"
                "并把准确日期写入 corrections。"
                "matches 返回最适合的1-3个候选 Skill，且只能使用候选列表中的 skill_id。"
                "variants 必须严格使用 matches[0] 的 skeleton 顺序；skill_coverage 按顺序写明用户"
                "每一步应填写什么内容。spoken_script 不要写成完整口播稿，只写结构说明。"
                "content_angle 用2-6个字命名具体创作切口，不使用固定的"
                "‘事实叙事/情绪共鸣/观点升维’。至少一版从具体瞬间或读者记忆切入，一版写透"
                "人物选择或作品困境，一版提出可争辩的新判断。"
            ),
        },
    ]
    try:
        output = structured_completion(
            StructuredRewriteWorkflowOutput,
            messages,
            config,
            allow_web_search=requires_fact_verification,
            activity_callback=activity_callback,
            activity_phase="research" if requires_fact_verification else "skill_match",
            heartbeat_title="等待 Codex 完成核验与结构设计",
            process_timeout_seconds=180.0,
        )
    except (ValidationError, Exception) as exc:
        if config.mode == "required":
            raise
        fact_verification = (
            FactVerification(
                required=True,
                verdict="failed",
                claim=claim,
                summary=f"Codex 联网核验失败：{str(exc)[:240]}",
                checked_at=datetime.now(timezone.utc),
            )
            if requires_fact_verification
            else FactVerification(required=False, verdict="not_required")
        )
        return fact_verification, [], [], fallback_status(config, exc)

    fact_output = output.fact_verification
    sources: list[FactSource] = []
    seen_urls: set[str] = set()
    for source in fact_output.sources:
        url = source.url.strip()
        if not url.startswith(("https://", "http://")) or url in seen_urls:
            continue
        seen_urls.add(url)
        sources.append(
            FactSource(
                title=source.title.strip(),
                url=url,
                publisher=source.publisher.strip(),
                published_at=source.published_at,
            )
        )
    if requires_fact_verification:
        verdict_value = fact_output.verdict.strip().lower()
        if fact_output.core_event_verified or verdict_value in {
            "confirmed",
            "true",
            "verified",
            "yes",
            "属实",
        }:
            verdict: Literal["verified", "refuted", "uncertain"] = "verified"
        elif verdict_value in {"refuted", "false", "incorrect", "no", "不实"}:
            verdict = "refuted"
        else:
            verdict = "uncertain"
        if verdict == "verified" and len(sources) < 2:
            verdict = "uncertain"
        fact_verification = FactVerification(
            required=True,
            verdict=verdict,
            claim=fact_output.claim.strip() or claim,
            summary=fact_output.summary.strip(),
            verified_facts=[
                item.strip() for item in fact_output.verified_facts if item.strip()
            ][:10],
            corrections=[
                item.strip() for item in fact_output.corrections if item.strip()
            ][:6],
            sources=sources[:8],
            checked_at=datetime.now(timezone.utc),
        )
    else:
        fact_verification = FactVerification(
            required=False,
            verdict="not_required",
            claim=fact_output.claim.strip(),
            summary=fact_output.summary.strip(),
            verified_facts=[
                item.strip() for item in fact_output.verified_facts if item.strip()
            ][:10],
            sources=sources[:8],
            checked_at=datetime.now(timezone.utc),
        )

    if activity_callback is not None:
        for source in fact_verification.sources[:5]:
            activity_callback(
                {
                    "phase": "research",
                    "kind": "source",
                    "title": "已采纳可靠来源",
                    "detail": f"{source.publisher or source.title} · {source.title}",
                    "status": "completed",
                }
            )
        activity_callback(
            {
                "phase": "research",
                "kind": "check",
                "title": "事实与创作证据包已整理",
                "detail": (
                    f"确认 {len(fact_verification.verified_facts)} 条可写事实，"
                    f"{len(fact_verification.sources)} 个来源。"
                ),
                "status": "completed",
            }
        )

    if requires_fact_verification and fact_verification.verdict != "verified":
        return fact_verification, [], [], success_status(config)

    by_id = {skill.id: skill for skill in candidates}
    matches: list[SkillMatch] = []
    for choice in output.matches:
        skill = by_id.get(choice.skill_id)
        if skill is None:
            continue
        matches.append(
            SkillMatch(
                skill=skill,
                match_score=choice.match_score,
                reason=choice.reason.strip(),
                apply_plan=[item.strip() for item in choice.apply_plan if item.strip()],
            )
        )
    if not matches or len(output.variants) != 3:
        error = RuntimeError("Codex 未返回完整的 Skill 选择和三个结构。")
        return fact_verification, [], [], fallback_status(config, error)

    primary_match = matches[0]
    if activity_callback is not None:
        activity_callback(
            {
                "phase": "skill_match",
                "kind": "skill",
                "title": f"已选用「{primary_match.skill.name}」",
                "detail": primary_match.reason,
                "status": "completed",
            }
        )

    scripts: list[GeneratedScript] = []
    for index, variant in enumerate(output.variants, start=1):
        spoken_script = _structure_workspace_text(
            payload=payload,
            skill=primary_match.skill,
            draft=variant,
            fact_verification=fact_verification,
        )
        scripts.append(
            GeneratedScript(
                id=f"script_{os.urandom(5).hex()}",
                title=variant.title.strip(),
                account_type=payload.account_type,
                content_angle=variant.content_angle.strip(),
                duration_seconds=payload.duration_seconds,
                spoken_script=spoken_script,
                shot_suggestions=variant.shot_suggestions,
                subtitle_rhythm=variant.subtitle_rhythm,
                comment_cta=variant.comment_cta,
                risk_check=risk_check(
                    f"{variant.title} {spoken_script} {variant.comment_cta}"
                ),
                template_used=primary_match.skill.name,
                preset_application=[
                    f"本版重点：{variant.positioning}",
                    f"版本差异：{variant.difference_from_others}",
                    *[f"Skill 应用：{item}" for item in variant.skill_application],
                    *[
                        f"Skill 覆盖：{item.step}｜{item.evidence}"
                        for item in variant.skill_coverage
                    ],
                ],
                version_label=f"V{index}",
            )
        )
        if activity_callback is not None:
            activity_callback(
                {
                    "phase": "writing",
                    "kind": "draft",
                    "title": f"{variant.content_angle.strip()}结构已完成",
                    "detail": (
                        f"{len(''.join(spoken_script.split()))} 字 · {variant.title.strip()}"
                    ),
                    "status": "completed",
                }
            )
    return fact_verification, matches, scripts, success_status(config)


def generate_rewrite_scripts_structured(
    payload: DraftInputRequest,
    diagnosis: DraftDiagnosis,
    matches: list[SkillMatch],
    fact_verification: Optional[FactVerification] = None,
    activity_callback: Optional[ActivityCallback] = None,
) -> tuple[list[GeneratedScript], LLMCallStatus]:
    config = get_llm_config()
    if config.mode == "offline" or not matches:
        return [], disabled_status(config)

    primary_match = matches[0]
    skill = primary_match.skill
    target_min_chars = max(100, min(900, round(payload.duration_seconds * 4.5)))
    target_max_chars = max(
        target_min_chars + 30,
        min(1100, round(payload.duration_seconds * 5.3)),
    )
    repair_min_chars = max(80, min(760, round(payload.duration_seconds * 3.5)))
    repair_max_chars = max(
        repair_min_chars + 60,
        min(1300, round(payload.duration_seconds * 6.5)),
    )
    fact_verification = fact_verification or FactVerification()
    requires_fact_verification = fact_verification_required(payload)
    verified_fact_context = {
        "verdict": fact_verification.verdict,
        "summary": fact_verification.summary,
        "verified_facts": fact_verification.verified_facts,
        "corrections": fact_verification.corrections,
        "sources": [
            source.model_dump(mode="json") for source in fact_verification.sources
        ],
    }
    fact_instruction = (
        "Codex 已联网交叉核验该重大事实，结论为 verified。把证据包中已经确认的事实直接"
        "作为结构素材，不要再写‘尚待核实’或‘如果属实’，也不得扩写证据包之外的细节。"
        if fact_verification.verdict == "verified"
        else "不得补写用户未提供且没有公开证据支持的当前事件细节。"
    )
    skill_context = {
        "name": skill.name,
        "solves_problems": skill.solves_problems,
        "skeleton": skill.skeleton,
        "hook_formula": skill.hook_formula,
        "emotion_rhythm": skill.emotion_rhythm,
        "ending_formula": skill.ending_formula,
        "risk_boundary": skill.risk_boundary,
        "match_reason": primary_match.reason,
        "apply_plan": primary_match.apply_plan,
    }
    diagnosis_context = {
        "strengths": diagnosis.strengths,
        "problems": diagnosis.problems,
        "rewrite_goals": diagnosis.rewrite_goals,
        "no_go_zones": diagnosis.no_go_zones,
    }
    messages = [
        {
            "role": "system",
            "content": (
                "你是资深短视频主编。请把用户输入设计成可填写的文本结构，而不是直接替用户写完整口播成稿。"
                "必须深度使用给定 Writing Skill 的结构、钩子、情绪节奏和收束方式，但不能混用多个"
                "Skill 骨架。三个结构必须有实质差异：开头策略、证据顺序、情绪曲线、核心判断和"
                "结尾至少三项不同，不能只替换版本名称。spoken_script 字段只承载结构说明、段落目标、"
                "写作建议、可用素材和互动问题，不输出最终发布稿。"
                "每个结构先形成一个具体、可争辩的中心判断，再规划至少3组具体材料推进，其中至少2组"
                "应优先使用作品层材料；不能只罗列出生、获奖、销量和书名。每次提到作品都要说明它"
                "应如何支撑本版判断或触发观众记忆。禁止用‘陪伴很多人’‘留下宝贵作品’这类"
                "空泛句子代替待填写细节。"
                "不得编造未提供的具体事实、数字、引语或经历；用户输入中的重大事实若缺少证据，"
                "不得当作已证实事实。核实限制必须直接体现在结构标题和填写建议里，不能只写进策略说明。"
                "根据输入时效和受众上下文决定前情篇幅：热点受众通常已经知道核心事件，除非日期"
                "本身需要纠错或是本版论点，否则开头不要先播报具体日期、年龄和‘官方已确认’，"
                "最多用一个短分句交代事件，立即进入观众不知道的新细节、冲突或判断。"
                "结构按口播逻辑分成3-5个自然段；段落分别承担钩子、推进、转折和收束，"
                "每段都要说明用户应填写什么、为什么这样写。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"输入类型：{payload.input_type}\n标题：{payload.title}\n"
                f"用户素材：{payload.content}\n账号：{payload.account_type}\n"
                f"目标时长：约 {payload.duration_seconds} 秒，建议参考 "
                f"{target_min_chars}-{target_max_chars} 字。内容完整、节奏和情绪成立优先，允许"
                "合理超出或低于建议区间，不要为了凑字数重复信息\n"
                f"语气：{payload.tone}\n传播目标：{payload.goal}\n"
                f"稿件诊断：{json.dumps(diagnosis_context, ensure_ascii=False)}\n"
                f"必须使用的 Writing Skill：{json.dumps(skill_context, ensure_ascii=False)}\n\n"
                f"事实核验结果：{json.dumps(verified_fact_context, ensure_ascii=False)}\n"
                f"事实约束：{fact_instruction}\n\n"
                "请根据用户意图和已核实材料设计 3 个真正不同的创作方向，不要固定套用"
                "‘事实叙事/情绪共鸣/观点升维’。content_angle 用2-6个字准确命名本版切口；"
                "至少一版从具体瞬间或观众记忆直接切入，至少一版写透人物选择或作品困境，"
                "至少一版提出可争辩的新判断。"
                "每个方向都必须是一份独立、可填写的结构工作稿。positioning 用一句话说明本版"
                "最适合什么发布意图；difference_from_others 说明它和另外两版最关键的差异；"
                "skill_application 只写 2-4 条本版具体用了 Skill 的哪里。skill_coverage 必须按"
                "Writing Skill 的 skeleton 顺序逐步列出，每一项写清对应步骤里用户应填写什么内容；"
                "不能用泛泛的‘使用了钩子’代替。结构也必须遵循同一顺序。"
            ),
        },
    ]
    try:
        output = structured_completion(
            StructuredDraftRewriteOutput,
            messages,
            config,
            activity_callback=activity_callback,
            activity_phase="writing",
        )
    except (ValidationError, Exception) as exc:
        if config.mode == "required":
            raise
        return [], fallback_status(config, exc)

    outside_length_range = [
        variant
        for variant in output.variants
        if not (
            repair_min_chars
            <= len("".join(variant.spoken_script.split()))
            <= repair_max_chars
        )
    ]
    if outside_length_range:
        if activity_callback is not None:
            activity_callback(
                {
                    "phase": "writing",
                    "kind": "check",
                    "title": "结构信息量明显偏离，正在校正",
                    "detail": (
                        f"{len(outside_length_range)}/3 版超出 {repair_min_chars}-{repair_max_chars} 字的"
                        "宽容范围，Codex 将优先修复结构信息密度和完整性。"
                    ),
                    "status": "active",
                }
            )
        repair_messages = [
            {
                "role": "system",
                "content": (
                    "你是短视频结构质量编辑。只修复结构信息量和内容深度，不改变三版方向、已核实事实、"
                    "中心判断和 Writing Skill 顺序。过短结构必须通过补充证据包里已有的具体场景、"
                    "人物处境、选择、后果和观众联想来增强填写建议，不能重复原句、堆书名奖项或写成"
                    "最终口播稿。过长结构则删除重复。不得新增证据包之外的事实。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"每版结构说明应回到 {repair_min_chars}-{repair_max_chars} 字的宽容范围，理想参考"
                    f"仍是 {target_min_chars}-{target_max_chars} 字；完整和自然优先，不得重复凑字，也不得写成最终口播稿。\n"
                    f"Writing Skill：{json.dumps(skill_context, ensure_ascii=False)}\n"
                    f"已核实证据包：{json.dumps(verified_fact_context, ensure_ascii=False)}\n"
                    f"待修订三版：{json.dumps(output.model_dump(), ensure_ascii=False)}\n"
                    "保持原有 title、content_angle、positioning 和 difference_from_others 的方向；"
                    "返回完整的三个版本对象。"
                ),
            },
        ]
        try:
            output = structured_completion(
                StructuredDraftRewriteOutput,
                repair_messages,
                config,
                activity_callback=activity_callback,
                activity_phase="writing",
            )
        except (ValidationError, Exception):
            pass

    if requires_fact_verification and fact_verification.verdict != "verified":
        verification_markers = [
            "未证实",
            "尚无可靠",
            "仍需核实",
            "仍待核实",
            "以权威",
            "如果消息属实",
        ]
        unsafe_variants = [
            variant
            for variant in output.variants
            if not any(
                marker in f"{variant.title} {variant.spoken_script}"
                for marker in verification_markers
            )
        ]
        if unsafe_variants:
            return [], LLMCallStatus(
                used_model=True,
                mode=config.mode,
                model=config.model,
                error="FACT_GUARD: model treated an unsupported major claim as confirmed.",
            )

    scripts: list[GeneratedScript] = []
    for index, variant in enumerate(output.variants, start=1):
        spoken_script = _structure_workspace_text(
            payload=payload,
            skill=skill,
            draft=variant,
            fact_verification=fact_verification,
        )
        risk_source = f"{variant.title} {spoken_script} {variant.comment_cta}"
        if requires_fact_verification and fact_verification.verdict != "verified":
            risk_source = f"未经证实 {risk_source}"
        scripts.append(
            GeneratedScript(
                id=f"script_{os.urandom(5).hex()}",
                title=variant.title,
                account_type=payload.account_type,
                content_angle=variant.content_angle.strip(),
                duration_seconds=payload.duration_seconds,
                spoken_script=spoken_script,
                shot_suggestions=variant.shot_suggestions,
                subtitle_rhythm=variant.subtitle_rhythm,
                comment_cta=variant.comment_cta,
                risk_check=risk_check(risk_source),
                template_used=skill.name,
                preset_application=[
                    f"本版重点：{variant.positioning}",
                    f"版本差异：{variant.difference_from_others}",
                    *[f"Skill 应用：{item}" for item in variant.skill_application],
                    *[
                        f"Skill 覆盖：{item.step}｜{item.evidence}"
                        for item in variant.skill_coverage
                    ],
                ],
                version_label=f"V{index}",
            )
        )
        if activity_callback is not None:
            spoken_count = len("".join(spoken_script.split()))
            activity_callback(
                {
                    "phase": "writing",
                    "kind": "draft",
                    "title": f"{variant.content_angle.strip()}结构已完成",
                    "detail": f"{spoken_count} 字 · {variant.title}",
                    "status": "completed",
                }
            )
    return scripts, success_status(config)


def rewrite_selected_passage_structured(
    *,
    selected_text: str,
    instruction: str,
    full_script: str,
    account_type: str,
    duration_seconds: int,
    tone: str,
    skill_name: str,
    verified_facts: list[str],
    verified_sources: Optional[list[FactSource]] = None,
    rewrite_intents: Optional[list[str]] = None,
    research_mode: Literal["none", "targeted"] = "none",
    emotional_goal: str = "",
) -> StructuredSelectionRewriteOutput:
    config = get_llm_config()
    if config.mode == "offline":
        raise RuntimeError("Codex 当前未启用，无法执行局部改写。")

    targeted_research = research_mode == "targeted"
    research_instruction = (
        "必须先实际联网检索与选中片段直接相关的可靠来源，再写替换文本。"
        "只选 1-2 个最能形成情绪因果的细节：具体场景 -> 当时的压力、选择或失去 -> "
        "产生的后果 -> 观众为什么会在这里认出自己的感受。不要堆奖项、销量、书名和冷知识；"
        "除非它们能直接证明中心判断。不得编造心理活动、对话和引语。"
        if targeted_research
        else "不得新增已核实材料之外的具体日期、数字、引语、情节或人物经历。"
    )
    source_context = [
        source.model_dump(mode="json") for source in (verified_sources or [])
    ]
    messages = [
        {
            "role": "system",
            "content": (
                "你是短视频口播稿编辑。只重写用户选中的片段，不改动片段之外的正文。"
                "改写必须承接上下文、保持人物与时间线一致，并服从用户的具体修改要求。"
                f"{research_instruction}"
                "每一个新增事实都必须回答‘这个细节揭示了什么人的处境或选择’，宁可完整写透"
                "一个场景，也不要浅写三个事实。"
                "输出 replacement 时不要加引号、标题、解释或 Markdown。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"账号类型：{account_type}\n目标时长：{duration_seconds}秒\n"
                f"整体语气：{tone}\n采用 Skill：{skill_name}\n"
                f"已核实材料：{json.dumps(verified_facts, ensure_ascii=False)}\n\n"
                f"已有来源：{json.dumps(source_context, ensure_ascii=False)}\n"
                f"完整文本上下文：\n{full_script}\n\n"
                f"选中片段：\n{selected_text}\n\n"
                f"已选择修改意图：{json.dumps(rewrite_intents or [], ensure_ascii=False)}\n"
                f"情绪目标：{emotional_goal or '保持真实、具体、克制'}\n"
                f"修改要求：{instruction}\n\n"
                "replacement 只返回可原位替换的口播文字；change_summary 用一句话说明改了什么；"
                "supporting_facts 只列出 replacement 实际使用的事实；sources 只返回实际打开并用于"
                "改写的来源。没有新研究时可以返回空数组。"
            ),
        },
    ]
    return structured_completion(
        StructuredSelectionRewriteOutput,
        messages,
        config,
        allow_web_search=targeted_research,
    )


def suggest_selection_rewrites_structured(
    *,
    selected_text: str,
    full_script: str,
    account_type: str,
    duration_seconds: int,
    tone: str,
    skill_name: str,
    verified_facts: list[str],
) -> StructuredRewriteSuggestionOutput:
    config = get_llm_config()
    if config.mode == "offline":
        raise RuntimeError("Codex 当前未启用，无法生成局部改写建议。")
    messages = [
        {
            "role": "system",
            "content": (
                "你是短视频主编。根据用户实际选中的文字，提出 3-5 个互不重复、可以组合执行的"
                "局部改写动作。不能返回固定套话；label 要短，instruction 要具体到这段文字，"
                "reason 要说明这段当前缺了什么。如果建议需要新增作品情节、人物经历、日期、数字"
                "或引语，evidence_needed 必须为 true；纯节奏、措辞、结构修改则为 false。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"账号：{account_type}\n目标时长：{duration_seconds}秒\n语气：{tone}\n"
                f"当前 Skill：{skill_name}\n已核实事实：{json.dumps(verified_facts, ensure_ascii=False)}\n\n"
                f"完整文本上下文：\n{full_script}\n\n选中片段：\n{selected_text}\n\n"
                "建议必须直接针对选中片段，例如指出应补哪类场景、压缩哪种重复、深化哪一个判断。"
            ),
        },
    ]
    return structured_completion(StructuredRewriteSuggestionOutput, messages, config)


def deterministic_hotspot(
    hotspot: str,
    account_type: str,
    duration_seconds: int,
    tone: str,
    goal: str,
    template_id: Optional[str],
) -> StructuredHotspotResult:
    config = get_llm_config()
    matched = match_templates(account_type, hotspot)
    selected_template = pick_template_by_id(template_id, account_type)
    if selected_template.id not in {template.id for template in matched}:
        matched.insert(0, selected_template)
    brief = HotspotBrief(
        id="",
        event_summary=hotspot,
        controversy="争议集中在事实边界、公众情绪和表达态度。",
        audience_emotion="好奇、站队、质疑、求证。",
        angles=["细节反差", "公众情绪", "传播逻辑", "关系议题"],
        no_go_zones=["未经证实的爆料", "隐私细节", "攻击性站队", "绝对化定性"],
    )
    scripts = [
        build_script(
            hotspot,
            account_type,
            duration_seconds,
            tone,
            goal,
            template=selected_template,
            variant=index,
        )
        for index in range(1, 4)
    ]
    return StructuredHotspotResult(
        brief=brief,
        scripts=scripts,
        matched_templates=matched[:3],
        status=disabled_status(config),
    )


def generate_hotspot_structured(
    hotspot: str,
    account_type: str,
    duration_seconds: int,
    tone: str,
    goal: str,
    template_id: Optional[str],
) -> StructuredHotspotResult:
    config = get_llm_config()
    if config.mode == "offline":
        return deterministic_hotspot(
            hotspot,
            account_type,
            duration_seconds,
            tone,
            goal,
            template_id,
        )

    matched = match_templates(account_type, hotspot)
    selected_template = pick_template_by_id(template_id, account_type)
    if selected_template.id not in {template.id for template in matched}:
        matched.insert(0, selected_template)
    template_context = json.dumps(selected_template.model_dump(), ensure_ascii=False)
    messages = [
        {
            "role": "system",
            "content": (
                "你是依旧沉淀短视频写作 Skill 工作台。基于用户提供的热点和模板生成可拍摄脚本。"
                "必须遵守：不编造事实，不输出隐私、人身攻击、恶意引战、未成年人高敏内容；"
                "只学习结构，不仿写原文。输出必须符合 schema。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"热点：{hotspot}\n账号类型：{account_type}\n时长：{duration_seconds} 秒\n"
                f"语气：{tone}\n传播目标：{goal}\n套用写作预设：{template_context}\n"
                "请先给事件 brief，再生成 3-5 个不同内容角度的脚本。"
            ),
        },
    ]
    try:
        output = structured_completion(StructuredHotspotOutput, messages, config)
        return StructuredHotspotResult(
            brief=output.brief,
            scripts=output.scripts,
            matched_templates=matched[:3],
            status=success_status(config),
        )
    except (ValidationError, Exception) as exc:
        if config.mode == "required":
            raise
        result = deterministic_hotspot(
            hotspot,
            account_type,
            duration_seconds,
            tone,
            goal,
            template_id,
        )
        result.status = fallback_status(config, exc)
        return result
