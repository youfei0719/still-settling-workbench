import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.script_workbench import (
    AnalyzeTextRequest,
    AnalyzeTextResponse,
    CodexSkillPackResponse,
    CodexSkillPublishResponse,
    DraftDiagnosis,
    DraftInputRequest,
    DraftRewriteRequest,
    DraftRewriteResponse,
    DraftRewriteTask,
    ExternalGateReport,
    GeneratedScript,
    GeneratedScriptUpdateRequest,
    GenerateHotspotRequest,
    GenerateHotspotResponse,
    HumanReviewTemplateResponse,
    HumanReviewUpdateRequest,
    LinkDiagnosticRecord,
    LinkTaskResponse,
    LocalSettingsStatus,
    LocalSettingsUpdateRequest,
    LocalSettingsVerification,
    ModelCatalogResponse,
    ModelConnectionCheckResponse,
    GitHubRepositoryConnectRequest,
    GitHubRepositoryCreateRequest,
    LocalRepositoryCreateRequest,
    SkillRepositorySetupResponse,
    ModelRuntimeStatus,
    ModelWarmupRequest,
    ModelWarmupResponse,
    SelectionRewriteRequest,
    SelectionRewriteResponse,
    SelectionRewriteSuggestion,
    SelectionRewriteSuggestionRequest,
    SelectionRewriteSuggestionResponse,
    SkillMatch,
    SkillGovernanceUpdateRequest,
    SkillApprovalAndPublishResponse,
    SkillPromotionReadiness,
    SkillReleaseEvaluationResponse,
    TemplatePattern,
    TemplateReviewUpdateRequest,
    UploadTextRequest,
    VideoExtractionTask,
    VideoUploadResponse,
    WorkbenchCapabilities,
    WorkbenchOverview,
    WritingPresetCreateRequest,
    build_codex_skill_pack,
    capabilities,
    compact_rewrite_facts,
    connect_github_skill_repository,
    copy_generated_script,
    copy_generated_script_version,
    create_draft_rewrite_task,
    create_github_skill_repository,
    create_text_analysis,
    create_upload_text_analysis,
    create_writing_preset_from_draft,
    create_local_skill_repository,
    deduplicate_templates,
    discover_configured_models,
    diagnose_draft,
    external_gate_report,
    generate_hotspot,
    get_draft_rewrite_task,
    list_link_diagnostics,
    match_writing_skills,
    media_root,
    model_runtime_status,
    overview,
    publishable_skill_templates,
    skill_promotion_readiness,
    skill_promotion_errors,
    read_human_review_template,
    read_local_skill_templates,
    publish_codex_skill_pack_to_github,
    run_skill_release_evaluation,
    rewrite_draft,
    risk_check,
    local_settings_status,
    update_local_settings,
    test_configured_model_connection,
    verify_local_settings,
    safe_file_name,
    save_human_review_template,
    sort_skill_templates,
    update_generated_script,
    update_template_review,
    update_skill_governance,
    apply_skill_governance,
    upsert_local_skill_template,
    warmup_models,
    write_human_review_template,
)
from app.workbench_llm import LLMRuntimeConfig, get_llm_config


def require_loopback(request: Request) -> None:
    host = request.client.host if request.client else ""
    if host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        raise HTTPException(status_code=403, detail="工作台仅允许从本机访问。")


# Local development only accepts loopback requests. In production the workbench
# is a CPM feature, so every request is validated against the CPM login API.
router_dependencies = [Depends(require_loopback)]
if os.getenv("ENVIRONMENT", "local").strip().lower() != "local":
    from app.api.deps import get_current_cpm_user

    router_dependencies = [Depends(get_current_cpm_user)]

router = APIRouter(
    prefix="/script-workbench",
    tags=["script-workbench"],
    dependencies=router_dependencies,
)


VIDEO_UPLOAD_CONTENT_TYPES = {
    "application/octet-stream",
    "video/mp4",
    "video/quicktime",
    "video/webm",
    "video/x-matroska",
}
VIDEO_UPLOAD_EXTENSIONS = {".m4v", ".mkv", ".mov", ".mp4", ".webm"}
DEFAULT_MAX_VIDEO_UPLOAD_BYTES = 512 * 1024 * 1024


def max_video_upload_bytes() -> int:
    configured = os.getenv("WORKBENCH_MAX_VIDEO_UPLOAD_BYTES", "").strip()
    if not configured:
        return DEFAULT_MAX_VIDEO_UPLOAD_BYTES
    try:
        return max(1, int(configured))
    except ValueError:
        return DEFAULT_MAX_VIDEO_UPLOAD_BYTES


def video_upload_limit_label(limit: int) -> str:
    return f"{max(1, (limit + 1024 * 1024 - 1) // (1024 * 1024))} MB"


def validate_video_upload(request: Request, file_name: str) -> tuple[str, str, int]:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    if content_type not in VIDEO_UPLOAD_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="仅支持 MP4、MOV、M4V、MKV 或 WebM 视频文件。",
        )
    safe_name = safe_file_name(file_name)
    extension = Path(safe_name).suffix.lower()
    if extension not in VIDEO_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="视频文件扩展名不受支持。",
        )
    limit = max_video_upload_bytes()
    declared_size = request.headers.get("content-length")
    if declared_size:
        try:
            if int(declared_size) > limit:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"视频文件不能超过 {video_upload_limit_label(limit)}。",
                )
        except ValueError:
            raise HTTPException(status_code=400, detail="无效的视频文件大小。") from None
    return safe_name, extension, limit


async def save_video_upload(request: Request, *, file_name: str) -> tuple[Path, str]:
    safe_name, extension, limit = validate_video_upload(request, file_name)
    source_id = safe_file_name(Path(safe_name).stem)
    video_dir = media_root() / "videos"
    video_dir.mkdir(parents=True, exist_ok=True)
    temporary_path = video_dir / f".{source_id}-{uuid4().hex}.uploading"
    total_bytes = 0
    try:
        with temporary_path.open("xb") as output:
            async for chunk in request.stream():
                total_bytes += len(chunk)
                if total_bytes > limit:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"视频文件不能超过 {video_upload_limit_label(limit)}。",
                    )
                output.write(chunk)
        if total_bytes == 0:
            raise HTTPException(status_code=400, detail="视频文件为空。")
        material_path = video_dir / f"{source_id}-{uuid4().hex[:8]}-{total_bytes}{extension}"
        temporary_path.replace(material_path)
        return material_path, safe_name
    except HTTPException:
        temporary_path.unlink(missing_ok=True)
        raise
    except OSError as exc:
        temporary_path.unlink(missing_ok=True)
        raise HTTPException(status_code=507, detail="无法保存视频文件。") from exc


@contextmanager
def optional_database_session() -> Iterator[Optional[Any]]:
    if (
        os.getenv("WORKBENCH_ENABLE_PERSISTENCE", "").strip() != "1"
        or os.getenv("WORKBENCH_DB_MODE", "off").strip().lower() == "off"
    ):
        yield None
        return
    try:
        from sqlmodel import Session

        from app.core.db import engine
    except Exception:
        yield None
        return
    with Session(engine) as session:
        yield session


def persisted_overview_or_fallback() -> WorkbenchOverview:
    def with_local_templates(data: WorkbenchOverview) -> WorkbenchOverview:
        templates = sort_skill_templates(
            deduplicate_templates([*read_local_skill_templates(), *data.templates])
        )
        return data.model_copy(update={"templates": templates[:20]})

    with optional_database_session() as session:
        if session is None:
            return with_local_templates(overview())
        try:
            from app.workbench_persistence import overview_from_database

            data = overview_from_database(session)
            if data.templates or data.recent_analyses or data.generated_scripts:
                return with_local_templates(data)
        except Exception:
            return with_local_templates(overview())
    return with_local_templates(overview())


def persist_link_task_if_available(response: LinkTaskResponse) -> None:
    with optional_database_session() as session:
        if session is None:
            return
        try:
            from app.workbench_persistence import save_link_task_response

            save_link_task_response(session, response)
        except Exception:
            return


def persist_analysis_if_available(response: AnalyzeTextResponse) -> None:
    with optional_database_session() as session:
        if session is None:
            return
        try:
            from app.workbench_persistence import save_analysis_response

            save_analysis_response(session, response)
        except Exception:
            return


def persist_hotspot_if_available(response: GenerateHotspotResponse) -> None:
    with optional_database_session() as session:
        if session is None:
            return
        try:
            from app.workbench_persistence import save_hotspot_response

            save_hotspot_response(session, response)
        except Exception:
            return


def persist_template_if_available(template: TemplatePattern) -> None:
    try:
        upsert_local_skill_template(template)
    except Exception:
        pass
    with optional_database_session() as session:
        if session is None:
            return
        try:
            from app.workbench_persistence import save_template_pattern

            save_template_pattern(session, template)
        except Exception:
            return


def persist_script_if_available(script: GeneratedScript) -> None:
    with optional_database_session() as session:
        if session is None:
            return
        try:
            from app.workbench_persistence import save_generated_script

            save_generated_script(session, script)
        except Exception:
            return


@router.get("/overview", response_model=WorkbenchOverview)
def read_overview() -> Any:
    return persisted_overview_or_fallback()


@router.get("/llm-status", response_model=LLMRuntimeConfig)
def read_llm_status() -> Any:
    config = get_llm_config()
    sources = local_settings_status().sources
    if sources.get("llm_api_base") == "environment":
        config = config.model_copy(update={"api_base": None})
    return config


@router.get("/capabilities", response_model=WorkbenchCapabilities)
def read_capabilities() -> Any:
    return capabilities()


@router.get("/external-gates", response_model=ExternalGateReport)
def read_external_gates(
    link: Optional[str] = Query(default=None),
    run_link: bool = Query(default=False),
    expect_model: bool = Query(default=False),
) -> Any:
    return external_gate_report(link=link, run_link=run_link, expect_model=expect_model)


@router.get("/local-settings", response_model=LocalSettingsStatus)
def read_local_settings() -> Any:
    return local_settings_status()


@router.put("/local-settings", response_model=LocalSettingsStatus)
def save_local_settings_endpoint(
    payload: LocalSettingsUpdateRequest,
) -> Any:
    return update_local_settings(payload)


@router.post("/local-settings/verify", response_model=LocalSettingsVerification)
def verify_local_settings_endpoint() -> Any:
    return verify_local_settings()


@router.post("/local-settings/models", response_model=ModelCatalogResponse)
def discover_local_models() -> Any:
    return discover_configured_models()


@router.post("/local-settings/test-model", response_model=ModelConnectionCheckResponse)
def test_local_model() -> Any:
    return test_configured_model_connection()


@router.post("/local-settings/connect-github", response_model=SkillRepositorySetupResponse)
def connect_github_repository(
    payload: GitHubRepositoryConnectRequest,
) -> Any:
    try:
        return connect_github_skill_repository(payload)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/local-settings/create-github", response_model=SkillRepositorySetupResponse)
def create_github_repository(
    payload: GitHubRepositoryCreateRequest,
) -> Any:
    try:
        return create_github_skill_repository(payload)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/local-settings/create-local", response_model=SkillRepositorySetupResponse)
def create_local_repository(
    payload: LocalRepositoryCreateRequest,
) -> Any:
    try:
        return create_local_skill_repository(payload)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/human-review-template", response_model=HumanReviewTemplateResponse)
def create_human_review_template() -> Any:
    current_overview = persisted_overview_or_fallback()
    items = write_human_review_template(scripts=current_overview.generated_scripts[:10])
    return HumanReviewTemplateResponse(
        path="",
        required_count=10,
        items=items,
        message="已生成 10 条热点脚本人审模板。",
    )


@router.get("/human-review-template", response_model=HumanReviewTemplateResponse)
def read_human_review_template_file() -> Any:
    try:
        items = read_human_review_template()
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return HumanReviewTemplateResponse(
        path="",
        required_count=10,
        items=items,
        message="已读取当前人审模板。" if items else "尚未生成人审模板。",
    )


@router.put("/human-review-template", response_model=HumanReviewTemplateResponse)
def update_human_review_template_file(payload: HumanReviewUpdateRequest) -> Any:
    items = save_human_review_template(payload.items)
    return HumanReviewTemplateResponse(
        path="",
        required_count=10,
        items=items,
        message="人工质量复核已保存。",
    )


@router.get("/model-status", response_model=ModelRuntimeStatus)
def read_model_status() -> Any:
    return model_runtime_status()


@router.post("/model-warmup", response_model=ModelWarmupResponse)
def warmup_model_runtime(payload: ModelWarmupRequest) -> Any:
    return warmup_models(payload)


@router.post("/link-task", response_model=LinkTaskResponse)
def submit_link_task() -> Any:
    raise HTTPException(
        status_code=410,
        detail=(
            "云端媒体提取已关闭。请使用本机连接器完成下载和转写；"
            "服务器只接收文稿、分析结果和 Skill 历史。"
        ),
    )


@router.get("/link-diagnostics", response_model=list[LinkDiagnosticRecord])
def read_link_diagnostics(limit: int = Query(default=20, ge=1, le=100)) -> Any:
    return list_link_diagnostics(limit=limit)


@router.post("/analyze-text", response_model=AnalyzeTextResponse)
def analyze_text(payload: AnalyzeTextRequest) -> Any:
    response = create_text_analysis(payload, persisted_overview_or_fallback().templates)
    persist_analysis_if_available(response)
    return response


@router.post("/inspirations/analyze", response_model=AnalyzeTextResponse)
def analyze_inspiration(payload: AnalyzeTextRequest) -> Any:
    response = create_text_analysis(payload, persisted_overview_or_fallback().templates)
    persist_analysis_if_available(response)
    return response


@router.post("/upload-text", response_model=AnalyzeTextResponse)
def upload_text(payload: UploadTextRequest) -> Any:
    response = create_upload_text_analysis(
        payload, persisted_overview_or_fallback().templates
    )
    persist_analysis_if_available(response)
    return response


@router.post("/upload-video", response_model=VideoUploadResponse)
async def upload_video() -> Any:
    raise HTTPException(
        status_code=410,
        detail=(
            "云端视频上传已关闭。请由本机连接器完成下载和转写后提交文稿；"
            "服务器不会保存视频、音频或浏览器会话。"
        ),
    )


@router.post("/video-extraction-tasks/{source_video_id}", response_model=VideoExtractionTask)
def start_video_extraction_task() -> Any:
    raise HTTPException(
        status_code=410,
        detail="云端视频提取已关闭。请使用本机连接器完成转写后提交文稿。",
    )


@router.get("/video-extraction-tasks", response_model=list[VideoExtractionTask])
def read_video_extraction_tasks(_limit: int = Query(default=20, ge=1, le=100)) -> Any:
    raise HTTPException(
        status_code=410,
        detail="云端视频提取已关闭，服务器不再保存或处理媒体任务。",
    )


@router.get("/video-extraction-tasks/{task_id}", response_model=VideoExtractionTask)
def read_video_extraction_task(_task_id: str) -> Any:
    raise HTTPException(
        status_code=410,
        detail="云端视频提取已关闭，服务器不再保存或处理媒体任务。",
    )


@router.post(
    "/video-extraction-tasks/{task_id}/cancel", response_model=VideoExtractionTask
)
def cancel_extraction_task(_task_id: str) -> Any:
    raise HTTPException(
        status_code=410,
        detail="云端视频提取已关闭，服务器不再保存或处理媒体任务。",
    )


@router.post(
    "/video-extraction-tasks/{task_id}/retry", response_model=VideoExtractionTask
)
def retry_extraction_task(_task_id: str) -> Any:
    raise HTTPException(
        status_code=410,
        detail="云端视频提取已关闭。请使用本机连接器重新下载并转写。",
    )


@router.post("/generate-hotspot", response_model=GenerateHotspotResponse)
def create_hotspot_scripts(payload: GenerateHotspotRequest) -> Any:
    try:
        response = generate_hotspot(payload)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    persist_hotspot_if_available(response)
    return response


@router.post("/writing-presets", response_model=TemplatePattern)
def create_writing_preset(payload: WritingPresetCreateRequest) -> Any:
    template = create_writing_preset_from_draft(
        payload, persisted_overview_or_fallback().templates
    )
    persist_template_if_available(template)
    return template


@router.get("/writing-skills", response_model=list[TemplatePattern])
def read_writing_skills(status: str | None = Query(default=None)) -> Any:
    templates = persisted_overview_or_fallback().templates
    return [template for template in templates if status is None or template.status == status]


@router.get("/writing-skills/{template_id}", response_model=TemplatePattern)
def read_writing_skill(template_id: str) -> Any:
    template = next(
        (item for item in persisted_overview_or_fallback().templates if item.id == template_id),
        None,
    )
    if template is None:
        raise HTTPException(status_code=404, detail="Skill 不存在。")
    return template


@router.get("/codex-skill-pack", response_model=CodexSkillPackResponse)
def read_codex_skill_pack() -> Any:
    return build_codex_skill_pack(
        publishable_skill_templates(persisted_overview_or_fallback().templates)
    )


@router.post("/codex-skill-pack/publish-github", response_model=CodexSkillPublishResponse)
def publish_codex_skill_pack() -> Any:
    try:
        skill_pack = build_codex_skill_pack(
            publishable_skill_templates(persisted_overview_or_fallback().templates)
        )
        return publish_codex_skill_pack_to_github(skill_pack)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/writing-skills", response_model=TemplatePattern)
def create_writing_skill(payload: WritingPresetCreateRequest) -> Any:
    template = create_writing_preset_from_draft(
        payload, persisted_overview_or_fallback().templates
    )
    persist_template_if_available(template)
    return template


@router.post("/drafts/diagnose", response_model=DraftDiagnosis)
def diagnose_user_draft(payload: DraftInputRequest) -> Any:
    return diagnose_draft(payload)


@router.post("/drafts/match-skills", response_model=list[SkillMatch])
def match_user_draft_skills(payload: DraftRewriteRequest) -> Any:
    return match_writing_skills(
        payload, payload.skill_ids, persisted_overview_or_fallback().templates
    )


@router.post("/drafts/rewrite", response_model=DraftRewriteResponse)
def rewrite_user_draft(payload: DraftRewriteRequest) -> Any:
    response = rewrite_draft(payload, persisted_overview_or_fallback().templates)
    for script in response.scripts:
        persist_script_if_available(script)
    return response


def persist_draft_rewrite_response(response: DraftRewriteResponse) -> None:
    for script in response.scripts:
        persist_script_if_available(script)


@router.post("/drafts/rewrite-tasks", response_model=DraftRewriteTask)
def start_user_draft_rewrite(payload: DraftRewriteRequest) -> Any:
    return create_draft_rewrite_task(
        payload,
        persisted_overview_or_fallback().templates,
        on_complete=persist_draft_rewrite_response,
    )


@router.get("/drafts/rewrite-tasks/{task_id}", response_model=DraftRewriteTask)
def read_user_draft_rewrite(task_id: str) -> Any:
    try:
        return get_draft_rewrite_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="未找到结构生成任务。") from exc


@router.post("/scripts/selection-rewrite", response_model=SelectionRewriteResponse)
def rewrite_script_selection(payload: SelectionRewriteRequest) -> Any:
    if payload.selected_text not in payload.full_script:
        raise HTTPException(status_code=422, detail="选中的文字已发生变化，请重新选择。")
    from app.workbench_llm import rewrite_selected_passage_structured

    try:
        output = rewrite_selected_passage_structured(
            selected_text=payload.selected_text,
            instruction=payload.instruction,
            full_script=payload.full_script,
            account_type=payload.account_type,
            duration_seconds=payload.duration_seconds,
            tone=payload.tone,
            skill_name=payload.skill_name,
            verified_facts=compact_rewrite_facts(payload.verified_facts),
            verified_sources=payload.verified_sources,
            rewrite_intents=payload.rewrite_intents,
            research_mode=payload.research_mode,
            emotional_goal=payload.emotional_goal,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Codex 局部改写未完成，请保留当前选区后重试。",
        ) from exc
    return SelectionRewriteResponse(
        replacement=output.replacement.strip(),
        change_summary=output.change_summary.strip(),
        supporting_facts=[item.strip() for item in output.supporting_facts if item.strip()],
        sources=[source.model_dump() for source in output.sources],
    )


@router.post(
    "/scripts/selection-rewrite-suggestions",
    response_model=SelectionRewriteSuggestionResponse,
)
def suggest_script_selection_rewrites(
    payload: SelectionRewriteSuggestionRequest,
) -> Any:
    if payload.selected_text not in payload.full_script:
        raise HTTPException(status_code=422, detail="选中的文字已发生变化，请重新选择。")
    from app.workbench_llm import suggest_selection_rewrites_structured

    try:
        output = suggest_selection_rewrites_structured(
            selected_text=payload.selected_text,
            full_script=payload.full_script,
            account_type=payload.account_type,
            duration_seconds=payload.duration_seconds,
            tone=payload.tone,
            skill_name=payload.skill_name,
            verified_facts=compact_rewrite_facts(payload.verified_facts),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Codex 暂时没有返回针对这段文字的建议，你仍可直接输入修改要求。",
        ) from exc
    return SelectionRewriteSuggestionResponse(
        suggestions=[
            SelectionRewriteSuggestion(**item.model_dump())
            for item in output.suggestions
        ]
    )


@router.patch("/templates/{template_id}/review", response_model=TemplatePattern)
def review_template(template_id: str, payload: TemplateReviewUpdateRequest) -> Any:
    with optional_database_session() as session:
        if session is not None:
            try:
                from app.workbench_persistence import update_template_review_record

                updated_from_db = update_template_review_record(
                    session, template_id, payload
                )
                if updated_from_db is not None:
                    try:
                        update_template_review(template_id, payload)
                    except KeyError:
                        pass
                    return updated_from_db
            except Exception:
                pass

    try:
        updated = update_template_review(template_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="模板不存在。") from exc
    persist_template_if_available(updated)
    return updated


@router.patch("/writing-skills/{template_id}/governance", response_model=TemplatePattern)
def govern_writing_skill(template_id: str, payload: SkillGovernanceUpdateRequest) -> Any:
    current = next(
        (item for item in persisted_overview_or_fallback().templates if item.id == template_id),
        None,
    )
    if current is None:
        raise HTTPException(status_code=404, detail="Skill 不存在。")
    try:
        updated = apply_skill_governance(current, payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    with optional_database_session() as session:
        if session is not None:
            try:
                from app.workbench_persistence import save_template_pattern

                save_template_pattern(session, updated)
            except Exception as exc:
                raise HTTPException(
                    status_code=500, detail="Skill 治理状态未能写入数据库。"
                ) from exc
    try:
        update_skill_governance(template_id, payload)
    except KeyError:
        pass
    upsert_local_skill_template(updated)
    return updated


@router.post(
    "/writing-skills/{template_id}/approve-and-publish",
    response_model=SkillApprovalAndPublishResponse,
)
def approve_and_publish_writing_skill(
    template_id: str, payload: SkillGovernanceUpdateRequest
) -> Any:
    """Promote and distribute one Skill as a single user-confirmed operation."""
    current_overview = persisted_overview_or_fallback()
    current = next(
        (item for item in current_overview.templates if item.id == template_id), None
    )
    if current is None:
        raise HTTPException(status_code=404, detail="Skill 不存在。")

    preflight_errors = [
        error
        for error in skill_promotion_errors(current)
        if error
        not in {
            "真实模型发布评测尚未运行。",
            "真实模型发布评测未达到发布门槛。",
            "需要内容主审批准。",
        }
    ]
    if preflight_errors:
        raise HTTPException(status_code=409, detail="；".join(preflight_errors))

    evaluation = run_skill_release_evaluation()
    if not evaluation.passed:
        raise HTTPException(status_code=409, detail=evaluation.message)

    promotion_payload = payload.model_copy(
        update={
            "status": "active",
            "release_report_path": evaluation.report_path,
        }
    )
    try:
        updated = apply_skill_governance(current, promotion_payload)
        next_templates = [
            updated if item.id == template_id else item
            for item in current_overview.templates
        ]
        skill_pack = build_codex_skill_pack(publishable_skill_templates(next_templates))
        publish = publish_codex_skill_pack_to_github(skill_pack)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    with optional_database_session() as session:
        if session is not None:
            try:
                from app.workbench_persistence import save_template_pattern

                save_template_pattern(session, updated)
            except Exception as exc:
                raise HTTPException(
                    status_code=500, detail="GitHub 已同步，但正式状态未能写入数据库。"
                ) from exc
    try:
        update_skill_governance(template_id, promotion_payload)
    except KeyError:
        pass
    upsert_local_skill_template(updated)
    return SkillApprovalAndPublishResponse(skill=updated, publish=publish)


@router.get(
    "/writing-skills/{template_id}/promotion-readiness",
    response_model=SkillPromotionReadiness,
)
def get_writing_skill_promotion_readiness(template_id: str) -> Any:
    current = next(
        (item for item in persisted_overview_or_fallback().templates if item.id == template_id),
        None,
    )
    if current is None:
        raise HTTPException(status_code=404, detail="Skill 不存在。")
    return skill_promotion_readiness(current)


@router.post(
    "/skill-release-evaluation", response_model=SkillReleaseEvaluationResponse
)
def run_writing_skill_release_evaluation() -> Any:
    return run_skill_release_evaluation()


@router.patch("/scripts/{script_id}", response_model=GeneratedScript)
def update_script_production_order(
    script_id: str, payload: GeneratedScriptUpdateRequest
) -> Any:
    with optional_database_session() as session:
        if session is not None:
            try:
                from app.workbench_persistence import update_generated_script_record

                updated_from_db = update_generated_script_record(
                    session,
                    script_id,
                    payload,
                    risk_check(
                        f"{payload.title} {payload.spoken_script} {payload.comment_cta}"
                    ),
                )
                if updated_from_db is not None:
                    try:
                        update_generated_script(script_id, payload)
                    except KeyError:
                        pass
                    return updated_from_db
            except Exception:
                pass

    try:
        updated = update_generated_script(script_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="脚本生产单不存在。") from exc
    persist_script_if_available(updated)
    return updated


@router.post(
    "/scripts/{script_id}/versions/{version_id}/copy", response_model=GeneratedScript
)
def copy_script_version(script_id: str, version_id: str) -> Any:
    with optional_database_session() as session:
        if session is not None:
            try:
                from app.workbench_persistence import (
                    copy_generated_script_version_record,
                )

                copied_from_db = copy_generated_script_version_record(
                    session, script_id, version_id
                )
                if copied_from_db is not None:
                    return copied_from_db
            except Exception:
                pass

    try:
        copied = copy_generated_script_version(script_id, version_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="脚本历史版本不存在。") from exc
    persist_script_if_available(copied)
    return copied


@router.post("/scripts/{script_id}/copy", response_model=GeneratedScript)
def copy_script_production_order(script_id: str) -> Any:
    with optional_database_session() as session:
        if session is not None:
            try:
                from app.workbench_persistence import copy_generated_script_record

                copied_from_db = copy_generated_script_record(session, script_id)
                if copied_from_db is not None:
                    return copied_from_db
            except Exception:
                pass

    try:
        copied = copy_generated_script(script_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="脚本生产单不存在。") from exc
    persist_script_if_available(copied)
    return copied
    (diagnose_draft,)
    (match_writing_skills,)
    (rewrite_draft,)
