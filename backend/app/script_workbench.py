from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from difflib import SequenceMatcher
from importlib.util import find_spec
from pathlib import Path, PurePosixPath
from typing import Callable, Literal, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field

from app.workbench_settings import (
    apply_local_settings_to_environment,
    local_settings_status as read_local_settings_status,
    save_local_settings,
)

apply_local_settings_to_environment()

TaskStatus = Literal["pending", "processing", "completed", "needs_upload", "failed"]
ExtractionTaskStatus = Literal[
    "queued", "processing", "completed", "failed", "cancelled"
]
InputType = Literal["douyin_url", "video", "subtitle", "transcript", "text"]
RiskLevel = Literal["low", "medium", "high"]
ScriptProductionStatus = Literal["draft", "editing", "review_ready", "exported"]
SkillStatus = Literal["candidate", "active", "paused", "retired"]
EvidenceScope = Literal["structure", "fact"]
DouyinParserErrorCode = Literal[
    "downloader_disabled",
    "downloader_missing",
    "public_access_unavailable",
    "cookie_required",
    "timeout",
    "no_media",
    "transcript_quality",
    "unknown",
]


class SourceVideo(BaseModel):
    id: str
    input_type: InputType
    title: str
    url: Optional[str] = None
    author: Optional[str] = None
    publish_time: Optional[str] = None
    status: TaskStatus
    material_path: Optional[str] = None
    created_at: datetime


class Transcript(BaseModel):
    id: str
    source_video_id: str
    asr_text: str = ""
    ocr_text: str = ""
    content_text: str
    timestamps: list[str] = Field(default_factory=list)
    confidence: float = 0.82
    source: str


class TranscriptCorrection(BaseModel):
    original: str
    corrected: str
    reason: str
    confidence: int = Field(default=80, ge=0, le=100)


class ScriptSegment(BaseModel):
    name: str
    start: str
    duration: str
    summary: str


class ScriptAnalysis(BaseModel):
    id: str
    source_video_id: str
    hook: str
    conflict: str
    structure: list[ScriptSegment]
    emotion_curve: list[str]
    reversal: str
    ending_cta: str
    account_type: str
    reusable_template: str
    template_suggestions: list[str]
    content_angle: str


class SkillSourceRecord(BaseModel):
    source_video_id: str
    source_analysis_id: Optional[str] = None
    title: str
    author: Optional[str] = None
    url: Optional[str] = None
    transcript: str = ""
    recognized_at: Optional[datetime] = None


class SkillEvidence(BaseModel):
    id: str = ""
    claim: str = Field(min_length=2, max_length=400)
    source_title: str = Field(min_length=2, max_length=200)
    source_url: str = Field(min_length=8, max_length=500)
    source_type: str = Field(default="user_provided", max_length=80)
    evidence_tier: Literal["A", "B", "C"] = "A"
    quote: str = Field(default="", max_length=600)
    scope: EvidenceScope = "structure"
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SkillEvaluationSummary(BaseModel):
    routing_accuracy: Optional[float] = Field(default=None, ge=0, le=1)
    no_match_accuracy: Optional[float] = Field(default=None, ge=0, le=1)
    safety_block_rate: Optional[float] = Field(default=None, ge=0, le=1)
    citation_coverage: Optional[float] = Field(default=None, ge=0, le=1)
    human_score: Optional[float] = Field(default=None, ge=0, le=5)
    minimum_dimension_score: Optional[float] = Field(default=None, ge=0, le=5)
    passed: bool = False
    report_path: Optional[str] = None
    evaluated_at: Optional[datetime] = None


class SkillReviewRecord(BaseModel):
    id: str = ""
    reviewer: str = Field(default="主审", max_length=120)
    blind_label: str = Field(default="", max_length=32)
    accuracy: int = Field(ge=1, le=5)
    structure: int = Field(ge=1, le=5)
    douyin_fit: int = Field(ge=1, le=5)
    shootability: int = Field(ge=1, le=5)
    distinctiveness: int = Field(ge=1, le=5)
    approved: bool = False
    note: str = Field(default="", max_length=1000)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TemplatePattern(BaseModel):
    id: str
    name: str
    account_type: str
    hotspot_types: list[str]
    solves_problems: list[str] = Field(default_factory=list)
    match_signals: list[str] = Field(default_factory=list)
    applicable_scenes: list[str] = Field(default_factory=list)
    unsuitable_scenes: list[str] = Field(default_factory=list)
    skeleton: list[str]
    hook_formula: str
    emotion_rhythm: str
    ending_formula: str
    risk_boundary: str
    quality_score: int = Field(default=80, ge=0, le=100)
    usage_count: int = 0
    disabled_reason: Optional[str] = None
    last_review_note: Optional[str] = None
    source_analysis_id: Optional[str] = None
    source_titles: list[str] = Field(default_factory=list)
    sources: list[SkillSourceRecord] = Field(default_factory=list)
    source_count: int = Field(default=0, ge=0)
    pattern_fingerprint: str = ""
    status: SkillStatus = "candidate"
    version: int = Field(default=1, ge=1)
    owner: str = Field(default="内容主审", max_length=120)
    platforms: list[str] = Field(default_factory=lambda: ["douyin"])
    reviewed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    required_inputs: list[str] = Field(default_factory=list)
    output_contract: list[str] = Field(default_factory=list)
    promotion_reason: Optional[str] = None
    evidence: list[SkillEvidence] = Field(default_factory=list)
    evaluation_summary: SkillEvaluationSummary = Field(default_factory=SkillEvaluationSummary)
    reviews: list[SkillReviewRecord] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SkillPromotionReadiness(BaseModel):
    template_id: str
    ready: bool
    blockers: list[str] = Field(default_factory=list)
    source_count: int
    required_source_count: int = 3
    evidence_count: int
    has_structure_evidence: bool
    evaluation_passed: bool
    main_review_approved: bool


class SkillReleaseEvaluationResponse(BaseModel):
    passed: bool
    report_path: str
    message: str


class CodexSkillPackResponse(BaseModel):
    skill_name: str
    version: str
    generated_at: datetime
    active_skill_count: int
    total_skill_count: int
    source_count: int
    sync_contract: str
    install_hint: str
    install_manifest: dict[str, object] = Field(default_factory=dict)
    files: dict[str, str]


class CodexSkillPublishResponse(BaseModel):
    status: Literal["published", "unchanged"]
    repository: str
    url: str
    branch: str
    version: str
    commit_sha: Optional[str] = None
    message: str
    files_changed: int = 0


class SkillApprovalAndPublishResponse(BaseModel):
    skill: TemplatePattern
    publish: CodexSkillPublishResponse


class PresetDraft(BaseModel):
    id: str
    draft_status: Literal["draft"] = "draft"
    source_analysis_id: str
    source_video_id: str
    source_title: str
    source_author: Optional[str] = None
    source_url: Optional[str] = None
    source_transcript: str = ""
    source_recognized_at: Optional[datetime] = None
    name: str
    account_type: str
    hotspot_types: list[str]
    solves_problems: list[str] = Field(default_factory=list)
    match_signals: list[str] = Field(default_factory=list)
    applicable_scenes: list[str] = Field(default_factory=list)
    unsuitable_scenes: list[str] = Field(default_factory=list)
    skeleton: list[str]
    hook_formula: str
    emotion_rhythm: str
    ending_formula: str
    risk_boundary: str
    borrowable_moves: list[str] = Field(default_factory=list)
    pattern_fingerprint: str = ""
    similar_skill_id: Optional[str] = None
    similar_skill_name: Optional[str] = None
    similarity_score: int = Field(default=0, ge=0, le=100)
    created_at: datetime


class RiskItem(BaseModel):
    label: str
    level: RiskLevel
    reason: str
    rewrite: str


class RiskCheck(BaseModel):
    passed: bool
    level: RiskLevel
    items: list[RiskItem]


class HotspotBrief(BaseModel):
    id: str
    event_summary: str
    controversy: str
    audience_emotion: str
    angles: list[str]
    no_go_zones: list[str]


class GeneratedScriptVersion(BaseModel):
    id: str
    source_script_id: str
    title: str
    spoken_script: str
    shot_suggestions: list[str]
    subtitle_rhythm: list[str]
    comment_cta: str
    production_status: ScriptProductionStatus
    version_label: str
    editor_note: Optional[str] = None
    created_at: datetime


class GeneratedScript(BaseModel):
    id: str
    title: str
    account_type: str
    content_angle: str
    duration_seconds: int
    spoken_script: str
    shot_suggestions: list[str]
    subtitle_rhythm: list[str]
    comment_cta: str
    risk_check: RiskCheck
    template_used: str
    preset_application: list[str] = Field(default_factory=list)
    production_status: ScriptProductionStatus = "draft"
    version_label: str = "v1"
    editor_note: Optional[str] = None
    updated_at: Optional[datetime] = None
    version_history: list[GeneratedScriptVersion] = Field(default_factory=list)


class WorkbenchOverview(BaseModel):
    tasks: dict[str, int]
    templates: list[TemplatePattern]
    recent_analyses: list[ScriptAnalysis]
    generated_scripts: list[GeneratedScript]


class WorkbenchCapability(BaseModel):
    key: str
    label: str
    available: bool
    status: Literal["ready", "missing", "reserved"]
    detail: str


class WorkbenchCapabilities(BaseModel):
    items: list[WorkbenchCapability]
    ready_count: int
    total_count: int


class ModelRuntimeItem(BaseModel):
    key: Literal["asr", "ocr"]
    label: str
    available: bool
    mode: Literal["auto", "off", "required"]
    initialized: bool
    status: Literal["ready", "not_loaded", "disabled", "missing", "failed"]
    detail: str
    action_items: list[str] = Field(default_factory=list)


class ModelRuntimeStatus(BaseModel):
    items: list[ModelRuntimeItem]
    ready_count: int
    total_count: int
    message: str


class ModelWarmupRequest(BaseModel):
    run_asr: bool = True
    run_ocr: bool = True
    execute: bool = False


class ModelWarmupResponse(BaseModel):
    items: list[ModelRuntimeItem]
    executed: bool
    message: str


class LocalSettingsUpdateRequest(BaseModel):
    llm_mode: Optional[Literal["offline", "optional", "required"]] = None
    llm_model: Optional[str] = Field(default=None, max_length=160)
    llm_api_base: Optional[str] = Field(default=None, max_length=500)
    llm_api_key: Optional[str] = Field(default=None, max_length=500)
    douyin_cookie_string: Optional[str] = Field(default=None, max_length=6000)
    skill_repository_path: Optional[str] = Field(default=None, max_length=1000)
    skill_remote: Optional[str] = Field(default=None, max_length=120)
    skill_remote_url: Optional[str] = Field(default=None, max_length=1000)
    skill_branch: Optional[str] = Field(default=None, max_length=120)
    skill_sync_mode: Optional[Literal["github", "local"]] = None
    clear_llm_key: bool = False
    clear_douyin_cookie: bool = False


class LocalSettingsStatus(BaseModel):
    llm_mode: Literal["offline", "optional", "required"] = "offline"
    llm_model: str = "openai/gpt-4.1-mini"
    llm_api_base: str = ""
    skill_repository_path: str = ""
    skill_remote: str = "origin"
    skill_remote_url: str = ""
    skill_branch: str = "main"
    skill_sync_mode: Literal["github", "local"] = "github"
    sources: dict[str, Literal["environment", "local", "default"]] = Field(
        default_factory=dict
    )
    llm_api_key_configured: bool = False
    llm_api_key_source: Literal["environment", "keyring", "session", "none"] = "none"
    douyin_cookie_configured: bool = False
    douyin_cookie_source: Literal["environment", "keyring", "session", "none"] = "none"
    secret_storage: Literal["system_keyring", "session_only"] = "session_only"
    secrets_persisted: bool = False
    publish_configured: bool = False
    message: str


class ModelCatalogItem(BaseModel):
    id: str
    recommended: bool = False
    recommendation_reason: str = ""


class ModelCatalogResponse(BaseModel):
    models: list[ModelCatalogItem] = Field(default_factory=list)
    recommended_model: str = ""
    message: str


class ModelConnectionCheckResponse(BaseModel):
    passed: bool
    message: str


class GitHubRepositoryConnectRequest(BaseModel):
    repository_url: str = Field(min_length=12, max_length=500)
    local_parent_path: Optional[str] = Field(default=None, max_length=1000)


class GitHubRepositoryCreateRequest(BaseModel):
    repository_name: str = Field(min_length=1, max_length=100)
    visibility: Literal["private", "public"] = "private"
    local_parent_path: Optional[str] = Field(default=None, max_length=1000)


class LocalRepositoryCreateRequest(BaseModel):
    local_parent_path: Optional[str] = Field(default=None, max_length=1000)
    repository_name: str = Field(default="douyin-writing-skills", min_length=1, max_length=100)


class SkillRepositorySetupResponse(BaseModel):
    settings: LocalSettingsStatus
    message: str


class LocalSettingsVerification(BaseModel):
    publish_ready: bool
    git_available: bool
    gh_authenticated: bool
    repository_valid: bool
    remote_matches: bool
    branch_exists: bool
    action_items: list[str] = Field(default_factory=list)
    message: str


class AnalyzeTextRequest(BaseModel):
    title: str = "未命名样本"
    content: str = Field(min_length=10)
    input_type: Literal["subtitle", "transcript", "text"] = "text"
    url: Optional[str] = None
    source_video_id: Optional[str] = None
    author: Optional[str] = None
    publish_time: Optional[str] = None
    source_created_at: Optional[datetime] = None
    asr_text: Optional[str] = None
    ocr_text: Optional[str] = None
    transcript_source: Optional[str] = None
    transcript_confidence: Optional[float] = Field(default=None, ge=0, le=1)


class UploadTextRequest(BaseModel):
    file_name: str
    content: str = Field(min_length=10)
    input_type: Literal["subtitle", "transcript", "text"] = "transcript"
    title: Optional[str] = None


class AnalyzeTextResponse(BaseModel):
    source_video: SourceVideo
    transcript: Transcript
    analysis: ScriptAnalysis
    preset_draft: PresetDraft
    risk_check: RiskCheck
    generated_preview: GeneratedScript
    export_markdown: str
    export_json: dict


class LinkTaskRequest(BaseModel):
    url: str


class AsrTranscriptionResult(BaseModel):
    status: Literal["completed", "skipped", "failed"]
    provider: str = "FunASR"
    text: str = ""
    timestamps: list[str] = Field(default_factory=list)
    message: str


class OcrExtractionResult(BaseModel):
    status: Literal["completed", "skipped", "failed"]
    provider: str = "PaddleOCR"
    text: str = ""
    frame_paths: list[str] = Field(default_factory=list)
    message: str


class VideoUploadResponse(BaseModel):
    source_video: SourceVideo
    audio_path: Optional[str] = None
    frame_paths: list[str] = Field(default_factory=list)
    extraction_status: Literal["completed", "skipped", "failed"]
    asr_status: Literal["completed", "skipped", "failed"]
    asr_provider: str = "FunASR"
    asr_text: str = ""
    ocr_status: Literal["completed", "skipped", "failed"]
    ocr_provider: str = "PaddleOCR"
    ocr_text: str = ""
    transcript: Optional[Transcript] = None
    correction_status: Literal["completed", "needs_review", "skipped", "failed"] = (
        "skipped"
    )
    corrections: list[TranscriptCorrection] = Field(default_factory=list)
    unresolved_fragments: list[str] = Field(default_factory=list)
    transcript_quality_score: int = Field(default=0, ge=0, le=100)
    transcript_quality_message: str = ""
    context_terms: list[str] = Field(default_factory=list)
    message: str
    asr_message: str
    ocr_message: str
    next_step: str
    fallback_inputs: list[str]
    media_cleanup_status: Literal["retained", "completed", "failed"] = "retained"
    media_cleanup_message: str = "临时媒体会在成功生成可分析文本后自动清理。"


class VideoExtractionRequest(BaseModel):
    run_asr: bool = True
    run_ocr: bool = True


class VideoExtractionTask(BaseModel):
    id: str
    source_video_id: str
    status: ExtractionTaskStatus
    stage: str
    stage_detail: str = ""
    progress: int = Field(default=0, ge=0, le=100)
    source_video: SourceVideo
    audio_path: Optional[str] = None
    frame_paths: list[str] = Field(default_factory=list)
    asr_status: Literal["completed", "skipped", "failed"] = "skipped"
    asr_message: str = ""
    ocr_status: Literal["completed", "skipped", "failed"] = "skipped"
    ocr_message: str = ""
    transcript: Optional[Transcript] = None
    video_upload: Optional[VideoUploadResponse] = None
    error: Optional[str] = None
    cancel_requested: bool = False
    retry_of: Optional[str] = None
    run_asr: bool = True
    run_ocr: bool = True
    next_step: str = ""
    fallback_inputs: list[str] = Field(default_factory=list)
    media_cleanup_status: Literal["retained", "completed", "failed"] = "retained"
    media_cleanup_message: str = ""
    created_at: datetime
    updated_at: datetime


class DouyinDownloadResult(BaseModel):
    status: Literal["completed", "skipped", "failed"]
    provider: str = "jiji262/douyin-downloader"
    output_dir: Optional[str] = None
    downloaded_files: list[str] = Field(default_factory=list)
    selected_video_path: Optional[str] = None
    error_code: Optional[DouyinParserErrorCode] = None
    error_title: Optional[str] = None
    error_detail: Optional[str] = None
    action_items: list[str] = Field(default_factory=list)
    message: str
    metadata_title: Optional[str] = None
    metadata_author: Optional[str] = None
    metadata_publish_time: Optional[str] = None


class LinkTaskResponse(BaseModel):
    source_video: SourceVideo
    parser_status: Literal["completed", "skipped", "failed"]
    parser_provider: str = "jiji262/douyin-downloader"
    output_dir: Optional[str] = None
    downloaded_files: list[str] = Field(default_factory=list)
    video_upload: Optional[VideoUploadResponse] = None
    parser_error_code: Optional[DouyinParserErrorCode] = None
    parser_error_title: Optional[str] = None
    parser_error_detail: Optional[str] = None
    parser_action_items: list[str] = Field(default_factory=list)
    message: str
    fallback_inputs: list[str]


class LinkDiagnosticRecord(BaseModel):
    id: str
    url: str
    source_video_id: str
    parser_status: Literal["completed", "skipped", "failed"]
    parser_provider: str
    parser_error_code: Optional[DouyinParserErrorCode] = None
    parser_error_title: Optional[str] = None
    parser_error_detail: Optional[str] = None
    parser_action_items: list[str] = Field(default_factory=list)
    fallback_inputs: list[str] = Field(default_factory=list)
    output_dir: Optional[str] = None
    downloaded_file_count: int = 0
    has_video_upload: bool = False
    cookie_configured: bool = False
    downloader_mode: Literal["auto", "off", "required"] = "auto"
    recommended_next_step: str
    message: str
    created_at: datetime


class GenerateHotspotRequest(BaseModel):
    hotspot: str = Field(min_length=4)
    account_type: str = "娱乐吃瓜号"
    template_id: Optional[str] = None
    duration_seconds: int = Field(default=45, ge=15, le=180)
    tone: str = "犀利但不造谣"
    goal: str = "引发评论"


class GenerateHotspotResponse(BaseModel):
    brief: HotspotBrief
    matched_templates: list[TemplatePattern]
    scripts: list[GeneratedScript]


class DraftInputRequest(BaseModel):
    title: str = "未命名稿件"
    content: str = Field(min_length=4)
    input_type: Literal["hotspot", "outline", "partial_script", "script"] = "outline"
    account_type: str = "娱乐吃瓜号"
    duration_seconds: int = Field(default=45, ge=15, le=180)
    tone: str = "克制、有信息增量"
    goal: str = "让脚本更完整、更好拍"


class DraftDiagnosis(BaseModel):
    id: str
    draft_title: str
    draft_type: Literal["hotspot", "outline", "partial_script", "script"]
    strengths: list[str]
    problems: list[str]
    rewrite_goals: list[str]
    suggested_skill_types: list[str]
    no_go_zones: list[str]


class SkillMatch(BaseModel):
    skill: TemplatePattern
    match_score: int = Field(ge=0, le=100)
    reason: str
    apply_plan: list[str]


class DraftRewriteRequest(DraftInputRequest):
    skill_ids: list[str] = Field(default_factory=list)


class FactSource(BaseModel):
    title: str
    url: str
    publisher: str = ""
    published_at: Optional[str] = None


class FactVerification(BaseModel):
    required: bool = False
    verdict: Literal["not_required", "verified", "refuted", "uncertain", "failed"] = (
        "not_required"
    )
    claim: str = ""
    summary: str = ""
    verified_facts: list[str] = Field(default_factory=list)
    corrections: list[str] = Field(default_factory=list)
    sources: list[FactSource] = Field(default_factory=list)
    checked_at: Optional[datetime] = None


class DraftRewriteResponse(BaseModel):
    diagnosis: DraftDiagnosis
    matched_skills: list[SkillMatch]
    rewrite_plan: list[str]
    scripts: list[GeneratedScript]
    generation_mode: Literal["ai", "fallback", "blocked"] = "fallback"
    generation_model: Optional[str] = None
    generation_note: str = ""
    fact_verification: FactVerification = Field(default_factory=FactVerification)


class DraftRewriteActivity(BaseModel):
    id: str
    phase: Literal["diagnosis", "research", "skill_match", "writing", "quality"]
    kind: Literal["status", "search", "source", "skill", "draft", "check"]
    title: str
    detail: str = ""
    status: Literal["active", "completed", "failed"] = "completed"
    created_at: datetime


class DraftRewriteTask(BaseModel):
    id: str
    status: Literal["queued", "processing", "completed", "failed"] = "queued"
    stage: Literal[
        "queued",
        "diagnosing",
        "fact_checking",
        "matching_skill",
        "generating_scripts",
        "quality_checking",
        "completed",
        "failed",
    ] = "queued"
    stage_detail: str = "已进入生成队列"
    progress: int = Field(default=0, ge=0, le=100)
    timeout_seconds: int = Field(default=420, ge=60, le=3600)
    activities: list[DraftRewriteActivity] = Field(default_factory=list)
    result: Optional[DraftRewriteResponse] = None
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class SelectionRewriteRequest(BaseModel):
    selected_text: str = Field(min_length=2, max_length=1600)
    instruction: str = Field(min_length=2, max_length=300)
    full_script: str = Field(min_length=20, max_length=6000)
    account_type: str = Field(default="泛娱乐观点号", max_length=80)
    duration_seconds: int = Field(default=60, ge=15, le=180)
    tone: str = Field(default="自然口播", max_length=100)
    skill_name: str = Field(default="", max_length=120)
    verified_facts: list[str] = Field(default_factory=list, max_length=40)
    verified_sources: list[FactSource] = Field(default_factory=list, max_length=8)
    rewrite_intents: list[str] = Field(default_factory=list, max_length=6)
    research_mode: Literal["none", "targeted"] = "none"
    emotional_goal: str = Field(default="", max_length=160)


class SelectionRewriteResponse(BaseModel):
    replacement: str
    change_summary: str
    supporting_facts: list[str] = Field(default_factory=list)
    sources: list[FactSource] = Field(default_factory=list)


class SelectionRewriteSuggestionRequest(BaseModel):
    selected_text: str = Field(min_length=2, max_length=1600)
    full_script: str = Field(min_length=20, max_length=6000)
    account_type: str = Field(default="泛娱乐观点号", max_length=80)
    duration_seconds: int = Field(default=60, ge=15, le=180)
    tone: str = Field(default="自然口播", max_length=100)
    skill_name: str = Field(default="", max_length=120)
    verified_facts: list[str] = Field(default_factory=list, max_length=40)


class SelectionRewriteSuggestion(BaseModel):
    id: str
    label: str
    instruction: str
    reason: str
    evidence_needed: bool = False


class SelectionRewriteSuggestionResponse(BaseModel):
    suggestions: list[SelectionRewriteSuggestion]


def compact_rewrite_facts(items: list[str], limit: int = 12) -> list[str]:
    compacted: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = item.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        compacted.append(value)
        if len(compacted) >= limit:
            break
    return compacted


class TemplateReviewUpdateRequest(BaseModel):
    quality_score: int = Field(ge=0, le=100)
    applicable_scenes: list[str] = Field(default_factory=list)
    unsuitable_scenes: list[str] = Field(default_factory=list)
    disabled_reason: Optional[str] = None
    last_review_note: Optional[str] = None


class SkillGovernanceUpdateRequest(BaseModel):
    status: SkillStatus
    owner: str = Field(default="内容主审", min_length=2, max_length=120)
    platforms: list[str] = Field(default_factory=lambda: ["douyin"])
    required_inputs: list[str] = Field(default_factory=list)
    output_contract: list[str] = Field(default_factory=list)
    promotion_reason: Optional[str] = Field(default=None, max_length=1000)
    expires_at: Optional[datetime] = None
    evidence: list[SkillEvidence] = Field(default_factory=list)
    evaluation_summary: SkillEvaluationSummary = Field(default_factory=SkillEvaluationSummary)
    release_report_path: Optional[str] = Field(default=None, max_length=500)
    review: Optional[SkillReviewRecord] = None


class WritingPresetCreateRequest(BaseModel):
    preset_draft: PresetDraft
    name: Optional[str] = None
    quality_score: int = Field(default=86, ge=0, le=100)
    applicable_scenes: list[str] = Field(default_factory=list)
    unsuitable_scenes: list[str] = Field(default_factory=list)
    last_review_note: Optional[str] = None
    merge_target_id: Optional[str] = None
    merge_as_new: bool = False


class GeneratedScriptUpdateRequest(BaseModel):
    title: str = Field(min_length=2)
    spoken_script: str = Field(min_length=20)
    shot_suggestions: list[str] = Field(default_factory=list)
    subtitle_rhythm: list[str] = Field(default_factory=list)
    comment_cta: str = Field(min_length=2)
    production_status: ScriptProductionStatus = "editing"
    version_label: str = "v1"
    editor_note: Optional[str] = None


class ExternalGateItem(BaseModel):
    key: Literal["link", "llm", "human_review"]
    label: str
    passed: bool
    status: str
    detail: str
    action_items: list[str] = Field(default_factory=list)


class ExternalGateReport(BaseModel):
    passed: bool
    items: list[ExternalGateItem]
    link_gate: dict
    llm_gate: dict
    human_review_gate: dict
    report_path: str


class HumanReviewItem(BaseModel):
    id: str
    hotspot: str = ""
    script_title: str = ""
    shootable: bool = False
    not_pure_rewrite: bool = False
    clear_structure: bool = False
    risk_passed: bool = False
    reviewer: str = ""
    notes: str = ""


class HumanReviewUpdateRequest(BaseModel):
    items: list[HumanReviewItem]


class HumanReviewTemplateResponse(BaseModel):
    path: str
    required_count: int
    items: list[HumanReviewItem]
    message: str


ANALYSES: list[ScriptAnalysis] = []
TEMPLATES: list[TemplatePattern] = []
GENERATED: list[GeneratedScript] = []
SOURCES: list[SourceVideo] = []
VIDEO_UPLOADS: dict[str, VideoUploadResponse] = {}
VIDEO_EXTRACTION_TASKS: dict[str, VideoExtractionTask] = {}
VIDEO_EXTRACTION_OPTIONS: dict[str, VideoExtractionRequest] = {}
VIDEO_EXTRACTION_LOCK = threading.Lock()
VIDEO_EXTRACTION_STATE_LOADED = False
DRAFT_REWRITE_TASKS: dict[str, DraftRewriteTask] = {}
DRAFT_REWRITE_LOCK = threading.Lock()
LINK_DIAGNOSTICS: list[LinkDiagnosticRecord] = []
LINK_DIAGNOSTICS_LOCK = threading.Lock()
LINK_DIAGNOSTICS_STATE_LOADED = False
LOCAL_SKILL_LIBRARY_FILE = "writing-skills.json"


PROJECT_ROOT = Path(__file__).resolve().parents[2]
# Public workbench data must never be inferred from a previous private install.
# Legacy locations are available only through an explicit migration opt-in.
PUBLIC_DATA_ROOT = Path.home() / ".local/share/douyin-script-workbench/public"
LEGACY_MEDIA_ROOT = Path("/tmp/douyin-script-workbench")
LEGACY_SKILL_LIBRARY_ROOT = Path.home() / ".local/share/douyin-script-workbench"
_FUNASR_MODELS: dict[str, object] = {}
_PADDLE_OCR_MODEL = None
MODEL_WORKER_PYTHON: dict[str, str | None] = {}


SEED_TEMPLATES = [
    TemplatePattern(
        id="tpl_problem_solution",
        name="问题解决型",
        account_type="泛娱乐观点号",
        hotspot_types=["生活方式", "争议话题", "消费避坑"],
        applicable_scenes=["生活争议", "消费避坑", "普通人情绪共鸣"],
        unsuitable_scenes=["明星隐私爆料", "高敏社会事件"],
        skeleton=["开头反问", "痛点放大", "分步解释", "结果展示", "评论引导"],
        hook_formula="你以为这是 A？其实真正的问题是 B。",
        emotion_rhythm="疑问 -> 共鸣 -> 获得感 -> 轻互动",
        ending_formula="你遇到过这种情况吗？评论区聊聊。",
        risk_boundary="避免绝对化承诺和未经证实的事实判断。",
        quality_score=86,
        usage_count=126000,
        last_review_note="适合做生活化热点，观点不能过度下判断。",
    ),
    TemplatePattern(
        id="tpl_reversal",
        name="反差对比型",
        account_type="娱乐吃瓜号",
        hotspot_types=["明星事件", "粉丝争议", "剧综热点"],
        applicable_scenes=["公开回应", "剧综争议", "粉丝与路人观感分歧"],
        unsuitable_scenes=["未证实恋情", "私生活细节", "未成年人相关争议"],
        skeleton=["爆点开场", "表面信息", "细节反差", "态度升维", "站队讨论"],
        hook_formula="这件事最离谱的不是结果，而是这个细节。",
        emotion_rhythm="惊讶 -> 怀疑 -> 发现细节 -> 表达观点",
        ending_formula="你觉得哪边更体面？评论区说说。",
        risk_boundary="只评论公开信息和表达策略，不扩写隐私、不编造内幕。",
        quality_score=91,
        usage_count=83000,
        last_review_note="娱乐热点起量强，但必须严格保留公开信息边界。",
    ),
    TemplatePattern(
        id="tpl_context",
        name="背景拆解型",
        account_type="商业分析号",
        hotspot_types=["品牌危机", "代言翻车", "平台热点"],
        applicable_scenes=["品牌公关", "代言争议", "平台规则变化"],
        unsuitable_scenes=["投资建议", "法律定责", "未公开商业数据"],
        skeleton=["事件一句话", "利益关系", "传播后果", "行业规律", "风险提示"],
        hook_formula="这不是一次普通热搜，而是一次标准的传播风险样本。",
        emotion_rhythm="理性 -> 信息增量 -> 判断 -> 风险意识",
        ending_formula="这类事件你更看重态度，还是处理速度？",
        risk_boundary="避免给出投资、法律、确定性商业结论。",
        quality_score=88,
        usage_count=51000,
        last_review_note="适合品牌/平台类热点，重点输出结构化信息增量。",
    ),
]


def bootstrap_templates() -> None:
    if not TEMPLATES:
        fixtures_enabled = os.getenv("WORKBENCH_SKILL_EVAL_FIXTURES") == "1"
        TEMPLATES.extend(
            sort_skill_templates(
                deduplicate_templates(
                    [
                        *read_local_skill_templates(),
                        *(
                            [
                                enrich_skill_template(template)
                                for template in SEED_TEMPLATES
                            ]
                            if fixtures_enabled
                            else []
                        ),
                    ]
                )
            )
        )


def enable_offline_evaluation_templates() -> None:
    """Expose in-memory fixtures only for deterministic regression suites."""
    if os.getenv("WORKBENCH_SKILL_EVAL_FIXTURES") != "1":
        return
    bootstrap_templates()
    TEMPLATES[:] = [
        template.model_copy(update={"status": "active", "disabled_reason": None})
        for template in TEMPLATES
    ]


def read_local_skill_templates() -> list[TemplatePattern]:
    templates: list[TemplatePattern] = []
    for path in local_skill_library_paths():
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        raw_items = payload.get("templates") if isinstance(payload, dict) else payload
        if not isinstance(raw_items, list):
            continue
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            try:
                templates.append(enrich_skill_template(TemplatePattern(**item)))
            except Exception:
                continue
    return sort_skill_templates(deduplicate_templates(templates))


def write_local_skill_templates(templates: list[TemplatePattern]) -> None:
    path = local_skill_library_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    merged = deduplicate_templates(templates)
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "templates": [template.model_dump(mode="json") for template in merged],
    }
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def upsert_local_skill_template(template: TemplatePattern) -> None:
    templates = read_local_skill_templates()
    replaced = False
    for index, item in enumerate(templates):
        if item.id == template.id:
            templates[index] = template
            replaced = True
            break
    if not replaced:
        templates.insert(0, template)
    write_local_skill_templates(templates)


def skill_has_source_evidence(template: TemplatePattern) -> bool:
    meaningful_titles = [
        title
        for title in template.source_titles
        if title.strip() and title.strip() != "暂无来源记录"
    ]
    meaningful_sources = [
        source
        for source in template.sources
        if source.title.strip() and source.title.strip() != "暂无来源记录"
    ]
    return bool(meaningful_sources or meaningful_titles)


def publishable_skill_templates(templates: list[TemplatePattern]) -> list[TemplatePattern]:
    publishable: list[TemplatePattern] = []
    for template in sort_skill_templates(deduplicate_templates(templates)):
        if (
            template.status != "active"
            or template.disabled_reason
            or not skill_has_source_evidence(template)
            or not any(review.approved for review in template.reviews)
        ):
            continue
        try:
            verified_summary = load_skill_release_evidence(template)
        except ValueError:
            continue
        publishable.append(
            template.model_copy(update={"evaluation_summary": verified_summary})
        )
    return publishable


def skill_is_routable(template: TemplatePattern) -> bool:
    return template.status == "active" and not template.disabled_reason


def skill_promotion_errors(template: TemplatePattern) -> list[str]:
    errors: list[str] = []
    if template.source_count < 3:
        errors.append("至少需要 3 个授权来源案例。")
    if not skill_has_source_evidence(template):
        errors.append("缺少可追溯来源证据。")
    if len(template.skeleton) < 3 or not template.match_signals:
        errors.append("Skill 需要可脱离原事件复用的结构骨架和匹配信号。")
    if not any(item.scope == "structure" for item in template.evidence):
        errors.append("至少需要一条结构来源证据。")
    if not template.evaluation_summary.passed:
        errors.append(
            "真实模型发布评测尚未运行。"
            if template.evaluation_summary.evaluated_at is None
            else "真实模型发布评测未达到发布门槛。"
        )
    if not any(review.approved for review in template.reviews):
        errors.append("需要内容主审批准。")
    return errors


def skill_promotion_readiness(template: TemplatePattern) -> SkillPromotionReadiness:
    enriched = enrich_skill_template(template)
    return SkillPromotionReadiness(
        template_id=enriched.id,
        ready=not skill_promotion_errors(enriched),
        blockers=skill_promotion_errors(enriched),
        source_count=enriched.source_count,
        evidence_count=len(enriched.evidence),
        has_structure_evidence=any(
            item.scope == "structure" for item in enriched.evidence
        ),
        evaluation_passed=enriched.evaluation_summary.passed,
        main_review_approved=any(review.approved for review in enriched.reviews),
    )


def skill_release_report_root() -> Path:
    """Return the local, isolated directory for generated release evidence."""
    return workbench_data_root() / "reports"


def run_skill_release_evaluation() -> SkillReleaseEvaluationResponse:
    root = Path(__file__).resolve().parents[2]
    report_path = skill_release_report_root() / "skill-release-report.json"
    report_name = report_path.name
    environment = {**os.environ, "WORKBENCH_LLM_MODE": "required"}
    try:
        completed = subprocess.run(
            [sys.executable, str(root / "backend" / "scripts" / "verify_skill_release.py")],
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=1800,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return SkillReleaseEvaluationResponse(
            passed=False,
            report_path=report_name,
            message="真实 Skill 发布评测超时，未生成可发布版本。",
        )
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return SkillReleaseEvaluationResponse(
            passed=False,
            report_path=report_name,
            message="真实 Skill 发布评测未生成有效报告。",
        )
    passed = completed.returncode == 0 and report.get("passed") is True
    return SkillReleaseEvaluationResponse(
        passed=passed,
        report_path=report_name,
        message=(
            "真实 Skill 发布评测已通过，可回到 Skill 库批准正式版本。"
            if passed
            else "真实 Skill 发布评测未通过；请根据报告补齐来源、人审或模型质量门禁。"
        ),
    )


def load_skill_release_evidence(
    template: TemplatePattern, report_path: Optional[str] = None
) -> SkillEvaluationSummary:
    """Load immutable release evidence instead of trusting API-supplied scores."""
    requested = report_path or template.evaluation_summary.report_path
    if not requested:
        raise ValueError("需要指定真实模型发布评测报告。")
    candidate = Path(requested).expanduser()
    if not candidate.is_absolute():
        candidate = skill_release_report_root() / candidate
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError("真实模型发布评测报告不存在。") from exc
    root = skill_release_report_root().resolve()
    if root != resolved and root not in resolved.parents:
        raise ValueError("发布评测报告必须位于 evals/workbench 目录。")
    try:
        report = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("发布评测报告不是有效 JSON。") from exc
    if report.get("model_mode") != "required" or not report.get("model"):
        raise ValueError("发布评测报告不是 required 模式的真实模型运行。")
    if not report.get("passed"):
        raise ValueError("真实模型发布评测尚未通过。")
    skill_results = report.get("skill_results")
    if not isinstance(skill_results, list):
        raise ValueError("发布评测报告缺少按 Skill 记录的结果。")
    result = next(
        (item for item in skill_results if item.get("template_id") == template.id),
        None,
    )
    if not isinstance(result, dict) or not result.get("passed"):
        raise ValueError("该 Skill 没有通过对应的发布评测。")
    metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
    required_metrics = {
        "routing_accuracy": 0.85,
        "no_match_accuracy": 0.90,
        "safety_block_rate": 1.0,
        "citation_coverage": 1.0,
        "human_score": 4.0,
        "minimum_dimension_score": 3.0,
    }
    for key, minimum in required_metrics.items():
        value = metrics.get(key)
        if not isinstance(value, (int, float)) or value < minimum:
            raise ValueError(f"该 Skill 的发布评测未达到 {key} 门槛。")
    return SkillEvaluationSummary(
        routing_accuracy=float(metrics["routing_accuracy"]),
        no_match_accuracy=float(metrics["no_match_accuracy"]),
        safety_block_rate=float(metrics["safety_block_rate"]),
        citation_coverage=float(metrics["citation_coverage"]),
        human_score=float(metrics["human_score"]),
        minimum_dimension_score=float(metrics["minimum_dimension_score"]),
        passed=True,
        report_path=resolved.name,
        evaluated_at=datetime.fromisoformat(report["generated_at"]),
    )


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def safe_file_name(file_name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+", "_", file_name).strip("._")
    return cleaned or "uploaded-video.mp4"


def legacy_data_enabled() -> bool:
    return os.getenv("WORKBENCH_ALLOW_LEGACY_DATA", "").strip() == "1"


def workbench_data_root() -> Path:
    configured = os.getenv("WORKBENCH_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return PUBLIC_DATA_ROOT.expanduser().resolve()


def media_root() -> Path:
    if legacy_data_enabled():
        configured = os.getenv("WORKBENCH_MEDIA_DIR", "").strip()
        if configured:
            return Path(configured).expanduser().resolve()
        return LEGACY_MEDIA_ROOT.resolve()
    return workbench_data_root() / "media"


def local_skill_library_path() -> Path:
    configured = os.getenv("WORKBENCH_SKILL_LIBRARY_PATH", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    if legacy_data_enabled():
        return (LEGACY_SKILL_LIBRARY_ROOT / LOCAL_SKILL_LIBRARY_FILE).expanduser().resolve()
    return workbench_data_root() / LOCAL_SKILL_LIBRARY_FILE


def local_skill_library_paths() -> list[Path]:
    primary = local_skill_library_path()
    if os.getenv("WORKBENCH_SKILL_LIBRARY_PATH", "").strip() or not legacy_data_enabled():
        return [primary]
    legacy = LEGACY_MEDIA_ROOT / LOCAL_SKILL_LIBRARY_FILE
    paths: list[Path] = []
    for path in [primary, legacy]:
        if path not in paths:
            paths.append(path)
    return paths


def link_diagnostics_path() -> Path:
    return media_root() / "douyin-link-diagnostics.json"


def human_review_template_path() -> Path:
    return workbench_data_root() / "reports" / "human-review-template.json"


def external_gates_report_path() -> Path:
    return workbench_data_root() / "reports" / "external-gates-report.json"


def workbench_llm_mode() -> str:
    mode = os.getenv("WORKBENCH_LLM_MODE", "offline").strip().lower()
    if mode not in {"offline", "optional", "required"}:
        mode = "offline"
    return mode


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


CHINESE_CHARACTER_PATTERN = re.compile(r"[\u3400-\u9fff]")
LONG_LATIN_PHRASE_PATTERN = re.compile(
    r"[A-Za-z][A-Za-z'-]*(?:\s+[A-Za-z][A-Za-z'-]*){2,}"
)
LONG_LATIN_WORD_PATTERN = re.compile(r"[A-Za-z]{18,}")
SHARE_HASHTAG_PATTERN = re.compile(r"#\s*([A-Za-z0-9_\u3400-\u9fff·-]{2,24})")
GENERIC_SHARE_TERMS = {
    "女性",
    "男性",
    "热点",
    "娱乐",
    "时尚",
    "奢侈品",
    "明星",
    "品牌",
    "社会",
    "生活",
    "情感",
    "励志",
    "正能量",
    "抖音",
    "视频",
}
COMMON_INTENTIONAL_REPEATS = {
    "人人",
    "看看",
    "慢慢",
    "往往",
    "常常",
    "纷纷",
    "偏偏",
    "渐渐",
    "好好",
    "刚刚",
    "年年",
    "次次",
    "拍拍",
}


def clean_spoken_transcript(text: str) -> str:
    cleaned = clean_text(text)
    chinese_count = len(CHINESE_CHARACTER_PATTERN.findall(cleaned))
    if chinese_count < 10:
        return cleaned
    cleaned = LONG_LATIN_PHRASE_PATTERN.sub(" ", cleaned)
    cleaned = LONG_LATIN_WORD_PATTERN.sub(" ", cleaned)
    return clean_text(cleaned)


def is_likely_subtitle_text(text: str) -> bool:
    cleaned = clean_text(text)
    chinese_count = len(CHINESE_CHARACTER_PATTERN.findall(cleaned))
    latin_count = len(re.findall(r"[A-Za-z]", cleaned))
    if chinese_count < 2:
        return False
    return latin_count < 20 or chinese_count * 2 >= latin_count


def build_primary_transcript(asr_text: str, ocr_text: str) -> tuple[str, str]:
    cleaned_asr = clean_spoken_transcript(asr_text)
    if len(cleaned_asr) >= 10:
        return cleaned_asr, "funasr"

    ocr_fragments = [
        fragment
        for fragment in re.split(r"[\n\r]+|(?<=[。！？!?])\s+", ocr_text)
        if is_likely_subtitle_text(fragment)
    ]
    cleaned_ocr = clean_spoken_transcript(" ".join(ocr_fragments))
    return cleaned_ocr, "paddleocr" if len(cleaned_ocr) >= 10 else ""


def extract_share_context_terms(context_text: str) -> tuple[list[str], list[str]]:
    terms: list[str] = []
    for match in SHARE_HASHTAG_PATTERN.finditer(context_text):
        term = match.group(1).strip("_-·")
        if term and term not in terms:
            terms.append(term)
    entity_terms = [
        term
        for term in terms
        if term not in GENERIC_SHARE_TERMS
        and 2 <= len(term) <= 6
        and len(CHINESE_CHARACTER_PATTERN.findall(term)) >= 2
    ]
    return terms, entity_terms


def pinyin_key(text: str) -> str:
    from pypinyin import Style, lazy_pinyin

    return "".join(lazy_pinyin(text, style=Style.NORMAL, errors="ignore"))


def apply_context_term_corrections(
    text: str, entity_terms: list[str]
) -> tuple[str, list[TranscriptCorrection]]:
    corrected_text = text
    corrections: list[TranscriptCorrection] = []
    for term in entity_terms:
        term_key = pinyin_key(term)
        if not term_key:
            continue
        windows = re.findall(rf"(?=([\u3400-\u9fff]{{{len(term)}}}))", corrected_text)
        ranked: list[tuple[float, str]] = []
        for window in set(windows):
            if window == term:
                continue
            similarity = SequenceMatcher(None, pinyin_key(window), term_key).ratio()
            ranked.append((similarity, window))
        ranked.sort(reverse=True)
        if not ranked:
            continue

        # Only phonetic near-matches are safe to apply automatically. Lower-scoring
        # candidates remain visible to the quality gate for review.
        accepted_floor = 0.80
        for score, original in ranked:
            if score < accepted_floor or original not in corrected_text:
                continue
            corrected_text = corrected_text.replace(original, term)
            corrections.append(
                TranscriptCorrection(
                    original=original,
                    corrected=term,
                    reason=f"与分享标签“{term}”读音高度相近",
                    confidence=min(98, round(score * 100)),
                )
            )
    return clean_text(corrected_text), corrections


def find_context_term_mismatches(text: str, entity_terms: list[str]) -> list[str]:
    mismatches: list[str] = []
    for term in entity_terms:
        if term in text:
            continue
        term_key = pinyin_key(term)
        if not term_key:
            continue
        windows = set(re.findall(rf"(?=([\u3400-\u9fff]{{{len(term)}}}))", text))
        ranked = sorted(
            (
                (SequenceMatcher(None, pinyin_key(window), term_key).ratio(), window)
                for window in windows
            ),
            reverse=True,
        )
        if ranked and ranked[0][0] >= 0.65:
            score, candidate = ranked[0]
            mismatches.append(
                f"疑似专名“{candidate}”需核对为分享标签“{term}”"
                f"（读音相似度 {round(score * 100)}%）"
            )
    return mismatches


def find_transcript_anomalies(text: str, context_terms: list[str]) -> list[str]:
    inspection_text = text
    for term in context_terms:
        inspection_text = inspection_text.replace(term, "")
    anomalies: list[str] = []
    for match in re.finditer(r"([\u3400-\u9fff])\1", inspection_text):
        repeated = match.group(0)
        if repeated in COMMON_INTENTIONAL_REPEATS:
            continue
        start = max(0, match.start() - 6)
        end = min(len(inspection_text), match.end() + 8)
        fragment = inspection_text[start:end]
        if fragment not in anomalies:
            anomalies.append(fragment)
    return anomalies[:8]


def correct_primary_transcript(
    transcript: str,
    context_text: str,
    ocr_text: str,
) -> tuple[str, list[TranscriptCorrection], list[str], int, str, list[str]]:
    context_terms, entity_terms = extract_share_context_terms(context_text)
    corrected_text, corrections = apply_context_term_corrections(
        transcript, entity_terms
    )

    try:
        from app.workbench_llm import correct_transcript_structured

        llm_result = correct_transcript_structured(
            corrected_text, context_text, context_terms, ocr_text
        )
    except Exception:
        llm_result = None

    unresolved: list[str] = []
    if llm_result is not None:
        edit_budget = max(24, round(len(corrected_text) * 0.12))
        edited_characters = 0
        seen_originals: set[str] = set()
        for item in llm_result.corrections:
            original = clean_text(item.original)
            replacement = clean_text(item.corrected)
            if (
                not original
                or original == replacement
                or original in seen_originals
                or original not in corrected_text
            ):
                continue
            seen_originals.add(original)
            if corrected_text.count(original) != 1:
                unresolved.append(
                    f"自动校正片段定位不唯一，已拒绝应用：“{original}” -> “{replacement}”"
                )
                continue
            if item.confidence < 80 or len(original) > 30 or len(replacement) > 30:
                unresolved.append(f"低置信校正待确认：“{original}” -> “{replacement}”")
                continue
            edit_size = max(len(original), len(replacement))
            if edited_characters + edit_size > edit_budget:
                unresolved.append("自动校正累计改动范围过大，剩余修改已拒绝应用")
                break
            corrected_text = corrected_text.replace(original, replacement, 1)
            edited_characters += edit_size
            corrections.append(
                TranscriptCorrection(
                    original=original,
                    corrected=replacement,
                    reason=item.reason,
                    confidence=item.confidence,
                )
            )
        unresolved.extend(llm_result.unresolved_fragments)

    unresolved.extend(find_transcript_anomalies(corrected_text, entity_terms))
    unresolved.extend(find_context_term_mismatches(corrected_text, entity_terms))
    unresolved = list(dict.fromkeys(clean_text(item) for item in unresolved if item))
    quality_score = max(40, 98 - min(18, len(corrections) * 2) - len(unresolved) * 12)
    if unresolved:
        message = f"仍有 {len(unresolved)} 处无法可靠确认，已停止后续拆解。"
    elif corrections:
        message = f"已自动校正 {len(corrections)} 处专名或转写错误，可以继续拆解。"
    else:
        message = "未发现需要修改的明显专名或转写异常，可以继续拆解。"
    return (
        corrected_text,
        corrections,
        unresolved,
        quality_score,
        message,
        context_terms,
    )


HTTP_URL_PATTERN = re.compile(r"https?://[^\s，,。；;）)】\]]+", re.IGNORECASE)
BARE_DOUYIN_URL_PATTERN = re.compile(
    r"(?<![\w./-])(?:www\.)?(?:v\.)?douyin\.com/[^\s，,。；;）)】\]]+", re.IGNORECASE
)


def normalize_douyin_url_input(value: str) -> str:
    cleaned = clean_text(value)
    if not cleaned:
        return cleaned
    urls = [
        match.group(0).rstrip(".,;，。；、")
        for match in HTTP_URL_PATTERN.finditer(cleaned)
    ]
    for match in BARE_DOUYIN_URL_PATTERN.finditer(cleaned):
        bare = match.group(0).rstrip(".,;，。；、")
        if not bare.lower().startswith(("http://", "https://")):
            bare = f"https://{bare}"
        urls.append(bare)
    douyin_urls = [url for url in urls if "douyin.com" in url.lower()]
    return (douyin_urls or urls or [cleaned])[0]


def parse_douyin_share_source_context(value: str) -> dict[str, str]:
    """Extract trustworthy source hints from a pasted Douyin share sentence."""

    cleaned = clean_text(value)
    if not cleaned:
        return {}

    without_urls = HTTP_URL_PATTERN.sub(" ", cleaned)
    without_urls = BARE_DOUYIN_URL_PATTERN.sub(" ", without_urls)
    without_urls = re.sub(
        r"复制此链接.*?(?:观看视频|搜索|打开抖音).*?$",
        " ",
        without_urls,
        flags=re.IGNORECASE,
    )
    title_seed = without_urls
    if ":/" in title_seed:
        title_seed = title_seed.rsplit(":/", 1)[-1]
    title_seed = re.sub(r"#\s*[^#\s，,。；;]+", " ", title_seed)
    title_seed = re.sub(r"\s+", " ", title_seed).strip(" ，,。；;")

    author = ""
    author_patterns = [
        r"(?:作者|账号|博主|抖音号|昵称)[:：]\s*([^#，,。；;\s]{2,30})",
        r"(?:来自|分享自)[:：]?\s*([^#，,。；;\s]{2,30})",
    ]
    for pattern in author_patterns:
        match = re.search(pattern, cleaned)
        if match:
            author = clean_text(match.group(1)).strip("@")
            break

    result: dict[str, str] = {}
    if title_seed and not title_seed.lower().startswith(("http://", "https://")):
        result["title"] = title_seed[:120]
    if author:
        result["author"] = author[:80]
    return result


def _read_json_file(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def douyin_download_metadata(output_dir: Path) -> dict[str, str]:
    if not output_dir.exists():
        return {}
    metadata_files = sorted(
        [
            path
            for path in output_dir.rglob("*.json")
            if path.is_file() and path.name != "config.yml"
        ],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in metadata_files:
        payload = _read_json_file(path)
        title = clean_text(str(payload.get("title") or payload.get("desc") or ""))
        author = clean_text(
            str(
                payload.get("uploader")
                or payload.get("creator")
                or payload.get("channel")
                or payload.get("nickname")
                or payload.get("author")
                or payload.get("user", {}).get("nickname")
                if isinstance(payload.get("user"), dict)
                else ""
            )
        )
        publish_time = clean_text(
            str(payload.get("upload_date") or payload.get("release_timestamp") or "")
        )
        if title or author or publish_time:
            return {
                key: value
                for key, value in {
                    "title": title[:160],
                    "author": author[:120],
                    "publish_time": publish_time[:64],
                }.items()
                if value
            }
    return {}


def credential_present() -> bool:
    return bool(os.getenv("OPENAI_API_KEY") or os.getenv("WORKBENCH_LLM_API_KEY"))


def local_settings_status(message: str = "本机设置状态已读取。") -> LocalSettingsStatus:
    return LocalSettingsStatus.model_validate(read_local_settings_status(message))


def update_local_settings(payload: LocalSettingsUpdateRequest) -> LocalSettingsStatus:
    return LocalSettingsStatus.model_validate(
        save_local_settings(
            payload.model_dump(
                exclude={"clear_llm_key", "clear_douyin_cookie"},
                exclude_none=False,
            ),
            clear_llm_key=payload.clear_llm_key,
            clear_douyin_cookie=payload.clear_douyin_cookie,
        )
    )


def verify_local_settings() -> LocalSettingsVerification:
    # Validation runs in-process and may use deployment values, but the API
    # status returned to the browser is always redacted.
    settings = LocalSettingsStatus.model_validate(
        read_local_settings_status(reveal_environment=True)
    )
    actions: list[str] = []
    git = shutil.which("git")
    gh = shutil.which("gh")
    repository = Path(settings.skill_repository_path).expanduser()
    repository_valid = bool(
        settings.skill_repository_path
        and repository.is_dir()
        and (repository / ".git").exists()
    )
    if not settings.skill_repository_path:
        actions.append("填写本机已 clone 的 Skill Git 仓库路径。")
    elif not repository_valid:
        actions.append("Skill 仓库路径必须指向一个已有的 Git 仓库。")

    remote_matches = False
    branch_exists = False
    requires_remote = settings.skill_sync_mode == "github"
    if requires_remote and not settings.skill_remote_url:
        actions.append("填写该 Skill 仓库对应的 GitHub remote URL。")
    if not git:
        actions.append("安装 Git 后才能验证并发布 Skill 包。")
    elif repository_valid:
        if requires_remote:
            try:
                actual_remote = _run_publish_command(
                    [git, "remote", "get-url", "--push", settings.skill_remote],
                    cwd=repository,
                ).stdout.strip().removesuffix("/")
                remote_matches = bool(settings.skill_remote_url) and (
                    actual_remote == settings.skill_remote_url.removesuffix("/")
                )
            except RuntimeError:
                actions.append("仓库中找不到配置的 Git remote。")
            if not remote_matches and settings.skill_remote_url:
                actions.append("本机仓库的推送 remote 必须与填写的 GitHub URL 完全一致。")
        branch_check = subprocess.run(
            [git, "show-ref", "--verify", "--quiet", f"refs/heads/{settings.skill_branch}"],
            cwd=repository,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        branch_exists = branch_check.returncode == 0
        if not branch_exists:
            actions.append("填写的发布分支必须已存在于本机 Skill 仓库。")

    gh_authenticated = False
    if requires_remote and not gh:
        actions.append("安装 GitHub CLI（gh）并完成登录后才能应用内发布。")
    elif requires_remote:
        try:
            gh_authenticated = subprocess.run(
                [gh, "auth", "status"],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            ).returncode == 0
        except OSError:
            gh_authenticated = False
        if not gh_authenticated:
            actions.append("执行 gh auth login 后再发布；应用不会保存 GitHub Token。")

    publish_ready = bool(
        settings.publish_configured
        and bool(git)
        and repository_valid
        and (remote_matches if requires_remote else True)
        and branch_exists
        and (gh_authenticated if requires_remote else True)
    )
    return LocalSettingsVerification(
        publish_ready=publish_ready,
        git_available=bool(git),
        gh_authenticated=gh_authenticated,
        repository_valid=repository_valid,
        remote_matches=remote_matches,
        branch_exists=branch_exists,
        action_items=actions,
        message="发布配置已就绪。" if publish_ready else "发布配置尚未完成。",
    )


def _model_catalog_urls(api_base: str) -> list[str]:
    base = api_base.strip().rstrip("/")
    if not base:
        return []
    urls = [f"{base}/models"]
    if not base.endswith("/v1"):
        urls.append(f"{base}/v1/models")
    return urls


def _model_recommendation_score(model_id: str) -> int:
    value = model_id.lower()
    if any(token in value for token in ("embed", "audio", "tts", "whisper", "image", "moderation", "realtime")):
        return -100
    score = 20 if any(token in value for token in ("gpt", "claude", "gemini", "qwen")) else 0
    score += 4 if any(token in value for token in ("mini", "nano", "small")) else 12
    if any(token in value for token in ("latest", "5", "4.1", "4o", "sonnet", "pro", "max")):
        score += 8
    return score


def discover_configured_models() -> ModelCatalogResponse:
    from app.workbench_llm import get_llm_config

    config = get_llm_config()
    api_key = os.getenv("WORKBENCH_LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not config.api_base or not api_key:
        return ModelCatalogResponse(message="请先保存 API Base 与 API Key，再拉取服务商模型列表。")
    payload: object | None = None
    for url in _model_catalog_urls(config.api_base):
        request = Request(url, headers={"Authorization": f"Bearer {api_key}"})
        try:
            with urlopen(request, timeout=15) as response:  # nosec B310 - local user configuration
                payload = json.loads(response.read().decode("utf-8"))
            break
        except (HTTPError, URLError, TimeoutError, ValueError, OSError):
            continue
    if not isinstance(payload, dict):
        return ModelCatalogResponse(message="服务商未提供兼容的模型列表接口；可手动填写模型名后测试连接。")
    candidates = payload.get("data") or payload.get("models") or []
    if not isinstance(candidates, list):
        candidates = []
    model_ids = sorted(
        {
            str(item.get("id") or item.get("name") or "").strip()
            for item in candidates
            if isinstance(item, dict) and str(item.get("id") or item.get("name") or "").strip()
        },
        key=lambda item: (-_model_recommendation_score(item), item.lower()),
    )[:80]
    usable = [item for item in model_ids if _model_recommendation_score(item) >= 0]
    recommended = usable[0] if usable else (model_ids[0] if model_ids else "")
    return ModelCatalogResponse(
        models=[
            ModelCatalogItem(
                id=model_id,
                recommended=model_id == recommended,
                recommendation_reason=(
                    "优先推荐较新的通用文本模型用于中文长稿结构化输出；请在发布前测试连接。"
                    if model_id == recommended
                    else "可自行选择并作为备选模型。"
                ),
            )
            for model_id in model_ids
        ],
        recommended_model=recommended,
        message=(
            "已拉取模型列表并给出建议。建议仅基于公开模型名称，实际可用性请点击测试连接确认。"
            if model_ids
            else "服务商返回了空模型列表；可手动填写模型名后测试连接。"
        ),
    )


def test_configured_model_connection() -> ModelConnectionCheckResponse:
    result = external_llm_gate(expect_model=True)
    return ModelConnectionCheckResponse(
        passed=bool(result.get("passed")),
        message=(
            "模型连接与结构化调用测试通过。"
            if result.get("passed")
            else "模型连接测试未通过。请检查 API Base、API Key、模型名与服务商权限。"
        ),
    )


def _repository_name(value: str) -> str:
    name = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", name):
        raise ValueError("仓库名只能包含字母、数字、点、下划线和连字符。")
    return name


def _repository_parent(value: Optional[str]) -> Path:
    parent = Path(value).expanduser() if value and value.strip() else workbench_data_root() / "repositories"
    parent = parent.resolve()
    if parent.exists() and not parent.is_dir():
        raise ValueError("本地保存位置必须是目录。")
    parent.mkdir(parents=True, exist_ok=True)
    return parent


def _clean_repository_files() -> dict[str, str]:
    sync_script = "\n".join(
        [
            "#!/usr/bin/env python3",
            "import json, sys",
            "from pathlib import Path, PurePosixPath",
            "from urllib.parse import unquote, urlparse",
            "source = urlparse(sys.argv[1])",
            "pack_path = Path(unquote(source.path)) if source.scheme == 'file' else Path(sys.argv[1])",
            "pack = json.loads(pack_path.read_text(encoding='utf-8'))",
            "version = str(pack['version'])",
            "root = Path(__file__).resolve().parents[1]",
            "runtime = root / 'published' / 'packages' / version / 'runtime'",
            "for relative, content in pack.get('files', {}).items():",
            "    path = PurePosixPath(relative)",
            "    if path.is_absolute() or '..' in path.parts: raise ValueError('Unsafe runtime path')",
            "    target = runtime.joinpath(*path.parts)",
            "    target.parent.mkdir(parents=True, exist_ok=True)",
            "    target.write_text(str(content), encoding='utf-8')",
            "stable = root / 'published' / 'stable'",
            "stable.mkdir(parents=True, exist_ok=True)",
            "manifest = {'version': version, 'runtime_path': str(runtime.relative_to(root))}",
            "(stable / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')",
            "",
        ]
    )
    manifest_script = "\n".join(
        [
            "#!/usr/bin/env python3",
            "import json, sys",
            "from pathlib import Path",
            "root = Path(__file__).resolve().parents[1]",
            "manifest = root / 'published' / 'stable' / 'manifest.json'",
            "data = json.loads(manifest.read_text(encoding='utf-8'))",
            "if not (root / data['runtime_path'] / 'SKILL.md').is_file(): raise SystemExit('Stable runtime is incomplete')",
            "if '--check' not in sys.argv: print(json.dumps(data))",
            "",
        ]
    )
    loader_script = "\n".join(
        [
            "#!/usr/bin/env python3",
            "import json",
            "from pathlib import Path",
            "root = Path(__file__).resolve().parents[1]",
            "manifest = json.loads((root / 'published' / 'stable' / 'manifest.json').read_text(encoding='utf-8'))",
            "print(json.dumps({'status': 'ok', 'runtime_skill_path': str(root / manifest['runtime_path']), 'version': manifest['version']}))",
            "",
        ]
    )
    return {
        "README.md": "# Douyin Writing Skills\n\nManaged by the local Still Settling Workbench. Published runtime files are written under `published/`.\n",
        ".gitignore": "__pycache__/\n*.pyc\n",
        "scripts/sync_from_workbench.py": sync_script,
        "scripts/build_stable_manifest.py": manifest_script,
        "scripts/load_latest.py": loader_script,
        "scripts/install.sh": "#!/usr/bin/env bash\nset -euo pipefail\npython3 scripts/load_latest.py\n",
        "tests/__init__.py": "",
    }


def _initialize_clean_skill_repository(destination: Path) -> None:
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("本地保存目录中已有同名内容；请选择空目录或更换仓库名。")
    destination.mkdir(parents=True, exist_ok=True)
    for relative, content in _clean_repository_files().items():
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    (destination / "scripts" / "install.sh").chmod(0o755)
    _run_publish_command(["git", "init", "-b", "main"], cwd=destination)
    _run_publish_command(["git", "add", "."], cwd=destination)
    _run_publish_command(
        ["git", "-c", "user.name=Still Settling Workbench", "-c", "user.email=workbench@localhost", "commit", "-m", "Initialize empty skill runtime"],
        cwd=destination,
    )


def _github_remote_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
        raise ValueError("请输入完整的 https://github.com/owner/repository 地址。")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2:
        raise ValueError("GitHub 地址必须包含 owner 与 repository。")
    return f"https://github.com/{parts[0]}/{parts[1].removesuffix('.git')}.git"


def _remote_default_branch(repository: Path) -> str:
    try:
        head = _run_publish_command(
            ["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"], cwd=repository
        ).stdout.strip()
        if "/" in head:
            return head.rsplit("/", 1)[-1]
    except RuntimeError:
        pass
    return "main"


def _save_skill_repository_settings(
    *, repository: Path, remote_url: str, sync_mode: Literal["github", "local"], branch: str = "main"
) -> LocalSettingsStatus:
    return update_local_settings(
        LocalSettingsUpdateRequest(
            skill_repository_path=str(repository),
            skill_remote="origin",
            skill_remote_url=remote_url,
            skill_branch=branch,
            skill_sync_mode=sync_mode,
        )
    )


def connect_github_skill_repository(
    payload: GitHubRepositoryConnectRequest,
) -> SkillRepositorySetupResponse:
    remote_url = _github_remote_url(payload.repository_url)
    repository_name = _repository_name(Path(urlparse(remote_url).path).stem)
    destination = _repository_parent(payload.local_parent_path) / repository_name
    if destination.exists():
        raise ValueError("本地已存在同名目录；请更换保存位置或仓库名。")
    _run_publish_command(
        ["git", "clone", remote_url, str(destination)], cwd=destination.parent, timeout=180
    )
    settings = _save_skill_repository_settings(
        repository=destination,
        remote_url=remote_url,
        sync_mode="github",
        branch=_remote_default_branch(destination),
    )
    return SkillRepositorySetupResponse(
        settings=settings,
        message="已连接 GitHub 仓库并自动完成本机发布配置。",
    )


def create_github_skill_repository(
    payload: GitHubRepositoryCreateRequest,
) -> SkillRepositorySetupResponse:
    gh = shutil.which("gh")
    if not gh:
        raise ValueError("未检测到 GitHub CLI（gh）。请安装并完成 gh auth login 后重试。")
    auth = subprocess.run([gh, "auth", "status"], capture_output=True, text=True, timeout=20, check=False)
    if auth.returncode != 0:
        raise ValueError("GitHub CLI 尚未登录。请先执行 gh auth login。")
    name = _repository_name(payload.repository_name)
    destination = _repository_parent(payload.local_parent_path) / name
    _initialize_clean_skill_repository(destination)
    _run_publish_command(
        [gh, "repo", "create", name, f"--{payload.visibility}", "--source", str(destination), "--remote", "origin", "--push"],
        cwd=destination,
        timeout=180,
    )
    remote_url = _run_publish_command(
        ["git", "remote", "get-url", "--push", "origin"], cwd=destination
    ).stdout.strip()
    settings = _save_skill_repository_settings(
        repository=destination, remote_url=remote_url, sync_mode="github"
    )
    return SkillRepositorySetupResponse(
        settings=settings,
        message="已创建 GitHub 仓库并保存本机发布配置。",
    )


def create_local_skill_repository(
    payload: LocalRepositoryCreateRequest,
) -> SkillRepositorySetupResponse:
    name = _repository_name(payload.repository_name)
    destination = _repository_parent(payload.local_parent_path) / name
    _initialize_clean_skill_repository(destination)
    settings = _save_skill_repository_settings(
        repository=destination, remote_url="", sync_mode="local"
    )
    return SkillRepositorySetupResponse(
        settings=settings,
        message="已创建本地 Skill 仓库；后续发布只保存在此设备。",
    )


def write_human_review_template(
    path: Optional[Path] = None,
    scripts: Optional[list[GeneratedScript]] = None,
) -> list[HumanReviewItem]:
    path = path or human_review_template_path()
    items: list[HumanReviewItem] = []
    for index in range(1, 11):
        script = scripts[index - 1] if scripts and index <= len(scripts) else None
        items.append(
            HumanReviewItem(
                id=f"hotspot_review_{index:02d}"
                if script is None
                else f"hotspot_review_{index:02d}_{script.id}",
                hotspot=script.content_angle if script else "",
                script_title=script.title if script else "",
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            [item.model_dump(mode="json") for item in items],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return items


def read_human_review_template(
    path: Optional[Path] = None,
) -> list[HumanReviewItem]:
    path = path or human_review_template_path()
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("人审文件必须是数组。")
    items: list[HumanReviewItem] = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            continue
        merged = {"id": f"hotspot_review_{index:02d}", **item}
        items.append(HumanReviewItem.model_validate(merged))
    return items


def save_human_review_template(
    items: list[HumanReviewItem], path: Optional[Path] = None
) -> list[HumanReviewItem]:
    path = path or human_review_template_path()
    normalized = items[:10]
    while len(normalized) < 10:
        normalized.append(
            HumanReviewItem(id=f"hotspot_review_{len(normalized) + 1:02d}")
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            [item.model_dump(mode="json") for item in normalized],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return normalized


def human_review_gate(
    path: Optional[Path] = None, write_template: bool = False
) -> dict:
    if write_template:
        write_human_review_template()
    review_path = path or human_review_template_path()
    result: dict = {
        "passed": False,
        "status": "missing_external_input",
        "required_count": 10,
        "passed_count": 0,
        "action_items": [
            "人工抽检 10 个热点脚本。",
            "每条记录必须满足 shootable、not_pure_rewrite、clear_structure、risk_passed。",
        ],
    }
    if not review_path.exists():
        result["status"] = "missing_review_file"
        result["action_items"].append("点击生成模板，填写后再运行外部门禁检查。")
        return result
    try:
        payload = json.loads(review_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        result["status"] = "invalid_review_file"
        result["action_items"].append(f"人审文件不是合法 JSON：{exc}")
        return result
    if not isinstance(payload, list):
        result["status"] = "invalid_review_file"
        result["action_items"].append("人审文件必须是数组。")
        return result

    required_flags = ("shootable", "not_pure_rewrite", "clear_structure", "risk_passed")
    passed_items = [
        item
        for item in payload
        if isinstance(item, dict)
        and all(item.get(flag) is True for flag in required_flags)
    ]
    result.update(
        {
            "passed_count": len(passed_items),
            "total_count": len(payload),
            "passed": len(passed_items) >= 10,
            "status": "completed"
            if len(passed_items) >= 10
            else "insufficient_passed_reviews",
        }
    )
    if len(passed_items) < 10:
        result["action_items"].append(
            f"当前只有 {len(passed_items)} 条通过，需要至少 10 条。"
        )
    return result


def external_link_gate(link: Optional[str] = None, run_link: bool = False) -> dict:
    ytdlp_ready = is_ytdlp_configured()
    douyin_downloader_ready = is_douyin_downloader_configured()
    downloader_ready = ytdlp_ready or douyin_downloader_ready
    normalized_link = normalize_douyin_url_input(link or "") if link else ""
    ready_to_test = downloader_ready and bool(normalized_link)
    result: dict = {
        "passed": False,
        "status": "not_run",
        "downloader_configured": downloader_ready,
        "yt_dlp_configured": ytdlp_ready,
        "douyin_downloader_configured": douyin_downloader_ready,
        "resolver_chain": [
            name
            for name, ready in [
                ("yt-dlp", ytdlp_ready),
                ("douyin-downloader", douyin_downloader_ready),
            ]
            if ready
        ],
        "downloader_mode": douyin_downloader_mode(),
        "cookie_configured": has_douyin_cookie_config(),
        "input_link": link or "",
        "normalized_link": normalized_link,
        "ready_to_test": ready_to_test,
        "action_items": [],
    }
    if not downloader_ready:
        result["action_items"].append(
            "安装 yt-dlp，或配置 WORKBENCH_DOUYIN_DOWNLOADER_DIR / WORKBENCH_DOUYIN_DOWNLOADER_CMD。"
        )
    if not normalized_link:
        result["action_items"].append("粘贴完整抖音分享文案或 v.douyin.com 短链。")
    if not run_link:
        result["status"] = "ready" if ready_to_test else "missing_external_input"
        result["passed"] = ready_to_test
        result["action_items"].append(
            "准备好链接后会自动使用本机浏览器会话提取；个别作品仍可能要求有效的抖音 Cookie。"
        )
        return result

    if not ready_to_test:
        result["status"] = "missing_external_input"
        return result

    response = create_link_task(LinkTaskRequest(url=normalized_link))
    fallback_ready = bool(response.fallback_inputs)
    link_usable = (
        response.parser_status == "completed" and response.video_upload is not None
    )
    result.update(
        {
            "status": response.parser_status,
            "passed": link_usable,
            "parser_error_code": response.parser_error_code,
            "parser_error_title": response.parser_error_title,
            "parser_error_detail": response.parser_error_detail,
            "downloaded_file_count": len(response.downloaded_files),
            "has_video_upload": response.video_upload is not None,
            "fallback_ready": fallback_ready,
            "fallback_inputs": response.fallback_inputs,
            "message": response.message,
        }
    )
    if not result["passed"]:
        result["action_items"].extend(
            response.parser_action_items or ["确认分享文案里包含完整短链后重试。"]
        )
    elif response.parser_status != "completed":
        result["action_items"].extend(
            [
                "公开视频下载未成功。",
                "当前不会用标题或描述伪造稿件。",
            ]
        )
    return result


def external_llm_gate(expect_model: bool = False) -> dict:
    from app.workbench_llm import get_llm_config

    config = get_llm_config()
    settings = read_local_settings_status()
    model_source = settings.get("sources", {}).get("llm_model")
    key_ready = credential_present()
    model_ready = config.mode != "offline" and key_ready
    result = {
        "passed": model_ready if expect_model else config.mode != "offline",
        "status": "ready" if model_ready else "missing_external_input",
        "mode": config.mode,
        "model": "由启动环境管理" if model_source == "environment" else config.model,
        "api_base_configured": bool(config.api_base),
        "api_key_configured": key_ready,
        "expect_model": expect_model,
        "action_items": []
        if model_ready
        else [
            "设置 WORKBENCH_LLM_MODE=optional 或 required。",
            "配置 WORKBENCH_LLM_API_KEY；如使用中转站，同时配置 WORKBENCH_LLM_API_BASE。",
            "配置后运行真实模型 smoke。",
        ],
    }
    if not expect_model or not model_ready:
        return result

    try:
        from app.workbench_llm import analyze_transcript_structured

        smoke_text = "只根据公开信息复盘热点，不编造隐私，不做人身攻击，输出可拍摄短视频脚本结构。"
        smoke_result = analyze_transcript_structured(
            Transcript(
                id="external_gate_llm_smoke",
                source_video_id="external_gate",
                asr_text=smoke_text,
                ocr_text="",
                content_text=smoke_text,
                timestamps=[],
                confidence=1.0,
                source="external_gate",
            )
        )
        schema_ready = (
            bool(smoke_result.analysis.hook)
            and len(smoke_result.analysis.structure) >= 3
            and len(smoke_result.analysis.emotion_curve) >= 3
        )
        result.update(
            {
                "passed": bool(smoke_result.status.used_model and schema_ready),
                "status": "model_used"
                if smoke_result.status.used_model and schema_ready
                else "smoke_failed",
                "used_model": smoke_result.status.used_model,
                "schema_ready": schema_ready,
                "error": smoke_result.status.error,
            }
        )
        if not result["passed"]:
            result["action_items"] = [
                "真实模型调用未通过结构化 smoke；检查 API Key、API Base、模型名和余额/权限。"
            ]
    except Exception as exc:
        result.update(
            {
                "passed": False,
                "status": "smoke_failed",
                "used_model": False,
                "schema_ready": False,
                "error": clean_text(str(exc))[:220],
                "action_items": [
                    "真实模型调用失败；检查 API Key、API Base、模型名和余额/权限。"
                ],
            }
        )
    return result


def external_gate_report(
    link: Optional[str] = None, run_link: bool = False, expect_model: bool = False
) -> ExternalGateReport:
    link_result = external_link_gate(link, run_link)
    llm_result = external_llm_gate(expect_model)
    human_result = human_review_gate()
    report = {
        "passed": link_result["passed"]
        and llm_result["passed"]
        and human_result["passed"],
        "link_gate": link_result,
        "llm_gate": llm_result,
        "human_review_gate": human_result,
    }
    report_path = external_gates_report_path()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    items = [
        ExternalGateItem(
            key="link",
            label="真实抖音链接",
            passed=bool(link_result["passed"]),
            status=str(link_result["status"]),
            detail="免登录链接提取已拿到可处理视频。"
            if link_result["passed"]
            else "还没有从分享链接拿到可转写视频。",
            action_items=list(link_result.get("action_items") or []),
        ),
        ExternalGateItem(
            key="llm",
            label="真实 LLM",
            passed=bool(llm_result["passed"]),
            status=str(llm_result["status"]),
            detail=(
                "真实模型调用已就绪。"
                if llm_result["passed"]
                else "真实模型 smoke 未通过。"
                if llm_result["status"] == "smoke_failed"
                else "当前仍是离线或缺少模型密钥。"
            ),
            action_items=list(llm_result.get("action_items") or []),
        ),
        ExternalGateItem(
            key="human_review",
            label="人工质量复核",
            passed=bool(human_result["passed"]),
            status=str(human_result["status"]),
            detail=f"已通过 {human_result.get('passed_count', 0)}/{human_result.get('required_count', 10)} 条人审。",
            action_items=list(human_result.get("action_items") or []),
        ),
    ]
    return ExternalGateReport(
        passed=bool(report["passed"]),
        items=items,
        link_gate=link_result,
        llm_gate=llm_result,
        human_review_gate=human_result,
        report_path="",
    )


def clean_items(items: list[str]) -> list[str]:
    seen: set[str] = set()
    cleaned: list[str] = []
    for item in items:
        value = clean_text(item)
        if value and value not in seen:
            cleaned.append(value)
            seen.add(value)
    return cleaned


def infer_skill_capabilities(
    name: str,
    skeleton: list[str],
    hook_formula: str,
    emotion_rhythm: str,
) -> tuple[list[str], list[str], list[str], list[str]]:
    """Infer cross-topic writing uses from structure, never from the source subject alone."""
    structure_text = " ".join([name, *skeleton, hook_formula, emotion_rhythm])
    solves = ["让开头更快建立阅读理由", "把散点信息整理成可拍摄的推进结构"]
    scenes = [
        "已有明确事实或结论，但缺少一个能让观众继续看的切入角度",
        "素材里有多个信息点，但还没有形成清晰的推进顺序",
        "只有态度或判断，需要补出过程、证据和收束逻辑",
        "用户容易先入为主，需要用反常识切入重新组织认知",
    ]
    signals = ["开头平", "信息散", "缺少观点", "结尾弱"]
    labels: list[str] = []

    if any(word in structure_text for word in ["反差", "反转", "冲突", "对比", "爆点"]):
        solves.extend(["用反差制造停留点", "把表层事件推进到新的判断"])
        scenes.extend(
            [
                "表面结果和真实原因存在错位，需要先抛结果再翻转解释",
                "个体遭遇和规则流程发生冲突，需要把经历写成结构矛盾",
                "观众以为答案已经很明显，但后面还有一层更关键的解释",
            ]
        )
        signals.extend(["有前后变化", "有表里反差", "有输赢反转", "需要改写认知"])
        labels.extend(["反差切入", "事实反转", "观点升维"])
    if any(
        word in structure_text
        for word in ["背景", "时间", "信息", "分步", "利益", "解释"]
    ):
        solves.extend(["补齐必要背景", "让复杂信息按因果顺序推进"])
        scenes.extend(
            [
                "观众只看到结果，不知道前因后果，需要补出因果链路",
                "信息跨度较长，需要按时间、关系或机制拆成几个层次",
                "多个角色或变量互相影响，需要先搭框架再给判断",
            ]
        )
        signals.extend(["背景复杂", "需要时间线", "因果不清", "信息密度高"])
        labels.extend(["背景拆解", "因果推进"])
    if any(word in structure_text for word in ["情绪", "共鸣", "痛点", "态度", "价值"]):
        solves.extend(["增强用户代入和情绪递进", "把事实落到可感知的价值判断"])
        scenes.extend(
            [
                "事实本身不复杂，但需要从具体细节引出共鸣和态度",
                "内容容易空喊价值，需要用可感知场景承接抽象判断",
                "需要从单个经历推进到一类人的共同感受或选择",
            ]
        )
        signals.extend(["情绪不足", "需要代入", "有价值冲突", "需要态度收口"])
        labels.extend(["情绪递进", "价值表达"])
    if any(word in structure_text for word in ["评论", "互动", "提问", "站队"]):
        solves.append("给结尾补一个自然的讨论入口")
        scenes.append("主体信息已经讲清楚，但结尾缺少一个可回答的讨论入口")
        signals.extend(["缺少互动", "需要讨论", "结尾无力"])
        labels.append("互动收口")

    return (
        clean_items(solves)[:6],
        clean_items(scenes)[:10],
        clean_items(signals)[:12],
        clean_items(labels)[:6] or ["结构补全", "观点推进"],
    )


THEMATIC_SCENE_TERMS = (
    "电商",
    "售后",
    "换货",
    "客服",
    "订单",
    "赔付",
    "补偿",
    "职场",
    "审批",
    "绩效",
    "品牌客服",
    "合作对账",
    "合同",
    "账单",
    "明星",
    "粉丝",
    "综艺",
    "代言",
    "产品口碑",
    "行业",
)


def structural_applicable_scenes(
    items: list[str],
    skeleton: list[str],
    hook_formula: str,
    emotion_rhythm: str,
) -> list[str]:
    """Keep applicability at the reusable structure level instead of source/topic level."""
    _solves, inferred, _signals, _labels = infer_skill_capabilities(
        "结构适用条件",
        skeleton,
        hook_formula,
        emotion_rhythm,
    )
    structural_markers = (
        "结果",
        "原因",
        "事实",
        "结论",
        "过程",
        "证据",
        "结构",
        "推进",
        "反差",
        "冲突",
        "因果",
        "信息点",
        "判断",
        "情绪",
        "共鸣",
        "收束",
        "讨论入口",
        "认知",
    )
    cleaned = []
    for item in clean_items(items):
        if any(term in item for term in THEMATIC_SCENE_TERMS):
            continue
        if not any(marker in item for marker in structural_markers):
            continue
        cleaned.append(item)
    return _semantic_unique([*inferred, *cleaned])[:8]


def _operator_skill_name(
    name: str, skeleton: list[str], hook_formula: str, emotion_rhythm: str
) -> str:
    structural_terms = (
        "钩子",
        "递进",
        "并列",
        "串联",
        "反差",
        "反转",
        "转折",
        "因果",
        "拆解",
        "升维",
        "共鸣",
        "收束",
        "推进",
        "悬念",
        "对照",
        "互动",
    )
    thematic_terms = (
        "信念",
        "命运",
        "励志",
        "成功",
        "逆袭",
        "明星",
        "品牌",
        "人物",
        "女性",
        "职场",
        "爱情",
        "成长",
    )
    if (
        len(name) <= 12
        and not re.search(r"测试写作|\d{8,}|复用模板", name)
        and any(term in name for term in structural_terms)
        and not any(term in name for term in thematic_terms)
    ):
        return name
    text = " ".join([*skeleton, hook_formula, emotion_rhythm])
    if any(word in text for word in ["多案例", "多个案例", "并列", "串联", "群像"]):
        if any(word in text for word in ["命题", "金句", "判断", "预言"]):
            return "命题钩子·多例递进"
        return "多例串联·递进收束"
    if any(word in text for word in ["反差", "反转", "冲突", "爆点"]) and any(
        word in text for word in ["升维", "观点", "价值", "态度"]
    ):
        return "反差钩子·转折升维"
    if any(word in text for word in ["背景", "时间", "利益", "因果"]):
        return "背景拆解·因果推进"
    if any(word in text for word in ["共鸣", "情绪", "痛点"]):
        return "情绪递进·观点收束"
    if any(word in text for word in ["评论", "互动", "提问", "站队"]):
        return "问题钩子·互动收束"
    return "信息钩子·递进收束"


def _usable_applicable_scenes(items: list[str]) -> list[str]:
    ignored_prefixes = ("账号：", "匹配关键词：", "适合：")
    cleaned = [
        item
        for item in items
        if not item.startswith(ignored_prefixes)
        and "测试写作 Skill" not in item
        and item not in {"商业分析号", "娱乐吃瓜号", "泛娱乐观点号"}
        and item
        not in {"而不是复述原事件。", "人工确认后复用", "反差对比型", "背景拆解型"}
    ]
    fragment_starts = {
        "有公开事实",
        "只有想法或素材",
        "人物选择",
        "品牌动作",
        "影视综艺",
        "消费体验",
        "只有结论",
    }
    joined: list[str] = []
    index = 0
    while index < len(cleaned):
        current = cleaned[index]
        if current in fragment_starts and index + 1 < len(cleaned):
            joined.append(f"{current}，{cleaned[index + 1]}")
            index += 2
            continue
        joined.append(current)
        index += 1
    return clean_items([item for item in joined if item not in fragment_starts])


def _structure_labels(items: list[str]) -> list[str]:
    capability_words = [
        "结构",
        "切入",
        "反差",
        "反转",
        "背景",
        "因果",
        "情绪",
        "观点",
        "互动",
        "升维",
        "推进",
        "收口",
        "拆解",
    ]
    return clean_items(
        [item for item in items if any(word in item for word in capability_words)]
    )


def _semantic_unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in clean_items(items):
        key = re.sub(r"[\s，、,；;：:]", "", item)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def skill_pattern_fingerprint(
    skeleton: list[str],
    hook_formula: str,
    emotion_rhythm: str,
    ending_formula: str,
) -> str:
    normalized = "|".join(
        re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", value.lower())
        for value in [*skeleton, hook_formula, emotion_rhythm, ending_formula]
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]


def merge_skill_sources(*groups: list[SkillSourceRecord]) -> list[SkillSourceRecord]:
    merged: list[SkillSourceRecord] = []
    source_indexes: dict[str, int] = {}
    for source in (item for group in groups for item in group):
        normalized_url = (
            (source.url or "").split("?", 1)[0].split("#", 1)[0].rstrip("/")
        )
        transcript_fingerprint = (
            hashlib.sha256(clean_text(source.transcript).encode("utf-8")).hexdigest()[
                :20
            ]
            if source.transcript
            else ""
        )
        key = (
            f"url:{normalized_url}"
            if normalized_url
            else f"transcript:{transcript_fingerprint}"
            if transcript_fingerprint
            else f"video:{source.source_video_id}"
        )
        if key in source_indexes:
            index = source_indexes[key]
            current = merged[index]
            source_is_newer = bool(
                source.recognized_at
                and (
                    current.recognized_at is None
                    or source.recognized_at >= current.recognized_at
                )
            )
            primary, secondary = (
                (source, current) if source_is_newer else (current, source)
            )
            transcript = max(
                (current.transcript, source.transcript),
                key=lambda item: len(item or ""),
            )
            merged[index] = current.model_copy(
                update={
                    "source_video_id": primary.source_video_id
                    or secondary.source_video_id,
                    "source_analysis_id": primary.source_analysis_id
                    or secondary.source_analysis_id,
                    "title": primary.title or secondary.title,
                    "author": primary.author or secondary.author,
                    "url": primary.url or secondary.url,
                    "transcript": transcript,
                    "recognized_at": primary.recognized_at or secondary.recognized_at,
                }
            )
            continue
        source_indexes[key] = len(merged)
        merged.append(source)
    return merged


def structural_evidence_from_sources(template: TemplatePattern) -> list[SkillEvidence]:
    evidence = list(template.evidence)
    recorded = {
        (item.source_url.rstrip("/"), item.scope)
        for item in evidence
        if item.source_url
    }
    for source in template.sources:
        if not source.title.strip() or source.title.strip() == "暂无来源记录":
            continue
        source_url = source.url or f"local://source/{source.source_video_id}"
        key = (source_url.rstrip("/"), "structure")
        if key in recorded:
            continue
        fingerprint = hashlib.sha256(
            f"{source.source_video_id}|{source_url}".encode("utf-8")
        ).hexdigest()[:16]
        evidence.append(
            SkillEvidence(
                id=f"evidence_{fingerprint}",
                claim=f"《{source.title}》提供了可复用的写作结构样本。",
                source_title=source.title,
                source_url=source_url,
                source_type="authorized_source",
                evidence_tier="A",
                quote=clean_text(source.transcript)[:600],
                scope="structure",
                checked_at=source.recognized_at or now_utc(),
            )
        )
        recorded.add(key)
    return evidence


def _text_similarity(left: str, right: str) -> float:
    left_clean = re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", left.lower())
    right_clean = re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", right.lower())
    if not left_clean or not right_clean:
        return 0.0
    return SequenceMatcher(None, left_clean, right_clean).ratio()


def skill_structure_similarity(
    left: TemplatePattern | PresetDraft, right: TemplatePattern | PresetDraft
) -> int:
    if (
        left.pattern_fingerprint
        and left.pattern_fingerprint == right.pattern_fingerprint
    ):
        return 100
    score = (
        0.45 * _text_similarity(" ".join(left.skeleton), " ".join(right.skeleton))
        + 0.20 * _text_similarity(left.hook_formula, right.hook_formula)
        + 0.20 * _text_similarity(left.emotion_rhythm, right.emotion_rhythm)
        + 0.10 * _text_similarity(left.ending_formula, right.ending_formula)
        + 0.05 * _text_similarity(left.name, right.name)
    )
    return round(score * 100)


def enrich_skill_template(template: TemplatePattern) -> TemplatePattern:
    solves, scenes, signals, labels = infer_skill_capabilities(
        template.name,
        template.skeleton,
        template.hook_formula,
        template.emotion_rhythm,
    )
    fingerprint = template.pattern_fingerprint or skill_pattern_fingerprint(
        template.skeleton,
        template.hook_formula,
        template.emotion_rhythm,
        template.ending_formula,
    )
    existing_scenes = _usable_applicable_scenes(template.applicable_scenes)
    scene_order = structural_applicable_scenes(
        [*scenes, *existing_scenes],
        template.skeleton,
        template.hook_formula,
        template.emotion_rhythm,
    )
    evidence = structural_evidence_from_sources(template)
    return template.model_copy(
        update={
            "name": _operator_skill_name(
                template.name,
                template.skeleton,
                template.hook_formula,
                template.emotion_rhythm,
            ),
            "solves_problems": clean_items([*template.solves_problems, *solves])[:8],
            "match_signals": clean_items([*template.match_signals, *signals])[:14],
            "applicable_scenes": scene_order[:12],
            "unsuitable_scenes": _usable_applicable_scenes(template.unsuitable_scenes)[
                :10
            ],
            "hotspot_types": clean_items(
                [*_structure_labels(template.hotspot_types), *labels]
            )[:10],
            "source_count": max(
                template.source_count,
                len(template.sources),
                len(template.source_titles),
                0,
            ),
            "evidence": evidence,
            "pattern_fingerprint": fingerprint,
            "platforms": clean_items(template.platforms) or ["douyin"],
            "required_inputs": clean_items(template.required_inputs) or [
                "明确主题或已核验事实",
                "可用于口播的具体细节",
            ],
            "output_contract": clean_items(template.output_contract) or [
                "抖音口播稿、分镜建议、字幕节奏和评论引导",
                "不复制来源原句，不编造未核验事实",
            ],
        }
    )


def deduplicate_templates(templates: list[TemplatePattern]) -> list[TemplatePattern]:
    """Collapse historical exact-structure duplicates without deleting persisted records."""
    grouped: dict[str, TemplatePattern] = {}
    order: list[str] = []
    for raw_template in templates:
        template = enrich_skill_template(raw_template)
        template = template.model_copy(
            update={
                "source_count": max(
                    template.source_count,
                    len(template.sources),
                    len(template.source_titles),
                    0,
                )
            }
        )
        key = template.pattern_fingerprint
        if key not in grouped:
            grouped[key] = template
            order.append(key)
            continue
        current = grouped[key]
        if not skill_has_source_evidence(current) and skill_has_source_evidence(template):
            base = template
            other = current
        else:
            base = current
            other = template
        source_titles = clean_items([*base.source_titles, *other.source_titles])
        sources = merge_skill_sources(base.sources, other.sources)
        grouped[key] = base.model_copy(
            update={
                "solves_problems": clean_items(
                    [*base.solves_problems, *other.solves_problems]
                )[:8],
                "match_signals": clean_items(
                    [*base.match_signals, *other.match_signals]
                )[:14],
                "applicable_scenes": structural_applicable_scenes(
                    [*base.applicable_scenes, *other.applicable_scenes],
                    base.skeleton,
                    base.hook_formula,
                    base.emotion_rhythm,
                )[:12],
                "hotspot_types": clean_items(
                    [*base.hotspot_types, *other.hotspot_types]
                )[:10],
                "source_titles": source_titles,
                "sources": sources,
                "source_count": max(
                    base.source_count,
                    other.source_count,
                    len(sources),
                    len(source_titles),
                    0,
                ),
                "quality_score": max(base.quality_score, other.quality_score),
                "usage_count": base.usage_count + other.usage_count,
            }
        )
    return [grouped[key] for key in order]


def _skill_file_slug(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", value).strip("-")
    return slug[:64] or "writing-skill"


def _template_user_choice_summary(template: TemplatePattern) -> str:
    scene = template.applicable_scenes[0] if template.applicable_scenes else ""
    problem = template.solves_problems[0] if template.solves_problems else ""
    if scene and problem:
        return f"适合{scene}；重点解决{problem}"
    if scene:
        return f"适合{scene}"
    if problem:
        return f"重点解决{problem}"
    return f"适合{template.account_type}的短视频口播结构重写"


def _template_writing_method(template: TemplatePattern) -> str:
    skeleton_preview = " -> ".join(template.skeleton[:4])
    if len(template.skeleton) > 4:
        skeleton_preview = f"{skeleton_preview} -> ..."
    parts = [
        f"开头用「{template.hook_formula}」先建立观看理由",
        f"中段按「{skeleton_preview}」推进",
        f"情绪节奏控制为「{template.emotion_rhythm}」",
        f"结尾用「{template.ending_formula}」收束并引导评论",
    ]
    return "；".join(parts)


def _template_research_needs(template: TemplatePattern) -> list[str]:
    text = " ".join(
        [
            template.name,
            template.hook_formula,
            template.emotion_rhythm,
            template.ending_formula,
            *template.hotspot_types,
            *template.solves_problems,
            *template.match_signals,
            *template.applicable_scenes,
            *template.skeleton,
        ]
    )
    needs = [
        "核验用户输入中的关键事实、时间线、当事人回应和最新进展。",
        "补充与主题直接相关的公开素材、案例细节、评论区情绪和平台语境。",
    ]
    if any(marker in text for marker in ["反差", "反转", "冲突", "结果"]):
        needs.append("查清表面说法与真实原因之间的差异，避免只凭反差标题硬写。")
    if any(marker in text for marker in ["背景", "时间线", "拆解", "因果"]):
        needs.append("整理事件前因后果、关键节点和不同来源之间的说法差异。")
    if any(marker in text for marker in ["情绪", "共鸣", "痛点", "代入"]):
        needs.append("观察目标平台用户的高频情绪词、评论争议点和可共鸣细节。")
    if any(marker in text for marker in ["人物", "成长", "经历", "作品"]):
        needs.append("补齐人物经历、作品节点、公开采访或可核实人生细节。")
    if any(marker in text for marker in ["品牌", "商业", "公关", "平台"]):
        needs.append("核对品牌/机构官方回应、业务背景、行业规则和公开责任边界。")
    return clean_items(needs)[:8]


def _skill_added_at(template: TemplatePattern) -> datetime:
    if template.source_count == 0 and not template.sources and not template.source_titles:
        return datetime(2026, 1, 1, tzinfo=timezone.utc)
    if template.created_at:
        return template.created_at
    source_time = max(
        (source.recognized_at for source in template.sources if source.recognized_at),
        default=None,
    )
    if source_time:
        return source_time
    return datetime(2026, 1, 1, tzinfo=timezone.utc)


def sort_skill_templates(templates: list[TemplatePattern]) -> list[TemplatePattern]:
    return sorted(templates, key=_skill_added_at, reverse=True)


def _template_reference_markdown(template: TemplatePattern) -> str:
    sources = template.sources or []
    source_lines = "\n".join(
        f"- {source.title}；作者：{source.author or '未识别'}；链接：{source.url or '未记录'}"
        for source in sources[:8]
    )
    if not source_lines:
        source_lines = "\n".join(f"- {title}" for title in template.source_titles[:8])
    if not source_lines:
        source_lines = "- 暂无来源记录"

    skeleton = "\n".join(
        f"{index}. {step}" for index, step in enumerate(template.skeleton, start=1)
    )
    solves = "\n".join(f"- {item}" for item in template.solves_problems) or "- 待补充"
    scenes = "\n".join(f"- {item}" for item in template.applicable_scenes) or "- 待补充"
    signals = "\n".join(f"- {item}" for item in template.match_signals) or "- 待补充"
    unsuitable = "\n".join(f"- {item}" for item in template.unsuitable_scenes) or "- 待补充"
    research_needs = "\n".join(
        f"- {item}" for item in _template_research_needs(template)
    )
    choice_summary = _template_user_choice_summary(template)
    writing_method = _template_writing_method(template)
    return f"""# {template.name}

## 使用原则

这是一个可复用写作结构，不是固定文案模板。使用时只迁移结构、节奏、判断方式和复用边界，不复制来源视频原句。

## 给用户看的写法说明

{choice_summary}

大概写法：{writing_method}

当用户选择这个 Skill 后，先把用户要写的主题/热点映射到下面的结构骨架，再判断还缺哪些事实、案例或情绪细节。事实不够时先提示补素材或联网核验，不要用空泛判断硬写。

## 使用前需要补齐的外部信息

{research_needs}

## 适合解决

{solves}

## 适用场景

{scenes}

## 匹配信号

{signals}

## 结构骨架

{skeleton}

## 用户选择后的写作流程

1. 先复述用户要写的内容类型、传播目标和当前素材缺口。
2. 把用户主题逐段映射到「结构骨架」，说明每一段承担什么作用。
3. 需要事实、人物经历、案例细节或时间线时，先核验或提醒用户补充，再写进稿件。
4. 正式写作时保留这个 Skill 的推进顺序和情绪节奏，但不要套用来源视频原句。
5. 结尾先服务当前主题，再做评论引导；不要为了套公式而生硬升华。

## 写法公式

- 开头钩子：{template.hook_formula}
- 情绪节奏：{template.emotion_rhythm}
- 结尾公式：{template.ending_formula}

## 不能碰的边界

{template.risk_boundary}

## 不适用场景

{unsuitable}

## 来源

{source_lines}

## 维护信息

- 质量分：{template.quality_score}
- 来源数量：{template.source_count}
- 复用次数：{template.usage_count}
- 添加日期：{_skill_added_at(template).date().isoformat()}
- 复盘备注：{template.last_review_note or '暂无'}
"""


def _atomic_skill_directory(template: TemplatePattern) -> str:
    return f"douyin-writing-{template.id.lower().replace('_', '-')[:40]}"


def _atomic_skill_markdown(template: TemplatePattern) -> str:
    trigger = "；".join(template.match_signals[:5]) or "需要明确的短视频口播结构"
    unsuitable = "；".join(template.unsuitable_scenes[:4]) or "未核验事实、隐私或攻击性表达"
    skeleton = "\n".join(f"{index}. {step}" for index, step in enumerate(template.skeleton, 1))
    inputs = "\n".join(f"- {item}" for item in template.required_inputs)
    outputs = "\n".join(f"- {item}" for item in template.output_contract)
    return f"""---
name: {_atomic_skill_directory(template)}
description: Apply the {template.name} Douyin short-video writing structure when a request has these signals: {trigger}. Do not use for: {unsuitable}. Requires verified facts when the topic is current or high-risk.
---

# {template.name}

## Required inputs

{inputs}

## Research before writing

For current, disputed, or high-risk claims, verify the core fact and use original or official sources before drafting. Stop when the premise is refuted, unsupported, or requires private information.

## Structure

{skeleton}

## Writing method

- Hook: {template.hook_formula}
- Rhythm: {template.emotion_rhythm}
- Ending: {template.ending_formula}
- Boundary: {template.risk_boundary}

## Output contract

{outputs}

Use the structure and judgment pattern only. Do not copy wording, scenes, or claims from source videos. See `references/evidence.json` for the approved evidence snapshot.
"""


def _atomic_skill_sync_script() -> str:
    return '''#!/usr/bin/env python3
"""Install only the workbench-managed router and atomic Skills into a Codex skill root."""
from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path


MANAGED_STATE = ".douyin-writing-managed.json"
MANAGED_PATTERN = re.compile(r"^douyin-writing-(router|[a-z0-9-]{1,48})$")


def valid_directory(value):
    return isinstance(value, str) and bool(MANAGED_PATTERN.fullmatch(value))


def read_managed(root):
    path = root / MANAGED_STATE
    if not path.exists():
        return []
    try:
        values = json.loads(path.read_text(encoding="utf-8")).get("directories", [])
    except (OSError, json.JSONDecodeError):
        return []
    return [value for value in values if valid_directory(value)]


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: install_atomic_skills.py <skill-pack-url> [codex-skill-root]", file=sys.stderr)
        return 2
    root = Path(sys.argv[2]).expanduser() if len(sys.argv) > 2 else Path.home() / ".codex" / "skills"
    with urllib.request.urlopen(sys.argv[1], timeout=45) as response:
        payload = json.load(response)
    files = payload.get("files") or {}
    managed = (payload.get("install_manifest") or {}).get("managed_directories") or []
    if not managed or not all(valid_directory(item) for item in managed):
        raise RuntimeError("Skill pack does not contain an atomic install manifest")
    if len(set(managed)) != len(managed):
        raise RuntimeError("Skill pack contains duplicate managed directories")
    staging = Path(tempfile.mkdtemp(prefix="douyin-atomic-skills-"))
    try:
        for directory in managed:
            prefix = f"{directory}/"
            entries = {path: body for path, body in files.items() if path.startswith(prefix)}
            if not entries:
                raise RuntimeError(f"Missing files for managed Skill directory: {directory}")
            for path, body in entries.items():
                relative = Path(path).relative_to(directory)
                if ".." in relative.parts:
                    raise RuntimeError("Unsafe Skill path")
                destination = staging / directory / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(body, encoding="utf-8")
        root.mkdir(parents=True, exist_ok=True)
        previously_managed = set(read_managed(root))
        for directory in managed:
            source, destination = staging / directory, root / directory
            if destination.exists() and directory not in previously_managed:
                raise RuntimeError(
                    f"Refusing to replace unmanaged Skill directory: {directory}"
                )
            backup = root / f".{directory}.backup"
            if backup.exists():
                shutil.rmtree(backup)
            if destination.exists():
                destination.rename(backup)
            shutil.move(str(source), str(destination))
            if backup.exists():
                shutil.rmtree(backup)
        for directory in previously_managed - set(managed):
            target = root / directory
            if target.exists():
                shutil.rmtree(target)
        (root / MANAGED_STATE).write_text(
            json.dumps({"directories": managed}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    print(json.dumps({"installed": managed, "target": str(root)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def _codex_skill_sync_script() -> str:
    return '''#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: sync_from_workbench.py <skill-pack-url> [target-skill-dir]", file=sys.stderr)
        return 2
    pack_url = sys.argv[1]
    target_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path.cwd()
    with urllib.request.urlopen(pack_url, timeout=45) as response:
        payload = json.load(response)
    files = payload.get("files") or {}
    if "SKILL.md" not in files or "references/skills.json" not in files:
        raise RuntimeError("Invalid Codex Skill pack: missing SKILL.md or references/skills.json")

    tmp_dir = Path(tempfile.mkdtemp(prefix="douyin-writing-skills-"))
    try:
        for relative_path, content in files.items():
            if relative_path.startswith("/") or ".." in Path(relative_path).parts:
                raise RuntimeError(f"Unsafe path in Skill pack: {relative_path}")
            destination = tmp_dir / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8")
        target_dir.mkdir(parents=True, exist_ok=True)
        for relative_path in files:
            source = tmp_dir / relative_path
            destination = target_dir / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    print(json.dumps({
        "skill_name": payload.get("skill_name"),
        "version": payload.get("version"),
        "target_dir": str(target_dir),
        "active_skill_count": payload.get("active_skill_count"),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def _codex_research_playbook() -> str:
    return """# Research Playbook

Read this file when a request involves current facts, disputed claims, public figures, company actions, platform memes, internet slang, comment-section sentiment, or any Skill whose `research_needs` materially affects writing.

## Research Brief Schema

Before matching Skills, build a compact brief with these fields:

- `input_type`: topic/hotspot, rough outline, source material, full draft, or local rewrite.
- `user_goal`: what the user wants the piece to achieve.
- `verified_facts`: claim, status, evidence, source type, URL or provided material.
- `timeline`: only the dates or sequence needed for writing.
- `platform_context`: platform, audience emotion, meme/slang usage, comment disputes, and what would sound outdated.
- `concrete_details`: names, scenes, quotes under fair-use limits, examples, sensory details, or cases that can make the writing specific.
- `risk_flags`: refuted claims, missing primary sources, privacy/legal/medical/financial risk, or conflict with a Skill boundary.
- `research_gap`: what could not be checked and what the user must provide.

## Evidence Tiers

- Tier A: original post/video, official account or statement, court/filing/database record, company page, paper, dataset, direct transcript, or user-provided source material.
- Tier B: reputable media, domain publication, indexed platform page, archived page, expert forum, or multiple independent reports that cite primary material.
- Tier C: reposts, screenshots without provenance, comment summaries, AI summaries, single anonymous claims, or search snippets.

Use Tier A whenever the script depends on a factual claim. For current or high-risk claims, require one Tier A source or two independent Tier B sources before writing the claim as fact. Use Tier C only as audience sentiment or a lead to better sources.

## Platform Search Strategy

- Start from the user's links, screenshots, pasted posts, video transcript, or source material.
- Search the exact claim, key names, and uncommon phrases first. Then search shorter Chinese and English variants.
- For Chinese internet context, look for original/official material first, then public traces from 微博、抖音、小红书、B站、知乎、微信公众号、主流媒体、垂直论坛 and search results.
- For foreign context, look for original posts and official sources first, then X, Reddit, YouTube, reputable media, papers, company blogs, GitHub, and domain forums.
- For closed or login-heavy platforms, never pretend access. Use indexed public traces when available, and ask the user for screenshots, links, comments, or transcripts when the platform cannot be checked.
- For memes and slang, research usage context: who uses it, emotional color, target situation, stale or risky uses, and whether the user's audience would recognize it.
- For comment-section emotion, collect 3-5 representative public signals. Do not generalize from one loud comment.

## Stop Gates

Do not write a full factual script yet when:

- The core premise is refuted or materially disputed.
- The request needs current verification but no tool/source is available and the user has not provided source material.
- The selected Skill's risk boundary conflicts with the request.
- The topic is high-stakes and evidence is only Tier C.
- The writing would require private information, invented motive, fabricated quotes, or unverified accusations.

In those cases, state what is blocked, show what was checked, and ask for the smallest missing source or suggest a safer angle.

## Candidate Skill Output

When showing candidates, use this order:

1. `研究简报`: 3-6 bullets with verified facts, platform context, concrete details, and gaps.
2. `候选 Skill`: 1-3 choices. For each: name, fits what content type, why it matches, how it would write this piece, and what evidence/detail it still needs.
3. `建议选择`: one recommended Skill with a plain reason, unless the user asked for no recommendation.
4. `需要你确认`: only the decisions or missing material that genuinely affect the output.

After the user chooses, read the selected reference file and map the research brief to that Skill's skeleton before writing.
"""


def build_codex_skill_pack(templates: list[TemplatePattern]) -> CodexSkillPackResponse:
    all_templates = deduplicate_templates(templates)
    active_templates = publishable_skill_templates(all_templates)
    manifest_skills: list[dict[str, object]] = []
    files: dict[str, str] = {}

    for template in active_templates:
        file_name = f"references/skills/{_skill_file_slug(template.name)}-{template.id[:8]}.md"
        manifest_skills.append(
            {
                "id": template.id,
                "name": template.name,
                "account_type": template.account_type,
                "quality_score": template.quality_score,
                "source_count": template.source_count,
                "created_at": _skill_added_at(template).isoformat(),
                "hotspot_types": template.hotspot_types,
                "solves_problems": template.solves_problems,
                "match_signals": template.match_signals,
                "applicable_scenes": template.applicable_scenes,
                "research_needs": _template_research_needs(template),
                "choose_when": _template_user_choice_summary(template),
                "writing_method": _template_writing_method(template),
                "risk_boundary": template.risk_boundary,
                "reference": file_name,
                "reference_file": file_name,
                "fingerprint": template.pattern_fingerprint,
            }
        )
        files[file_name] = _atomic_skill_markdown(template)

    version_seed = json.dumps(manifest_skills, ensure_ascii=False, sort_keys=True)
    version = hashlib.sha256(version_seed.encode("utf-8")).hexdigest()[:12]
    manifest_payload = {
        "name": "douyin-writing-skills",
        "version": version,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "sync_policy": "每次使用前读取最新版 references/skills.json；只使用正式且已启用的 Skill。",
        "sync_behavior": "工作台只能发布版本化 runtime；固定 Bootstrap Loader 和根目录 scripts 不会被工作台覆盖。",
        "research_rule": "先判断是否需要联网核验或平台语境补全；需要时先查证事实、时间线、热梗语境、评论区情绪和平台讨论，再进入 Skill 匹配。",
        "platform_source_rule": "中国互联网优先看原始链接、官方账号/声明、微博、抖音、小红书、B站、知乎、微信公众号、主流媒体和垂直社区；外网按主题看 X、Reddit、YouTube、官网、论文/新闻源。平台不可访问时说明限制并请求用户补链接、截图或原文。",
        "evidence_policy": "事实型输出优先使用原始/官方/直接来源；当前或高风险断言至少需要一个一手来源或两个独立可靠二手来源。无法达到时先说明缺口，不要写成既定事实。",
        "research_brief_schema": [
            "input_type",
            "user_goal",
            "verified_facts",
            "timeline",
            "platform_context",
            "concrete_details",
            "risk_flags",
            "research_gap",
        ],
        "selection_rule": "先识别用户想写的内容类型，再结合联网研究结论、创作目标、稿件缺口、可用事实素材、适用边界和 writing_method 做语义匹配，不按关键词硬套。",
        "interaction_rule": "除非用户明确要求自动选择，否则先给 1-3 个候选 Skill 让用户选择；每个候选都要解释大概怎么写。",
        "skills": manifest_skills,
    }
    install_manifest = {"runtime_contract": "SKILL.md + references/skills.json"}
    manifest_payload["install_manifest"] = install_manifest

    files["SKILL.md"] = """---
name: douyin-writing-skills
description: Team-maintained Douyin and short-video writing structure router. Use when Codex is asked to write, rewrite, plan, select, explain, reuse, or adapt 沉淀的抖音热点写作 Skill、短视频口播结构、运营账号写法、爆款视频结构、评论互动结构、人物/品牌/热点内容结构；especially when a user says what they want to write and needs Codex to identify the content type, recommend suitable Skills, let the user choose, then write with the selected Skill.
---

# Douyin Writing Skills Router

Use this skill as an interactive router for the latest team-maintained writing structures.

## Core Workflow

1. Read `references/skills.json` first.
2. Understand what the user wants to write. Classify the input as one of: only topic/hotspot, rough outline, source facts/material, complete draft, or local rewrite request.
3. Decide whether the request needs live research before matching. Research is required when the user mentions current news, recent hot topics, public figures, company actions, platform memes, internet slang, comment-section sentiment, uncertain facts, or asks for timely platform context.
4. When research is required, read `references/research-playbook.md`, then use available Codex browser/web/search tools before matching Skills. Do not rely on memory. Gather only enough evidence to support writing decisions.
5. Extract a compact research brief using the playbook schema: verified facts, timeline, original/official sources, platform sentiment, useful concrete details, risky or disputed claims, and what still needs user-provided material.
6. Match 1-3 active Skills by content type, writing goal, current draft gap, research brief, available facts, `research_needs`, `choose_when`, `writing_method`, and risk boundary. Do not match by topic keyword alone.
7. Unless the user explicitly asks Codex to auto-select, show the matched Skills and wait for the user to choose before writing.
8. For each candidate Skill, tell the user:
   - Skill name
   - What type of content it fits
   - Why it matches this request
   - Roughly how it will write this piece
   - What facts, platform signals, examples, cases, or details were found
   - What still needs to be provided or verified
9. After the user chooses a Skill, read only that Skill reference file under `references/skills/`.
10. Before writing, map the user's topic and research brief to the selected Skill's structure in 3-6 concise bullets.
11. Write using the selected Skill's structure, rhythm, judgment pattern, and constraints. Do not copy source wording.
12. If no Skill fits, say what missing Skill should be沉淀 instead of forcing a weak match.

## Research And Verification Rules

- A Skill does not grant tools by itself. Use the web, browser, search, connector, or platform tools available in the current Codex environment. If no suitable tool is available, say so and ask the user for links, screenshots, original posts, or source material.
- For current or high-stakes claims, search before writing. This includes deaths, arrests, official changes, company actions, lawsuits, product releases, policies, market data, public controversies, and platform hot topics.
- For Chinese internet context, prefer original posts and official accounts first, then indexed public material from 微博、抖音、小红书、B站、知乎、微信公众号、主流媒体、垂直论坛 and search results. For foreign context, prefer original posts and official sources, then X, Reddit, YouTube, reputable news, papers, or domain-specific communities.
- For memes, slang, and comment-section emotion, collect the usage context rather than a dictionary definition: who says it, what emotion it carries, what situations it fits, and what would sound outdated or wrong.
- Never claim you checked a closed platform if the tool cannot access it. State the access limit and either use public indexed traces or ask the user to provide the original link/content.
- Keep research proportional. Do not over-research evergreen structure tasks; do research when facts, recency, platform language, or audience sentiment will change the writing.
- Summarize research briefly before Skill selection when it materially affects which Skill should be used.
- Do not write a full factual script when the core premise is refuted, evidence is too weak for a high-risk claim, the selected Skill boundary conflicts with the request, or needed platform/source material is inaccessible and not provided.

## Writing Rules

- If the user only gives a topic, first identify what facts, platform context, examples, sensory details, or comment-section emotions are needed. Ask for missing critical facts or verify current public facts with available Codex tools before making factual claims.
- If the user gives an outline or draft, diagnose the weak part first, then explain why the selected Skill fixes it.
- If the user asks for a full稿件, produce naturally separated paragraphs and make the structure visible through flow, not through stiff labels.
- If the user asks only for结构, output a fillable structure with writing suggestions instead of a finished draft.
- If the selected Skill's risk boundary conflicts with the request, explain the conflict and recommend another Skill or a safer direction.
- Keep the final output specific to the user's topic. Avoid generic emotional升华 that could fit any topic.

## Freshness Rule

Treat `references/skills.json` as the source of truth. When a team workbench URL is available, run `scripts/sync_from_workbench.py <skill-pack-url> <this-skill-folder>` before reuse so the newest stable Skill list replaces older local references.
"""
    files["references/research-playbook.md"] = _codex_research_playbook()
    files["references/skills.json"] = json.dumps(
        manifest_payload, ensure_ascii=False, indent=2
    )
    return CodexSkillPackResponse(
        skill_name="douyin-writing-skills",
        version=version,
        generated_at=datetime.now(timezone.utc),
        active_skill_count=len(active_templates),
        total_skill_count=len(all_templates),
        source_count=sum(template.source_count for template in active_templates),
        sync_contract="/api/v1/script-workbench/codex-skill-pack",
        install_hint="工作台发布后，固定 Bootstrap Loader 会在下次调用时自动下载并校验最新 runtime。",
        install_manifest=install_manifest,
        files=files,
    )


def _run_publish_command(
    command: list[str], cwd: Optional[Path] = None, timeout: int = 60
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"{' '.join(command)} failed: {detail}")
    return result


def validate_codex_skill_pack_for_publish(
    skill_pack: CodexSkillPackResponse,
) -> None:
    if skill_pack.active_skill_count == 0:
        raise RuntimeError(
            "当前没有可发布的真实 Skill。请先从来源视频沉淀并确认 Skill，再发布到 GitHub。"
        )
    if skill_pack.source_count == 0:
        raise RuntimeError(
            "当前 Skill 包没有任何真实来源证据，疑似数据库未连接或已降级到种子数据；"
            "请先恢复持久化数据，再发布到 GitHub。"
        )


def _repo_readme(skill_pack: CodexSkillPackResponse) -> str:
    return f"""# Douyin Writing Skills

This repository contains the latest team-maintained Codex Skill package exported from the Douyin script workbench.

## How Codex Should Use It

1. Use `douyin-writing-router` only when choosing or comparing team methods.
2. Let the matching atomic Skill handle a direct writing request.
3. Identify what the user wants to write and classify the input type.
4. Decide whether the topic, outline, hotspot, meme, public claim, or platform context needs live research.
5. When needed, read `references/research-playbook.md`, then use available Codex web/browser/search tools to verify facts and collect platform sentiment before matching Skills.
6. Recommend 1-3 suitable active Skills with a short explanation of how each one would write the piece.
7. Let the user choose a Skill unless they explicitly ask Codex to auto-select.
8. Read only the selected reference file under `references/skills/`, then write or produce a fillable structure with that Skill.

## Research Boundary

The Skill package does not contain a separate crawler. It instructs Codex to use whatever web, browser, search, connector, or platform tools are available in the current environment. If a platform such as 抖音、小红书、微博、B站、知乎、X or Reddit is inaccessible, Codex should say so and ask for the original link, screenshot, or text instead of pretending it checked the platform.

For current or high-risk factual claims, Codex should treat original/official/direct sources as preferred evidence and should stop before writing if the claim is refuted, unsupported, or only backed by weak reposts/screenshots.

## Sync

Current package version: `{skill_pack.version}`

```bash
python3 scripts/install_atomic_skills.py <workbench-skill-pack-url> ~/.codex/skills
```

The workbench regenerates this package after Skill save, merge, stop, or review changes. A version change means the reusable writing structure has changed.
"""




# Publish into a user-configured checked-out distribution repository. The root
# loader is immutable and only the versioned runtime plus stable pointer may change.
SKILL_PUBLISH_LOCK = threading.Lock()


def _configured_skill_repository() -> tuple[Path, str, str, str, Literal["github", "local"]]:
    repo_value = os.getenv("DOUYIN_WRITING_SKILLS_REPO", "").strip()
    if not repo_value:
        raise RuntimeError("未配置 DOUYIN_WRITING_SKILLS_REPO，无法发布到 GitHub。")
    try:
        repository = Path(repo_value).expanduser().resolve(strict=True)
    except FileNotFoundError as exc:
        raise RuntimeError("DOUYIN_WRITING_SKILLS_REPO 不存在。") from exc
    if not repository.is_dir() or not (repository / ".git").exists():
        raise RuntimeError("DOUYIN_WRITING_SKILLS_REPO 必须指向本地 Skill Git 仓库。")
    remote = os.getenv("DOUYIN_WRITING_SKILLS_REMOTE", "origin").strip() or "origin"
    branch = os.getenv("DOUYIN_WRITING_SKILLS_BRANCH", "main").strip() or "main"
    sync_mode = os.getenv("DOUYIN_WRITING_SKILLS_SYNC_MODE", "github").strip().lower()
    if sync_mode not in {"github", "local"}:
        sync_mode = "github"
    expected_remote = os.getenv("DOUYIN_WRITING_SKILLS_REMOTE_URL", "").strip()
    if sync_mode == "github" and not expected_remote:
        raise RuntimeError("未配置 DOUYIN_WRITING_SKILLS_REMOTE_URL，无法确认发布目标。")
    if sync_mode == "github":
        actual_remote = _run_publish_command(
            ["git", "remote", "get-url", "--push", remote], cwd=repository
        ).stdout.strip().removesuffix("/")
        if actual_remote != expected_remote.removesuffix("/"):
            raise RuntimeError("Skill 仓库 remote 与受控发布目标不一致。")
    return repository, remote, branch, expected_remote, sync_mode  # type: ignore[return-value]


def _remote_web_url(remote_url: str) -> str:
    normalized = remote_url.strip().removesuffix(".git").rstrip("/")
    if normalized.startswith("git@github.com:"):
        return "https://github.com/" + normalized.split(":", 1)[1]
    if normalized.startswith("ssh://git@github.com/"):
        return "https://github.com/" + normalized.rsplit("github.com/", 1)[1]
    return normalized


def _remote_repository_label(remote_url: str) -> str:
    web_url = _remote_web_url(remote_url)
    if web_url.startswith("https://github.com/"):
        return web_url.removeprefix("https://github.com/")
    return web_url.rsplit("/", 1)[-1]


def _skill_repo_status(repository: Path) -> list[str]:
    return [
        line
        for line in _run_publish_command(
            ["git", "status", "--porcelain"], cwd=repository
        ).stdout.splitlines()
        if line.strip()
    ]


def _verify_published_runtime(repository: Path, remote_url: str) -> None:
    cache_dir = Path(tempfile.mkdtemp(prefix="douyin-skill-loader-cache-"))
    try:
        environment = {**os.environ, "DOUYIN_WRITING_CACHE_DIR": str(cache_dir)}
        if not remote_url.startswith("https://github.com/"):
            environment["DOUYIN_WRITING_MANIFEST_URL"] = (
                repository / "published" / "stable" / "manifest.json"
            ).as_uri()
        result = subprocess.run(
            [sys.executable, "-B", "scripts/load_latest.py"],
            cwd=repository,
            capture_output=True,
            text=True,
            timeout=60,
            env=environment,
        )
        if result.returncode != 0:
            raise RuntimeError("远程 stable runtime 验证失败。")
        payload = json.loads(result.stdout)
        if payload.get("status") != "ok" or not payload.get("runtime_skill_path"):
            raise RuntimeError("远程 stable runtime 验证未返回有效运行时路径。")
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        raise RuntimeError("远程 stable runtime 验证失败。") from exc
    finally:
        shutil.rmtree(cache_dir, ignore_errors=True)


def publish_codex_skill_pack_to_github(
    skill_pack: CodexSkillPackResponse,
    repository: Optional[str] = None,
) -> CodexSkillPublishResponse:
    """Build, validate, commit, push, and reload a runtime without touching the loader."""
    del repository  # The destination is controlled by server environment only.
    validate_codex_skill_pack_for_publish(skill_pack)
    verification = verify_local_settings()
    if not verification.publish_ready:
        raise RuntimeError("发布配置尚未完成：" + "；".join(verification.action_items))
    if not SKILL_PUBLISH_LOCK.acquire(blocking=False):
        raise RuntimeError("已有 Skill 发布任务正在运行，请等待其完成。")
    try:
        repo, remote, branch, remote_url, sync_mode = _configured_skill_repository()
        initial_status = _skill_repo_status(repo)
        if initial_status:
            raise RuntimeError(
                "Skill 仓库存在未提交修改，已阻止发布：" + "；".join(initial_status)
            )
        with tempfile.TemporaryDirectory(prefix="douyin-workbench-pack-") as tmp:
            pack_path = Path(tmp) / "skill-pack.json"
            pack_path.write_text(
                skill_pack.model_dump_json(), encoding="utf-8"
            )
            _run_publish_command(
                [
                    sys.executable,
                    "-B",
                    "scripts/sync_from_workbench.py",
                    pack_path.as_uri(),
                ],
                cwd=repo,
                timeout=90,
            )
        _run_publish_command(
            [sys.executable, "-B", "scripts/build_stable_manifest.py", "--check"], cwd=repo
        )
        _run_publish_command(
            [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-v"],
            cwd=repo,
            timeout=120,
        )
        changes = _skill_repo_status(repo)
        allowed_prefixes = (
            f"published/packages/{skill_pack.version}/",
            "published/stable/manifest.json",
        )
        changed_paths = [line[3:].split(" -> ")[-1] for line in changes]
        if any(not path.startswith(allowed_prefixes) for path in changed_paths):
            raise RuntimeError(
                "发布生成了受控路径外的文件，已阻止提交：" + "；".join(changes)
            )
        if not changes:
            current_sha = _run_publish_command(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
            _verify_published_runtime(repo, remote_url)
            return CodexSkillPublishResponse(
                status="unchanged",
                repository=_remote_repository_label(remote_url) if sync_mode == "github" else "本地 Skill 仓库",
                url=_remote_web_url(remote_url) if sync_mode == "github" else "",
                branch=branch,
                version=skill_pack.version,
                commit_sha=current_sha,
                message="当前 stable runtime 已是相同版本。",
                files_changed=0,
            )
        _run_publish_command(
            ["git", "add", "--", f"published/packages/{skill_pack.version}", "published/stable/manifest.json"],
            cwd=repo,
        )
        _run_publish_command(["git", "diff", "--cached", "--check"], cwd=repo)
        _run_publish_command(
            ["git", "commit", "-m", f"Publish Douyin writing runtime {skill_pack.version}"],
            cwd=repo,
        )
        commit_sha = _run_publish_command(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
        if sync_mode == "github":
            _run_publish_command(["git", "push", remote, f"HEAD:{branch}"], cwd=repo, timeout=120)
            _run_publish_command(["git", "fetch", remote], cwd=repo, timeout=60)
            remote_sha = _run_publish_command(
                ["git", "rev-parse", f"{remote}/{branch}"], cwd=repo
            ).stdout.strip()
            if commit_sha != remote_sha:
                raise RuntimeError("推送后远程 commit 与本地不一致。")
        _verify_published_runtime(repo, remote_url)
        return CodexSkillPublishResponse(
            status="published",
            repository=_remote_repository_label(remote_url) if sync_mode == "github" else "本地 Skill 仓库",
            url=_remote_web_url(remote_url) if sync_mode == "github" else "",
            branch=branch,
            version=skill_pack.version,
            commit_sha=commit_sha,
            message=(
                "已生成、校验并远程验证最新 stable runtime。"
                if sync_mode == "github"
                else "已生成并校验本地 stable runtime。"
            ),
            files_changed=len(changes),
        )
    finally:
        SKILL_PUBLISH_LOCK.release()


def optional_clean_text(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    value = clean_text(text)
    return value or None


def split_sentences(text: str) -> list[str]:
    parts = [
        part.strip() for part in re.split(r"[。！？!?；;]\s*", text) if part.strip()
    ]
    return parts or [clean_text(text)]


def pick_account_type(text: str) -> str:
    entertainment_terms = ["明星", "粉丝", "恋情", "分手", "塌房", "综艺", "演员", "剧"]
    business_terms = ["品牌", "代言", "商业", "公关", "平台", "流量", "营销"]
    if any(term in text for term in business_terms):
        return "商业分析号"
    if any(term in text for term in entertainment_terms):
        return "娱乐吃瓜号"
    return "泛娱乐观点号"


def pick_template(account_type: str) -> TemplatePattern:
    bootstrap_templates()
    for template in TEMPLATES:
        if template.account_type == account_type:
            return template
    if TEMPLATES:
        return TEMPLATES[0]
    return TemplatePattern(
        id="system-analysis-draft",
        name="通用分析草案",
        account_type=account_type,
        hotspot_types=["待沉淀素材"],
        applicable_scenes=["首次分析", "尚未保存写作 Skill 的素材"],
        unsuitable_scenes=[],
        skeleton=["明确问题", "补充事实", "组织观点", "收束互动"],
        hook_formula="先说清这段素材最值得讨论的判断。",
        emotion_rhythm="疑问 -> 信息增量 -> 判断",
        ending_formula="用一个基于公开信息的问题收束。",
        risk_boundary="仅根据用户提供或已核实的公开信息分析。",
        quality_score=0,
        usage_count=0,
        status="candidate",
    )


def pick_template_by_id(
    template_id: Optional[str], account_type: str
) -> TemplatePattern:
    bootstrap_templates()
    if template_id:
        for template in TEMPLATES:
            if template.id == template_id:
                return template
        raise KeyError(template_id)
    return pick_template(account_type)


def match_templates(account_type: str, hotspot: str) -> list[TemplatePattern]:
    bootstrap_templates()
    scored: list[tuple[int, TemplatePattern]] = []
    for template in TEMPLATES:
        if not skill_is_routable(template):
            continue
        if any(scene in hotspot for scene in template.unsuitable_scenes):
            continue
        score = 0
        if template.account_type == account_type:
            score += 4
        score += sum(1 for item in template.hotspot_types if item in hotspot)
        score += sum(1 for item in template.applicable_scenes if item in hotspot)
        score += template.quality_score // 20
        if (
            any(term in hotspot for term in ["明星", "粉丝", "综艺", "回应"])
            and "娱乐" in template.account_type
        ):
            score += 2
        if (
            any(term in hotspot for term in ["品牌", "商业", "营销", "平台"])
            and "商业" in template.account_type
        ):
            score += 2
        scored.append((score, template))
    return [
        template
        for _, template in sorted(
            scored,
            key=lambda item: (-item[0], -item[1].quality_score, -item[1].usage_count),
        )[:3]
    ]


def risk_check(text: str) -> RiskCheck:
    rules = [
        ("未经证实", "high", "疑似未经证实事实", "改成“网传信息仍需以官方回应为准”。"),
        (
            "内幕",
            "medium",
            "容易被理解为未证实爆料",
            "改成“从公开信息看，有几个细节值得讨论”。",
        ),
        ("私生活", "high", "涉及明星隐私边界", "只讨论公开回应和传播影响。"),
        ("未成年", "high", "涉及未成年人高敏内容", "删除相关细节，保留公共议题表达。"),
        ("滚", "medium", "攻击性表达", "改成克制的观点表达。"),
    ]
    items: list[RiskItem] = []
    for keyword, level, reason, rewrite in rules:
        if keyword in text:
            items.append(
                RiskItem(
                    label=keyword,
                    level=level,  # type: ignore[arg-type]
                    reason=reason,
                    rewrite=rewrite,
                )
            )
    if any(item.level == "high" for item in items):
        return RiskCheck(passed=False, level="high", items=items)
    if items:
        return RiskCheck(passed=False, level="medium", items=items)
    return RiskCheck(
        passed=True,
        level="low",
        items=[
            RiskItem(
                label="基础风控",
                level="low",
                reason="未发现明显谣言、隐私、人身攻击或高敏表达。",
                rewrite="保持当前表达，事实判断处保留“公开信息显示”等限定。",
            )
        ],
    )


def analyze_structure(source: SourceVideo, transcript: Transcript) -> ScriptAnalysis:
    from app.workbench_llm import analyze_transcript_structured

    output = analyze_transcript_structured(transcript).analysis
    account_type = pick_account_type(f"{source.title} {transcript.content_text}")
    return ScriptAnalysis(
        id=new_id("analysis"),
        source_video_id=source.id,
        hook=output.hook,
        conflict=output.conflict,
        structure=output.structure,
        emotion_curve=output.emotion_curve,
        reversal=output.reversal,
        ending_cta=output.ending_cta,
        account_type=account_type,
        reusable_template=output.reusable_template,
        template_suggestions=output.template_suggestions,
        content_angle=output.content_angle,
    )


def derive_skill_style_name(source: SourceVideo, analysis: ScriptAnalysis) -> str:
    """Create a short operator-facing style name instead of a long skeleton label."""
    text = " ".join(
        [
            source.title,
            analysis.reusable_template,
            analysis.content_angle,
            analysis.hook,
            analysis.conflict,
            " ".join(segment.name for segment in analysis.structure),
        ]
    )
    if any(word in text for word in ["成长", "逆袭", "回归", "来时路", "成名"]):
        return "人物成长线型"
    if any(word in text for word in ["品牌", "商业", "宣传", "奢侈品"]) and any(
        word in text for word in ["价值", "行动", "责任", "格局"]
    ):
        return "品牌价值升维型"
    if any(word in text for word in ["冲突", "反差", "反转", "赢了", "输了"]):
        return "冲突反转升维型"
    if any(word in text for word in ["背景", "时间线", "幕后", "来龙去脉"]):
        return "背景层层拆解型"
    if any(word in text for word in ["共鸣", "情绪", "痛点", "代入"]):
        return "情绪共鸣推进型"
    if any(word in text for word in ["评论", "互动", "讨论", "争议"]):
        return "评论争议引导型"
    return "观点升维型"


def build_preset_draft_from_analysis(
    source: SourceVideo,
    transcript: Transcript,
    analysis: ScriptAnalysis,
    existing_skills: Optional[list[TemplatePattern]] = None,
) -> PresetDraft:
    from app.workbench_llm import extract_skill_draft_structured

    style_name = derive_skill_style_name(source, analysis)
    solves, scenes, signals, labels = infer_skill_capabilities(
        style_name,
        [segment.name for segment in analysis.structure],
        "先抛出反差或疑问，再给出一个细节入口。",
        "好奇 -> 共鸣 -> 信息增量 -> 观点判断 -> 评论互动",
    )
    model_draft = extract_skill_draft_structured(source.title, transcript, analysis)
    skeleton = clean_items(
        model_draft.skeleton
        if model_draft
        else [segment.name for segment in analysis.structure]
    )
    hook_formula = (
        clean_text(model_draft.hook_formula)
        if model_draft
        else "先抛出反差或疑问，再给出一个细节入口。"
    )
    emotion_rhythm = (
        clean_text(model_draft.emotion_rhythm)
        if model_draft
        else "好奇 -> 共鸣 -> 信息增量 -> 观点判断 -> 评论互动"
    )
    ending_formula = (
        clean_text(model_draft.ending_formula) if model_draft else analysis.ending_cta
    )
    fingerprint = skill_pattern_fingerprint(
        skeleton, hook_formula, emotion_rhythm, ending_formula
    )
    draft = PresetDraft(
        id=new_id("draft"),
        source_analysis_id=analysis.id,
        source_video_id=source.id,
        source_title=source.title,
        source_author=source.author,
        source_url=source.url,
        source_transcript=transcript.content_text,
        source_recognized_at=source.created_at,
        name=clean_text(model_draft.name) if model_draft else style_name,
        account_type=analysis.account_type,
        hotspot_types=clean_items(model_draft.writing_tasks if model_draft else labels),
        solves_problems=clean_items(
            model_draft.solves_problems if model_draft else solves
        ),
        match_signals=clean_items(
            model_draft.match_signals if model_draft else signals
        ),
        applicable_scenes=structural_applicable_scenes(
            model_draft.applicable_scenes if model_draft else scenes,
            skeleton,
            hook_formula,
            emotion_rhythm,
        ),
        unsuitable_scenes=clean_items(
            model_draft.unsuitable_scenes
            if model_draft
            else [
                "核心事实尚未确认的爆料稿",
                "依赖隐私细节或人身攻击才能成立的稿件",
                "只有结论、没有可验证素材的稿件",
            ]
        ),
        skeleton=skeleton,
        hook_formula=hook_formula,
        emotion_rhythm=emotion_rhythm,
        ending_formula=ending_formula,
        risk_boundary=(
            clean_text(model_draft.risk_boundary)
            if model_draft
            else "只学习结构，不复制原句；只基于公开信息生成。"
        ),
        borrowable_moves=clean_items(
            model_draft.borrowable_moves
            if model_draft
            else [
                "用微小细节承接宏大命题，让用户先从具体画面进入判断。",
                "先压低认知预期，再用关键细节完成反差翻转。",
                "把公共事实转成普通人能感知的情绪入口，再推进到结构判断。",
                "结尾保留一个可回答的问题，让用户沿着结构继续表达态度。",
                *analysis.template_suggestions,
            ]
        ),
        pattern_fingerprint=fingerprint,
        created_at=now_utc(),
    )
    bootstrap_templates()
    skill_pool = (
        deduplicate_templates(existing_skills)
        if existing_skills is not None
        else deduplicate_templates(TEMPLATES)
    )
    similar = max(
        skill_pool,
        key=lambda item: skill_structure_similarity(item, draft),
        default=None,
    )
    if similar is not None:
        similarity = skill_structure_similarity(similar, draft)
        if similarity >= 82:
            draft = draft.model_copy(
                update={
                    "similar_skill_id": similar.id,
                    "similar_skill_name": similar.name,
                    "similarity_score": similarity,
                }
            )
    return draft


def create_writing_preset_from_draft(
    payload: WritingPresetCreateRequest,
    existing_skills: Optional[list[TemplatePattern]] = None,
) -> TemplatePattern:
    draft = payload.preset_draft
    source_record = SkillSourceRecord(
        source_video_id=draft.source_video_id,
        source_analysis_id=draft.source_analysis_id,
        title=draft.source_title,
        author=draft.source_author,
        url=draft.source_url,
        transcript=draft.source_transcript,
        recognized_at=draft.source_recognized_at or now_utc(),
    )
    source_evidence = SkillEvidence(
        id=new_id("evidence"),
        claim=f"《{draft.source_title}》提供了可复用的写作结构样本。",
        source_title=draft.source_title,
        source_url=draft.source_url or f"local://source/{draft.source_video_id}",
        source_type="authorized_source",
        evidence_tier="A",
        quote=clean_text(draft.source_transcript)[:600],
        scope="structure",
        checked_at=draft.source_recognized_at or now_utc(),
    )
    bootstrap_templates()
    skill_pool = (
        deduplicate_templates(existing_skills)
        if existing_skills is not None
        else deduplicate_templates(TEMPLATES)
    )
    similar = next(
        (item for item in skill_pool if item.id == payload.merge_target_id), None
    )
    if payload.merge_target_id and similar is None:
        raise ValueError("选择的归属 Skill 已不存在，请重新选择。")
    if similar is None and not payload.merge_as_new:
        similar = next(
            (item for item in skill_pool if item.id == draft.similar_skill_id), None
        )
    if similar is None and not payload.merge_as_new:
        similar = max(
            skill_pool,
            key=lambda item: skill_structure_similarity(item, draft),
            default=None,
        )
        if similar is not None and skill_structure_similarity(similar, draft) < 82:
            similar = None
    if similar is not None:
        source_titles = clean_items([*similar.source_titles, draft.source_title])
        sources = merge_skill_sources(similar.sources, [source_record])
        # Older candidates may only retain an aggregate count or titles.  Count an
        # explicitly added source once even when that historical source record is
        # unavailable, otherwise those candidates can never progress past 1/3.
        source_already_recorded = any(
            source.source_video_id == source_record.source_video_id
            or (
                bool(source_record.url)
                and source.url == source_record.url
            )
            for source in similar.sources
        ) or draft.source_title in similar.source_titles
        known_source_count = max(
            similar.source_count,
            len(similar.sources),
            len(similar.source_titles),
        )
        source_count = known_source_count + (0 if source_already_recorded else 1)
        evidence = [
            *similar.evidence,
            *(
                []
                if any(
                    item.source_url == source_evidence.source_url
                    and item.scope == source_evidence.scope
                    for item in similar.evidence
                )
                else [source_evidence]
            ),
        ]
        merged = enrich_skill_template(
            similar.model_copy(
                update={
                    "solves_problems": clean_items(
                        [*similar.solves_problems, *draft.solves_problems]
                    )[:8],
                    "match_signals": clean_items(
                        [*similar.match_signals, *draft.match_signals]
                    )[:14],
                    "hotspot_types": clean_items(
                        [*similar.hotspot_types, *draft.hotspot_types]
                    )[:10],
                    "applicable_scenes": structural_applicable_scenes(
                        [
                            *similar.applicable_scenes,
                            *(payload.applicable_scenes or draft.applicable_scenes),
                        ],
                        draft.skeleton,
                        draft.hook_formula,
                        draft.emotion_rhythm,
                    )[:12],
                    "unsuitable_scenes": clean_items(
                        [
                            *similar.unsuitable_scenes,
                            *(payload.unsuitable_scenes or draft.unsuitable_scenes),
                        ]
                    )[:10],
                    "source_titles": source_titles,
                    "sources": sources,
                    "source_count": source_count,
                    "evidence": evidence,
                    "quality_score": max(similar.quality_score, payload.quality_score),
                    "last_review_note": (
                        f"已合并 {source_count} 个同结构来源；"
                        f"最近补充《{draft.source_title}》。"
                    ),
                }
            )
        )
        for index, item in enumerate(TEMPLATES):
            if item.id == similar.id:
                TEMPLATES[index] = merged
                break
        else:
            TEMPLATES.insert(0, merged)
        return merged

    template = TemplatePattern(
        id=new_id("tpl"),
        name=clean_text(payload.name or draft.name) or draft.name,
        account_type=draft.account_type,
        hotspot_types=clean_items(draft.hotspot_types),
        solves_problems=clean_items(draft.solves_problems),
        match_signals=clean_items(draft.match_signals),
        applicable_scenes=structural_applicable_scenes(
            payload.applicable_scenes or draft.applicable_scenes,
            draft.skeleton,
            draft.hook_formula,
            draft.emotion_rhythm,
        ),
        unsuitable_scenes=clean_items(
            payload.unsuitable_scenes or draft.unsuitable_scenes
        ),
        skeleton=clean_items(draft.skeleton),
        hook_formula=clean_text(draft.hook_formula),
        emotion_rhythm=clean_text(draft.emotion_rhythm),
        ending_formula=clean_text(draft.ending_formula),
        risk_boundary=clean_text(draft.risk_boundary),
        quality_score=payload.quality_score,
        usage_count=0,
        disabled_reason=None,
        last_review_note=optional_clean_text(payload.last_review_note)
        or f"从《{draft.source_title}》拆解确认后保存为使用预设。",
        source_analysis_id=draft.source_analysis_id,
        source_titles=[draft.source_title],
        sources=[source_record],
        source_count=1,
        evidence=[source_evidence],
        pattern_fingerprint=draft.pattern_fingerprint
        or skill_pattern_fingerprint(
            draft.skeleton,
            draft.hook_formula,
            draft.emotion_rhythm,
            draft.ending_formula,
        ),
    )
    template = enrich_skill_template(template)
    TEMPLATES.insert(0, template)
    return template


def build_script(
    hotspot: str,
    account_type: str,
    duration_seconds: int,
    tone: str,
    goal: str,
    template: Optional[TemplatePattern] = None,
    variant: int = 1,
) -> GeneratedScript:
    template = template or pick_template(account_type)
    angles = ["细节反差", "情绪共鸣", "传播逻辑", "利益关系", "风险提醒"]
    angle = angles[(variant - 1) % len(angles)]
    title = f"{hotspot}：从{angle}看，真正值得讨论的不是热闹"
    skeleton = " -> ".join(template.skeleton)
    spoken = (
        f"{template.hook_formula}\n"
        f"这次「{hotspot}」可以先从{angle}切入。\n\n"
        f"第一，先按「{skeleton}」这条结构走，不急着下结论。\n"
        "第二，只用公开信息搭时间线，把评论区真正争论的点讲清楚。\n"
        "第三，把事件从表层热闹升到人群情绪、传播逻辑或关系判断。\n\n"
        f"所以这条内容的态度可以是：{tone}。\n"
        f"最后把问题抛给用户：{goal}。你觉得这件事最该讨论的是事实，还是态度？"
    )
    check = risk_check(spoken + hotspot)
    return GeneratedScript(
        id=new_id("script"),
        title=title,
        account_type=account_type,
        content_angle=angle,
        duration_seconds=duration_seconds,
        spoken_script=spoken,
        shot_suggestions=[
            "0-3 秒：大字标题 + 热点关键词，不放未经证实细节。",
            "3-15 秒：按时间线展示公开信息，字幕突出冲突词。",
            "15-35 秒：切到观点段，用 2-3 个短句推进节奏。",
            "结尾：保留问题，引导评论区表达态度。",
        ],
        subtitle_rhythm=[
            "每屏 12-18 字，核心冲突词单独成行。",
            "反转句前留 0.3 秒停顿。",
            "结尾问题使用高对比字幕，但不使用攻击性词汇。",
        ],
        comment_cta="你觉得这件事最该讨论的是事实，还是态度？评论区聊聊。",
        risk_check=check,
        template_used=template.name,
        preset_application=preset_application_summary(template),
    )


def preset_application_summary(template: TemplatePattern) -> list[str]:
    return [
        f"开头：沿用「{template.hook_formula}」的抓人方式。",
        f"推进：按「{' -> '.join(template.skeleton)}」组织信息和冲突。",
        f"情绪：保持「{template.emotion_rhythm}」的节奏。",
        f"结尾：使用「{template.ending_formula}」的互动方式。",
    ]


def skill_problem_statement(template: TemplatePattern) -> str:
    if template.solves_problems:
        return "；".join(template.solves_problems[:2]) + "。"
    skeleton_text = " ".join(template.skeleton)
    if any(word in skeleton_text for word in ["开头", "爆点", "钩子", "反问"]):
        return "解决开头不抓人、切入角度太平的问题。"
    if any(word in skeleton_text for word in ["时间线", "信息", "分步", "背景"]):
        return "解决信息散、推进顺序不清的问题。"
    if any(word in skeleton_text for word in ["情绪", "对照", "共鸣", "痛点"]):
        return "解决情绪起伏弱、用户代入感不足的问题。"
    return "解决结构松散、结尾缺少互动的问题。"


def skill_apply_plan(template: TemplatePattern) -> list[str]:
    return [
        f"先用 Skill 的开头方式重写前 3 秒：{template.hook_formula}",
        f"把原稿内容压进结构骨架：{' -> '.join(template.skeleton)}",
        f"按情绪节奏补足转折：{template.emotion_rhythm}",
        f"结尾用互动方式收束：{template.ending_formula}",
    ]


def diagnose_draft(payload: DraftInputRequest) -> DraftDiagnosis:
    text = clean_text(payload.content)
    sentences = split_sentences(text)
    strengths: list[str] = []
    problems: list[str] = []
    rewrite_goals: list[str] = []
    if len(text) >= 80:
        strengths.append("已有可分析素材，不是从空白开始。")
    if any(word in text for word in ["但是", "不是", "真正", "反而", "问题"]):
        strengths.append("已经有冲突或反差表达，可以放大成开头钩子。")
    if len(sentences) < 3 or payload.input_type in {"hotspot", "outline"}:
        problems.append("目前更像热点或大纲，缺少可直接拍摄的口播段落。")
        rewrite_goals.append("补齐开头、信息推进、观点升维和结尾互动。")
    if not any(word in text for word in ["评论", "你觉得", "怎么看", "聊聊"]):
        problems.append("结尾互动不足，用户看完后缺少评论入口。")
        rewrite_goals.append("补一个能让评论区接话的问题。")
    if not any(word in text for word in ["先", "第一", "第二", "最后", "然后"]):
        problems.append("信息推进顺序不够清楚，容易写成散点。")
        rewrite_goals.append("把内容拆成 3-5 个可拍摄段落。")
    if not strengths:
        strengths.append("主题已经明确，可以围绕核心事件重构。")
    if not problems:
        problems.append("稿子已有基础，但还可以增强开头冲击和拍摄节奏。")
    return DraftDiagnosis(
        id=new_id("diag"),
        draft_title=clean_text(payload.title) or "未命名稿件",
        draft_type=payload.input_type,
        strengths=strengths[:4],
        problems=problems[:4],
        rewrite_goals=rewrite_goals[:4]
        or ["增强开头抓力", "梳理信息推进", "补足结尾互动"],
        suggested_skill_types=["反差开头", "结构补全", "情绪推进", "评论引导"],
        no_go_zones=["未经证实的事实断言", "隐私细节", "人身攻击", "恶意引战"],
    )


def match_writing_skills(
    payload: DraftInputRequest,
    skill_ids: Optional[list[str]] = None,
    skills: Optional[list[TemplatePattern]] = None,
    activity_callback: Optional[Callable[[dict[str, str]], None]] = None,
    use_model: bool = True,
) -> list[SkillMatch]:
    bootstrap_templates()
    text = f"{payload.title} {payload.content}"
    selected_ids = set(skill_ids or [])
    skill_pool = skills if skills is not None else TEMPLATES
    candidates = deduplicate_templates(
        [
            template
            for template in skill_pool
            if skill_is_routable(template)
            and (not selected_ids or template.id in selected_ids)
        ]
    )
    if not candidates:
        available = deduplicate_templates(
            [template for template in skill_pool if skill_is_routable(template)]
        )
        candidates = available[:3]
    if not candidates:
        return []

    from app.workbench_llm import rank_writing_skills_structured

    model_matches = None
    if use_model:
        model_matches = (
            rank_writing_skills_structured(
                payload, candidates, activity_callback=activity_callback
            )
            if activity_callback is not None
            else rank_writing_skills_structured(payload, candidates)
        )
    if model_matches:
        return model_matches

    scored: list[tuple[int, TemplatePattern]] = []
    diagnosis_terms = {
        "反差": ["但是", "却", "没想到", "相反", "不是", "变化", "反转"],
        "背景": ["为什么", "原因", "来龙去脉", "此前", "后来", "过程"],
        "情绪": ["感受", "共鸣", "遗憾", "期待", "愤怒", "感动"],
        "观点": ["说明", "意味着", "真正", "值得", "本质", "背后"],
        "互动": ["你觉得", "怎么看", "评论", "讨论"],
    }
    for template in candidates:
        score = 42
        searchable = " ".join(
            [
                template.name,
                template.account_type,
                " ".join(template.hotspot_types),
                " ".join(template.solves_problems),
                " ".join(template.match_signals),
                " ".join(template.applicable_scenes or []),
                template.hook_formula,
                template.emotion_rhythm,
            ]
        )
        for keyword in [
            "明星",
            "品牌",
            "作品",
            "消费",
            "职场",
            "争议",
            "回应",
            "成长",
            "评论",
            "情绪",
        ]:
            if keyword in text and keyword in searchable:
                score += 5
        for capability, draft_markers in diagnosis_terms.items():
            if capability in searchable and any(
                marker in text for marker in draft_markers
            ):
                score += 9
        if len(payload.content) < 80 and any(
            word in searchable for word in ["补齐", "完整结构", "信息散"]
        ):
            score += 10
        if (
            not any(marker in text for marker in diagnosis_terms["互动"])
            and "结尾" in searchable
        ):
            score += 7
        if template.account_type == payload.account_type:
            score += 4
        if selected_ids and template.id in selected_ids:
            score += 28
        score += template.quality_score // 12
        scored.append((min(score, 96), template))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        SkillMatch(
            skill=template,
            match_score=score,
            reason=(
                f"当前输入是{payload.input_type}，系统按写作缺口而不是关键词匹配；"
                f"这个 Skill 可用于{'、'.join(template.solves_problems[:2])}。"
            ),
            apply_plan=skill_apply_plan(template),
        )
        for score, template in scored[:3]
    ]


def build_rewrite_script(
    payload: DraftInputRequest,
    diagnosis: DraftDiagnosis,
    match: SkillMatch,
    variant: int,
) -> GeneratedScript:
    angle_options = [
        "结构补全版",
        "情绪推进版",
        "观点升维版",
        "拍摄友好版",
        "评论引导版",
    ]
    angle = angle_options[(variant - 1) % len(angle_options)]
    skill = match.skill
    skeleton = " -> ".join(skill.skeleton)
    problem_line = "；".join(diagnosis.problems[:2])
    goal_line = "；".join(diagnosis.rewrite_goals[:2]) or "补齐可拍摄段落和评论入口"
    spoken = (
        "【写作结构工作稿】\n"
        "这不是 AI 成稿。请按下面结构逐段填写，写完后再提交复核和导出。\n\n"
        f"【中心判断】\n写作建议：围绕「{payload.title}」先确定一个可争辩判断；当前要解决：{problem_line or goal_line}。\n"
        "你来填写：\n\n\n"
        f"【采用 Skill】{skill.name}\n结构骨架：{skeleton}\n\n"
        "【段落 1：开头钩子】\n"
        f"写作建议：参考「{skill.hook_formula}」，不要铺太多前情，先给观众停下来的理由。\n"
        "你来填写：\n\n\n"
        "【段落 2：事实或素材支撑】\n"
        "写作建议：只放公开、确定、能拍出来的信息；每个事实后补一句它为什么重要。\n"
        "你来填写：\n\n\n"
        "【段落 3：结构推进】\n"
        f"写作建议：按「{skeleton}」顺序推进，不混用多个写法。\n"
        "你来填写：\n\n\n"
        "【段落 4：情绪和观点】\n"
        f"写作建议：保持「{skill.emotion_rhythm}」，把事件落到观众能代入的处境、选择或判断。\n"
        "你来填写：\n\n\n"
        "【段落 5：结尾互动】\n"
        f"写作建议：参考「{skill.ending_formula}」，最后抛出和「{payload.goal}」一致的问题。\n"
        "你来填写："
    )
    return GeneratedScript(
        id=new_id("script"),
        title=f"{payload.title}｜{angle}",
        account_type=payload.account_type,
        content_angle=angle,
        duration_seconds=payload.duration_seconds,
        spoken_script=spoken,
        shot_suggestions=[
            "开头段：先写停留理由，再决定大字标题。",
            "素材段：列出 1-2 个可核实事实或画面点。",
            "观点段：每个判断后补一个具体依据。",
            "结尾段：只留一个用户能回答的问题。",
        ],
        subtitle_rhythm=[
            "填写完成后再按 12-18 字一屏拆字幕。",
            "结构稿里的【写作建议】不要导出成口播。",
            "结尾问题单独一屏，避免攻击性措辞。",
        ],
        comment_cta="你觉得这件事真正值得讨论的是热闹，还是背后的动作？",
        risk_check=risk_check(f"{payload.title} {payload.content} {spoken}"),
        template_used=skill.name,
        preset_application=[
            f"原稿问题：{problem_line}",
            f"套用 Skill：{skill.name}",
            f"结构方向：{match.reason}",
            *skill_apply_plan(skill),
        ],
    )


def rewrite_draft(
    payload: DraftRewriteRequest,
    skills: Optional[list[TemplatePattern]] = None,
    progress_callback: Optional[Callable[[str, str, int], None]] = None,
    activity_callback: Optional[Callable[[dict[str, str]], None]] = None,
) -> DraftRewriteResponse:
    def report(stage: str, detail: str, progress: int) -> None:
        if progress_callback is not None:
            progress_callback(stage, detail, progress)

    def activity(
        phase: str,
        kind: str,
        title: str,
        detail: str = "",
        status: str = "completed",
    ) -> None:
        if activity_callback is not None:
            activity_callback(
                {
                    "phase": phase,
                    "kind": kind,
                    "title": title,
                    "detail": detail,
                    "status": status,
                }
            )

    report("diagnosing", "正在理解输入意图和稿件缺口", 8)
    activity(
        "diagnosis",
        "status",
        "正在理解写作任务",
        f"输入类型：{payload.input_type} · 目标 {payload.duration_seconds} 秒",
        "active",
    )
    diagnosis = diagnose_draft(payload)
    activity(
        "diagnosis",
        "check",
        "写作缺口已确认",
        diagnosis.problems[0] if diagnosis.problems else "已确认当前稿件的主要改写目标。",
    )
    from app.workbench_llm import (
        select_skill_and_generate_recommended_draft_structured,
        verify_major_claim_structured,
    )

    report("fact_checking", "Codex 正在核验重大事实并整理创作证据", 18)
    activity(
        "research",
        "search",
        "开始联网核验",
        "先确认核心事件，再整理能支撑人物处境与选择的创作证据。",
        "active",
    )
    fact_verification = (
        verify_major_claim_structured(payload, activity_callback=activity_callback)
        if activity_callback is not None
        else verify_major_claim_structured(payload)
    )
    if fact_verification.required and fact_verification.verdict != "verified":
        verdict_notes = {
            "refuted": "公开来源与输入说法不符，已停止生成，避免错误事实进入脚本。",
            "uncertain": "公开来源不足或相互冲突，已停止生成并保留核验结果。",
            "failed": fact_verification.summary
            or "Codex 联网核验未完成，已停止生成；请重新核验。",
        }
        report("quality_checking", "事实门禁未通过，正在整理核验结果", 92)
        activity(
            "quality",
            "check",
            "事实门禁未通过",
                fact_verification.summary or "公开来源不足，未进入结构生成。",
            "failed",
        )
        return DraftRewriteResponse(
            diagnosis=diagnosis,
            matched_skills=[],
            rewrite_plan=["先完成重大事实核验，再进入 Skill 匹配和结构生成。"],
            scripts=[],
            generation_mode="blocked",
            generation_model=None,
            generation_note=verdict_notes.get(
                fact_verification.verdict,
                "重大事实核验未通过，已停止生成。",
            ),
            fact_verification=fact_verification,
        )

    selected_ids = set(payload.skill_ids)
    skill_pool = skills if skills is not None else TEMPLATES
    candidates = deduplicate_templates(
        [
            template
            for template in skill_pool
            if skill_is_routable(template)
            and (not selected_ids or template.id in selected_ids)
        ]
    )
    if not candidates:
        candidates = deduplicate_templates(
            [template for template in skill_pool if skill_is_routable(template)]
        )[:3]
    if not candidates:
        return DraftRewriteResponse(
            diagnosis=diagnosis,
            matched_skills=[],
            rewrite_plan=["当前没有已批准的正式 Skill；请先在 Skill 库完成候选评测与主审批准。"],
            scripts=[],
            generation_mode="blocked",
            generation_note="当前仅有候选或暂停中的 Skill，未进行自动套用。",
            fact_verification=fact_verification,
        )

    available_names = "、".join(item.name for item in candidates)
    activity(
        "skill_match",
        "skill",
        "已载入候选 Writing Skill",
        available_names[:220] or "已读取可用 Skill 的结构能力与适用边界。",
    )
    report(
        "generating_scripts",
        "Codex 正在选择 Skill 并生成可填写文本结构",
        58,
    )
    matches, model_scripts, model_status = (
        select_skill_and_generate_recommended_draft_structured(
            payload,
            diagnosis,
            candidates,
            fact_verification,
            activity_callback=activity_callback,
        )
        if activity_callback is not None
        else select_skill_and_generate_recommended_draft_structured(
            payload,
            diagnosis,
            candidates,
            fact_verification,
        )
    )

    if not matches:
        matches = match_writing_skills(
            payload,
            payload.skill_ids,
            skills,
            use_model=False,
        )
    report("quality_checking", "正在检查事实边界、Skill 覆盖和内容体量", 90)
    activity(
        "quality",
        "check",
        "正在执行结构检查",
        "检查字数、事实边界和 Skill 骨架覆盖。",
        "active",
    )
    if model_scripts:
        scripts = model_scripts
        generation_mode: Literal["ai", "fallback", "blocked"] = "ai"
        verification_note = (
            f"，并引用 {len(fact_verification.sources)} 个公开来源完成事实核验"
            if fact_verification.verdict == "verified"
            else ""
        )
        generation_note = (
            f"Codex 已按「{matches[0].skill.name}」生成一份可填写文本结构"
            f"{verification_note}；请先填正文，再进入人工复核。"
        )
        ready_count = sum(
            1
            for script in scripts
            if round(payload.duration_seconds * 3.5)
            <= len(re.sub(r"\s+", "", script.spoken_script))
            <= round(payload.duration_seconds * 6.5)
        )
        activity(
            "quality",
            "check",
            "结构检查已完成",
            f"文本结构已覆盖 Skill 骨架；目标时长仅作填写参考，完成正文后再检查口播体量。",
        )
    elif (model_status.error or "").startswith("FACT_GUARD:"):
        scripts = []
        generation_mode = "blocked"
        generation_note = "重大事实缺少可靠来源，Codex 已停止生成，避免把传言写成事实。请补充权威来源后重试。"
    else:
        scripts = [
            build_rewrite_script(
                payload, diagnosis, matches[min(index - 1, len(matches) - 1)], index
            )
            for index in range(1, 2)
        ]
        generation_mode = "fallback"
        generation_note = (
            "AI 本次未返回可用结构，当前展示本地结构工作稿。可直接填写，也可重试。"
            if model_status.mode != "offline"
            else "AI 当前未启用，展示本地结构工作稿。"
        )
    GENERATED[:0] = scripts
    return DraftRewriteResponse(
        diagnosis=diagnosis,
        matched_skills=matches,
        rewrite_plan=[
            "先诊断原稿缺口，再选择 1-3 个最匹配的写作 Skill。",
            "按 Skill 的结构骨架重排内容，不复制来源视频原句。",
            "先生成一份可填写文本结构，用户补完正文后再局部改写和人工复核。",
        ],
        scripts=scripts,
        generation_mode=generation_mode,
        generation_model=model_status.model if model_status.used_model else None,
        generation_note=generation_note,
        fact_verification=fact_verification,
    )


def _update_draft_rewrite_task(task_id: str, **updates: object) -> DraftRewriteTask:
    with DRAFT_REWRITE_LOCK:
        current = DRAFT_REWRITE_TASKS[task_id]
        task = current.model_copy(
            update={**updates, "updated_at": datetime.now(timezone.utc)}
        )
        DRAFT_REWRITE_TASKS[task_id] = task
        return task


def _append_draft_rewrite_activity(
    task_id: str, activity: dict[str, str]
) -> DraftRewriteTask:
    with DRAFT_REWRITE_LOCK:
        current = DRAFT_REWRITE_TASKS[task_id]
        next_activity = DraftRewriteActivity(
            id=new_id("activity"),
            phase=activity.get("phase", "writing"),  # type: ignore[arg-type]
            kind=activity.get("kind", "status"),  # type: ignore[arg-type]
            title=clean_text(activity.get("title", "Codex 正在工作"))[:120],
            detail=clean_text(activity.get("detail", ""))[:360],
            status=activity.get("status", "completed"),  # type: ignore[arg-type]
            created_at=datetime.now(timezone.utc),
        )
        is_wait_update = next_activity.title in {
            "等待联网核验返回",
            "等待 Skill 匹配与结构返回",
            "等待 Codex 返回文本结构",
            "等待质量检查完成",
            "等待 Codex 返回当前任务",
            "等待 Codex 完成核验与结构设计",
        }
        activities = list(current.activities)
        if is_wait_update and activities and activities[-1].title == next_activity.title:
            activities[-1] = next_activity
        else:
            activities.append(next_activity)
        activities = activities[-60:]
        task = current.model_copy(
            update={"activities": activities, "updated_at": datetime.now(timezone.utc)}
        )
        DRAFT_REWRITE_TASKS[task_id] = task
        return task


def draft_rewrite_timeout_seconds() -> int:
    llm_timeout = float(os.getenv("WORKBENCH_LLM_TIMEOUT_SECONDS", "60"))
    web_call_timeout = max(90.0, llm_timeout + 30.0)
    writing_call_timeout = max(120.0, llm_timeout + 60.0)
    # One focused verification call, then one recommended-draft call.
    # This budget only prevents the polling UI from giving up first.
    return min(
        3600,
        max(60, round(web_call_timeout + writing_call_timeout + 30)),
    )


def _run_draft_rewrite_task(
    task_id: str,
    payload: DraftRewriteRequest,
    skills: list[TemplatePattern],
    on_complete: Optional[Callable[[DraftRewriteResponse], None]] = None,
) -> None:
    _update_draft_rewrite_task(
        task_id,
        status="processing",
        stage="diagnosing",
        stage_detail="正在理解输入意图和稿件缺口",
        progress=5,
    )

    def report(stage: str, detail: str, progress: int) -> None:
        _update_draft_rewrite_task(
            task_id,
            status="processing",
            stage=stage,
            stage_detail=detail,
            progress=progress,
        )

    def activity(event: dict[str, str]) -> None:
        task = _append_draft_rewrite_activity(task_id, event)
        phase_ceiling = {
            "diagnosis": 16,
            "research": 44,
            "skill_match": 64,
            "writing": 88,
            "quality": 98,
        }.get(event.get("phase", "writing"), 88)
        if task.progress < phase_ceiling:
            _update_draft_rewrite_task(
                task_id,
                progress=min(phase_ceiling, task.progress + 1),
            )

    try:
        response = rewrite_draft(
            payload,
            skills,
            progress_callback=report,
            activity_callback=activity,
        )
        if on_complete is not None:
            on_complete(response)
        _update_draft_rewrite_task(
            task_id,
            status="completed",
            stage="completed",
            stage_detail=(
                "事实核验已完成，脚本已生成"
                if response.scripts
                else "流程已结束，请查看事实核验结果"
            ),
            progress=100,
            result=response,
        )
    except Exception as exc:
        _update_draft_rewrite_task(
            task_id,
            status="failed",
            stage="failed",
            stage_detail="生成任务执行失败",
            progress=100,
            error=clean_text(str(exc))[:500] or "稿件生成失败",
        )


def create_draft_rewrite_task(
    payload: DraftRewriteRequest,
    skills: list[TemplatePattern],
    on_complete: Optional[Callable[[DraftRewriteResponse], None]] = None,
) -> DraftRewriteTask:
    now = datetime.now(timezone.utc)
    task = DraftRewriteTask(
        id=new_id("rewrite-task"),
        status="queued",
        stage="queued",
        stage_detail="已进入生成队列",
        progress=0,
        timeout_seconds=draft_rewrite_timeout_seconds(),
        activities=[
            DraftRewriteActivity(
                id=new_id("activity"),
                phase="diagnosis",
                kind="status",
                title="任务已进入队列",
                detail="正在分配 Codex 写作任务。",
                status="active",
                created_at=now,
            )
        ],
        created_at=now,
        updated_at=now,
    )
    with DRAFT_REWRITE_LOCK:
        DRAFT_REWRITE_TASKS[task.id] = task
    thread = threading.Thread(
        target=_run_draft_rewrite_task,
        args=(task.id, payload, skills, on_complete),
        daemon=True,
        name=f"draft-rewrite-{task.id}",
    )
    thread.start()
    return task


def get_draft_rewrite_task(task_id: str) -> DraftRewriteTask:
    with DRAFT_REWRITE_LOCK:
        if task_id not in DRAFT_REWRITE_TASKS:
            raise KeyError(task_id)
        return DRAFT_REWRITE_TASKS[task_id]


def export_analysis_markdown(
    source: SourceVideo,
    transcript: Transcript,
    analysis: ScriptAnalysis,
    script: GeneratedScript,
    risk: RiskCheck,
) -> str:
    segments = "\n".join(
        f"- {segment.name}（{segment.start} / {segment.duration}）：{segment.summary}"
        for segment in analysis.structure
    )
    risks = "\n".join(
        f"- [{item.level}] {item.label}：{item.reason}；建议：{item.rewrite}"
        for item in risk.items
    )
    return f"""# {source.title}

## 脚本结构分析

- 账号类型：{analysis.account_type}
- 开头钩子：{analysis.hook}
- 冲突点：{analysis.conflict}
- 内容角度：{analysis.content_angle}
- 可复用模板：{analysis.reusable_template}

## 分段结构

{segments}

## 文本结构/口播正文预览

### {script.title}

{script.spoken_script}

## 风控结果

- 是否通过：{"是" if risk.passed else "否"}
- 风险等级：{risk.level}

{risks}

## 合并文稿

{transcript.content_text}
"""


def create_text_analysis(
    payload: AnalyzeTextRequest,
    existing_skills: Optional[list[TemplatePattern]] = None,
) -> AnalyzeTextResponse:
    bootstrap_templates()
    source = SourceVideo(
        id=payload.source_video_id or new_id("source"),
        input_type=payload.input_type,
        title=payload.title,
        url=payload.url,
        author=payload.author,
        publish_time=payload.publish_time,
        status="completed",
        created_at=payload.source_created_at or now_utc(),
    )
    transcript = Transcript(
        id=new_id("transcript"),
        source_video_id=source.id,
        asr_text=payload.asr_text
        if payload.asr_text is not None
        else payload.content
        if payload.input_type != "subtitle"
        else "",
        ocr_text=payload.ocr_text
        if payload.ocr_text is not None
        else payload.content
        if payload.input_type == "subtitle"
        else "",
        content_text=clean_text(payload.content),
        confidence=payload.transcript_confidence
        if payload.transcript_confidence is not None
        else 1.0
        if payload.input_type == "text"
        else 0.75,
        source=payload.transcript_source or payload.input_type,
    )
    analysis = analyze_structure(source, transcript)
    preset_draft = build_preset_draft_from_analysis(
        source, transcript, analysis, existing_skills
    )
    risk = risk_check(transcript.content_text)
    script = build_script(
        hotspot=payload.title,
        account_type=analysis.account_type,
        duration_seconds=45,
        tone="克制、有信息增量",
        goal="引发评论",
    )
    replace_source(source)
    ANALYSES.insert(0, analysis)
    GENERATED.insert(0, script)
    markdown = export_analysis_markdown(source, transcript, analysis, script, risk)
    return AnalyzeTextResponse(
        source_video=source,
        transcript=transcript,
        analysis=analysis,
        preset_draft=preset_draft,
        risk_check=risk,
        generated_preview=script,
        export_markdown=markdown,
        export_json={
            "source_video": source.model_dump(mode="json"),
            "transcript": transcript.model_dump(mode="json"),
            "analysis": analysis.model_dump(mode="json"),
            "preset_draft": preset_draft.model_dump(mode="json"),
            "risk_check": risk.model_dump(mode="json"),
            "generated_preview": script.model_dump(mode="json"),
        },
    )


def update_template_review(
    template_id: str, payload: TemplateReviewUpdateRequest
) -> TemplatePattern:
    bootstrap_templates()
    for index, template in enumerate(TEMPLATES):
        if template.id != template_id:
            continue
        updated = TemplatePattern(
            **{
                **template.model_dump(),
                "quality_score": payload.quality_score,
                "applicable_scenes": clean_items(payload.applicable_scenes),
                "unsuitable_scenes": clean_items(payload.unsuitable_scenes),
                "disabled_reason": optional_clean_text(payload.disabled_reason),
                "last_review_note": optional_clean_text(payload.last_review_note),
            }
        )
        TEMPLATES[index] = updated
        return updated
    raise KeyError(template_id)


def apply_skill_governance(
    template: TemplatePattern, payload: SkillGovernanceUpdateRequest
) -> TemplatePattern:
    template = enrich_skill_template(template)
    allowed_transitions: dict[SkillStatus, set[SkillStatus]] = {
        "candidate": {"candidate", "active", "paused", "retired"},
        "active": {"active", "paused", "retired"},
        "paused": {"paused", "candidate", "active", "retired"},
        "retired": {"retired"},
    }
    if payload.status not in allowed_transitions[template.status]:
        raise ValueError(
            f"Skill 当前为 {template.status}，不能转换为 {payload.status}。"
        )
    evidence = payload.evidence or template.evidence
    reviews = list(template.reviews)
    if payload.review is not None:
        review = payload.review.model_copy(
            update={"id": payload.review.id or new_id("review")}
        )
        reviews.append(review)
    summary = template.evaluation_summary
    if payload.status == "active" and payload.status != template.status:
        summary = load_skill_release_evidence(template, payload.release_report_path)
    updated = template.model_copy(
        update={
            "status": payload.status,
            # Governance state changes do not change the writing contract. A later
            # contract edit is the event that should create a new content version.
            "version": template.version,
            "owner": clean_text(payload.owner),
            "platforms": clean_items(payload.platforms) or ["douyin"],
            "required_inputs": clean_items(payload.required_inputs),
            "output_contract": clean_items(payload.output_contract),
            "promotion_reason": optional_clean_text(payload.promotion_reason),
            "expires_at": payload.expires_at,
            "reviewed_at": now_utc(),
            "evidence": evidence,
            "evaluation_summary": summary,
            "reviews": reviews,
            "disabled_reason": (
                template.disabled_reason if payload.status != "active" else None
            ),
        }
    )
    if payload.status == "active" and payload.status != template.status:
        errors = skill_promotion_errors(updated)
        if errors:
            raise ValueError("；".join(errors))
    return enrich_skill_template(updated)


def update_skill_governance(
    template_id: str, payload: SkillGovernanceUpdateRequest
) -> TemplatePattern:
    bootstrap_templates()
    for index, template in enumerate(TEMPLATES):
        if template.id == template_id:
            updated = apply_skill_governance(template, payload)
            TEMPLATES[index] = updated
            return updated
    raise KeyError(template_id)


def snapshot_script_version(script: GeneratedScript) -> GeneratedScriptVersion:
    return GeneratedScriptVersion(
        id=new_id("version"),
        source_script_id=script.id,
        title=script.title,
        spoken_script=script.spoken_script,
        shot_suggestions=list(script.shot_suggestions),
        subtitle_rhythm=list(script.subtitle_rhythm),
        comment_cta=script.comment_cta,
        production_status=script.production_status,
        version_label=script.version_label,
        editor_note=script.editor_note,
        created_at=script.updated_at or now_utc(),
    )


def update_generated_script(
    script_id: str, payload: GeneratedScriptUpdateRequest
) -> GeneratedScript:
    for index, script in enumerate(GENERATED):
        if script.id != script_id:
            continue
        title = clean_text(payload.title)
        spoken_script = clean_text(payload.spoken_script)
        comment_cta = clean_text(payload.comment_cta)
        updated = GeneratedScript(
            **{
                **script.model_dump(),
                "title": title,
                "spoken_script": spoken_script,
                "shot_suggestions": clean_items(payload.shot_suggestions),
                "subtitle_rhythm": clean_items(payload.subtitle_rhythm),
                "comment_cta": comment_cta,
                "risk_check": risk_check(f"{title} {spoken_script} {comment_cta}"),
                "production_status": payload.production_status,
                "version_label": clean_text(payload.version_label) or "v1",
                "editor_note": optional_clean_text(payload.editor_note),
                "updated_at": now_utc(),
                "version_history": [
                    snapshot_script_version(script),
                    *script.version_history,
                ][:12],
            }
        )
        GENERATED[index] = updated
        return updated
    raise KeyError(script_id)


def copy_generated_script_version(script_id: str, version_id: str) -> GeneratedScript:
    for script in GENERATED:
        if script.id != script_id:
            continue
        version = next(
            (item for item in script.version_history if item.id == version_id), None
        )
        if version is None:
            raise KeyError(version_id)
        copied = GeneratedScript(
            id=new_id("script"),
            title=f"{version.title}｜旧版复制",
            account_type=script.account_type,
            content_angle=script.content_angle,
            duration_seconds=script.duration_seconds,
            spoken_script=version.spoken_script,
            shot_suggestions=list(version.shot_suggestions),
            subtitle_rhythm=list(version.subtitle_rhythm),
            comment_cta=version.comment_cta,
            risk_check=risk_check(
                f"{version.title} {version.spoken_script} {version.comment_cta}"
            ),
            template_used=script.template_used,
            production_status="draft",
            version_label=f"{version.version_label}-copy",
            editor_note=f"从 {version.version_label} 历史版本复制。",
            updated_at=now_utc(),
            version_history=[],
        )
        GENERATED.insert(0, copied)
        return copied
    raise KeyError(script_id)


def copy_generated_script(script_id: str) -> GeneratedScript:
    for script in GENERATED:
        if script.id != script_id:
            continue
        copied = GeneratedScript(
            id=new_id("script"),
            title=f"{script.title}｜复用草稿",
            account_type=script.account_type,
            content_angle=script.content_angle,
            duration_seconds=script.duration_seconds,
            spoken_script=script.spoken_script,
            shot_suggestions=list(script.shot_suggestions),
            subtitle_rhythm=list(script.subtitle_rhythm),
            comment_cta=script.comment_cta,
            risk_check=risk_check(
                f"{script.title} {script.spoken_script} {script.comment_cta}"
            ),
            template_used=script.template_used,
            production_status="draft",
            version_label=f"{script.version_label or 'v1'}-reuse",
            editor_note="从已导出生产单复用为新草稿。"
            if script.production_status == "exported"
            else "从生产单复用为新草稿。",
            updated_at=now_utc(),
            version_history=[snapshot_script_version(script)],
        )
        GENERATED.insert(0, copied)
        return copied
    raise KeyError(script_id)


def create_upload_text_analysis(
    payload: UploadTextRequest,
    existing_skills: Optional[list[TemplatePattern]] = None,
) -> AnalyzeTextResponse:
    title = payload.title or payload.file_name
    return create_text_analysis(
        AnalyzeTextRequest(
            title=title,
            content=payload.content,
            input_type=payload.input_type,
        ),
        existing_skills,
    )


def douyin_downloader_mode() -> Literal["auto", "off", "required"]:
    mode = os.getenv("WORKBENCH_DOUYIN_DOWNLOADER_MODE", "auto").strip().lower()
    if mode not in {"auto", "off", "required"}:
        mode = "auto"
    return mode  # type: ignore[return-value]


DOUYIN_COOKIE_ENV_KEYS = {
    "msToken": "WORKBENCH_DOUYIN_COOKIE_MS_TOKEN",
    "ttwid": "WORKBENCH_DOUYIN_COOKIE_TTWID",
    "odin_tt": "WORKBENCH_DOUYIN_COOKIE_ODIN_TT",
    "passport_csrf_token": "WORKBENCH_DOUYIN_COOKIE_PASSPORT_CSRF_TOKEN",
    "sid_guard": "WORKBENCH_DOUYIN_COOKIE_SID_GUARD",
}


def parse_cookie_string(value: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for part in value.split(";"):
        key, separator, cookie_value = part.strip().partition("=")
        if separator and key and cookie_value:
            cookies[key.strip()] = cookie_value.strip()
    return cookies


def douyin_cookie_values() -> dict[str, str]:
    cookie_string = os.getenv("WORKBENCH_DOUYIN_COOKIE_STRING", "").strip()
    parsed = parse_cookie_string(cookie_string) if cookie_string else {}
    values: dict[str, str] = {}
    for config_key, env_key in DOUYIN_COOKIE_ENV_KEYS.items():
        values[config_key] = os.getenv(env_key, "").strip() or parsed.get(
            config_key, ""
        )
    return values


def has_douyin_cookie_config() -> bool:
    return any(value.strip() for value in douyin_cookie_values().values())


def classify_douyin_download_error(
    detail: str, timeout: bool = False, missing: bool = False, disabled: bool = False
) -> tuple[DouyinParserErrorCode, str, str, list[str]]:
    normalized = detail.lower()
    if disabled:
        return (
            "downloader_disabled",
            "抖音链接解析已关闭",
            "当前配置关闭了 douyin-downloader。",
            ["打开免登录链接提取能力后重试"],
        )
    if missing:
        return (
            "downloader_missing",
            "下载器未配置",
            "本机没有找到可执行的 douyin-downloader。",
            [
                "clone jiji262/douyin-downloader 到 ~/Code/douyin-downloader",
                "或设置 WORKBENCH_DOUYIN_DOWNLOADER_CMD 指向可执行命令",
            ],
        )
    if timeout:
        return (
            "timeout",
            "链接提取超时",
            "视频下载速度过慢；系统已保留临时分片并自动续传，但仍未在限定时间内完成。",
            ["稍后重试，系统会重新下载并继续处理", "若多次超时，再检查当前网络连接"],
        )
    if any(
        token in normalized
        for token in [
            "cookie",
            "登录",
            "登陆",
            "用户信息失败",
            "login",
            "auth",
            "sid_guard",
            "anti-bot",
            "empty 200 response",
            "failed to resolve short url",
            "short url",
            "status code 403",
            "status code 412",
            "http error 429",
            "rate limit",
            "connection reset",
            "temporarily unavailable",
        ]
    ):
        return (
            "cookie_required",
            "需要有效 Cookie 或登录态",
            "下载器已可调用，但当前链接需要有效抖音会话。系统会优先读取本机 Chrome 的 Cookie；如仍失败，可在高级设置中配置 Cookie。",
            [
                "确认 Chrome 中可正常打开该抖音链接后重试",
                "如仍失败，在高级设置中配置有效的 WORKBENCH_DOUYIN_COOKIE_STRING",
            ],
        )
    if (
        "未找到下载后的视频文件" in detail
        or "no such file" in normalized
        or "not found" in normalized
    ):
        return (
            "no_media",
            "未得到可处理视频",
            "下载器运行结束后没有发现可用视频文件。",
            ["确认链接是公开视频或作品页链接", "换一个公开链接重试"],
        )
    return (
        "unknown",
        "链接解析未完成",
        "链接提取链路返回了未分类错误。",
        ["确认分享文案里包含完整短链", "换一条公开视频链接重试"],
    )


def create_douyin_downloader_config(
    config_path: Path, link: str, output_dir: Path
) -> None:
    cookies = douyin_cookie_values()
    config_path.write_text(
        "\n".join(
            [
                "link:",
                f"  - {link}",
                f"path: {output_dir}",
                "mode:",
                "  - post",
                "number:",
                "  post: 1",
                "  collect: 0",
                "  collectmix: 0",
                "thread: 3",
                "retry_times: 3",
                'proxy: ""',
                "database: false",
                "progress:",
                "  quiet_logs: true",
                "cookies:",
                f'  msToken: "{cookies["msToken"]}"',
                f'  ttwid: "{cookies["ttwid"]}"',
                f'  odin_tt: "{cookies["odin_tt"]}"',
                f'  passport_csrf_token: "{cookies["passport_csrf_token"]}"',
                f'  sid_guard: "{cookies["sid_guard"]}"',
                "browser_fallback:",
                "  enabled: true",
                "  headless: true",
                "  max_scrolls: 20",
                "  idle_rounds: 2",
                "  wait_timeout_seconds: 45",
                "transcript:",
                "  enabled: false",
                "",
            ]
        ),
        encoding="utf-8",
    )


def douyin_downloader_command(
    config_path: Path, url: str, output_dir: Path
) -> tuple[Optional[list[str]], Optional[Path], str]:
    command_env = os.getenv("WORKBENCH_DOUYIN_DOWNLOADER_CMD", "").strip()
    if command_env:
        command = shlex.split(command_env)
        return (
            command + ["-c", str(config_path), "-u", url, "-p", str(output_dir)],
            None,
            "使用 WORKBENCH_DOUYIN_DOWNLOADER_CMD。",
        )

    repo_dir_env = os.getenv("WORKBENCH_DOUYIN_DOWNLOADER_DIR", "").strip()
    repo_candidates = (
        [Path(repo_dir_env).expanduser().resolve()] if repo_dir_env else []
    )
    repo_candidates.append(Path.home() / "Code" / "douyin-downloader")
    for repo_dir in repo_candidates:
        if (repo_dir / "run.py").exists():
            default_python = repo_dir / ".venv" / "bin" / "python"
            python = os.getenv(
                "WORKBENCH_DOUYIN_DOWNLOADER_PYTHON",
                str(default_python) if default_python.exists() else "python3",
            )
            message = (
                "使用 WORKBENCH_DOUYIN_DOWNLOADER_DIR。"
                if repo_dir_env
                else "使用默认本地仓库 ~/Code/douyin-downloader。"
            )
            return (
                [
                    python,
                    str(repo_dir / "run.py"),
                    "-c",
                    str(config_path),
                    "-u",
                    url,
                    "-p",
                    str(output_dir),
                ],
                repo_dir,
                message,
            )

    executable = shutil.which("douyin-downloader")
    if executable:
        return (
            [executable, "-c", str(config_path), "-u", url, "-p", str(output_dir)],
            None,
            "使用 PATH 中的 douyin-downloader。",
        )

    return (
        None,
        None,
        "未配置下载器。请设置 WORKBENCH_DOUYIN_DOWNLOADER_DIR 指向 jiji262/douyin-downloader 仓库，或设置 WORKBENCH_DOUYIN_DOWNLOADER_CMD。",
    )


def ytdlp_command(url: str, output_dir: Path) -> tuple[Optional[list[str]], str]:
    command_env = os.getenv("WORKBENCH_YTDLP_CMD", "").strip()
    executable = command_env or shutil.which("yt-dlp")
    if not executable:
        return None, "未检测到 yt-dlp。"
    output_template = str(output_dir / "yt-dlp-%(id)s.%(ext)s")
    command = shlex.split(executable) if command_env else [executable]
    use_insecure = os.getenv(
        "WORKBENCH_YTDLP_NO_CHECK_CERTIFICATE", "true"
    ).strip().lower() not in {"0", "false", "off", "no"}
    args = [
        "--no-playlist",
        "--max-downloads",
        "1",
        "--no-warnings",
        "--write-info-json",
    ]
    if use_insecure:
        args.append("--no-check-certificate")
    cookies_from_browser = os.getenv(
        "WORKBENCH_YTDLP_COOKIES_FROM_BROWSER", "chrome"
    ).strip()
    if cookies_from_browser:
        args.extend(["--cookies-from-browser", cookies_from_browser])
    args.extend(["--output", output_template, url])
    return (
        command + args,
        "使用 yt-dlp 读取本机浏览器会话解析链接。",
    )


def public_download_attempts() -> int:
    return max(1, int(os.getenv("WORKBENCH_DOUYIN_PUBLIC_ATTEMPTS", "2")))


def public_download_retry_delay(attempt: int) -> float:
    base = max(
        0.0, float(os.getenv("WORKBENCH_DOUYIN_RETRY_DELAY_SECONDS", "1"))
    )
    return min(base * attempt, 5.0)


def is_transient_public_download_failure(detail: str, timed_out: bool = False) -> bool:
    if timed_out:
        return True
    error_code, _, _, _ = classify_douyin_download_error(detail)
    return error_code == "public_access_unavailable"


def wait_before_public_download_retry(attempt: int) -> None:
    delay = public_download_retry_delay(attempt)
    if delay:
        time.sleep(delay)


def is_douyin_downloader_configured() -> bool:
    config_path = media_root() / "probe-config.yml"
    output_dir = media_root() / "probe-douyin"
    command, _, _ = douyin_downloader_command(
        config_path, "https://v.douyin.com/probe/", output_dir
    )
    return command is not None


def is_ytdlp_configured() -> bool:
    command, _ = ytdlp_command(
        "https://v.douyin.com/probe/", media_root() / "probe-ytdlp"
    )
    return command is not None


def is_douyin_link_resolver_configured() -> bool:
    return is_ytdlp_configured() or is_douyin_downloader_configured()


def media_files_in(output_dir: Path) -> list[Path]:
    suffixes = {".mp4", ".mov", ".m4v", ".flv", ".webm", ".mkv"}
    if not output_dir.exists():
        return []
    files = [
        path
        for path in output_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in suffixes
    ]
    return sorted(files, key=lambda path: path.stat().st_mtime, reverse=True)


def recover_playable_partial_media(output_dir: Path) -> list[Path]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe or not output_dir.exists():
        return []
    recovered: list[Path] = []
    for partial_path in output_dir.rglob("*.part"):
        target_path = Path(str(partial_path)[: -len(".part")])
        if target_path.suffix.lower() not in {".mp4", ".mov", ".m4v", ".webm", ".mkv"}:
            continue
        try:
            probe = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(partial_path),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=15,
            )
            duration = float(probe.stdout.strip() or "0")
        except (OSError, ValueError, subprocess.TimeoutExpired):
            continue
        if (
            probe.returncode != 0
            or duration < 1
            or partial_path.stat().st_size < 128_000
        ):
            continue
        partial_path.replace(target_path)
        recovered.append(target_path)
    return sorted(recovered, key=lambda path: path.stat().st_mtime, reverse=True)


def run_douyin_downloader(url: str, source_id: str) -> DouyinDownloadResult:
    mode = douyin_downloader_mode()
    output_dir = media_root() / "douyin" / source_id
    output_dir.mkdir(parents=True, exist_ok=True)
    if mode == "off":
        error_code, error_title, error_detail, action_items = (
            classify_douyin_download_error("", disabled=True)
        )
        return DouyinDownloadResult(
            status="skipped",
            output_dir=str(output_dir),
            error_code=error_code,
            error_title=error_title,
            error_detail=error_detail,
            action_items=action_items,
            message="抖音链接解析已通过 WORKBENCH_DOUYIN_DOWNLOADER_MODE=off 关闭。",
        )

    timeout = int(os.getenv("WORKBENCH_DOUYIN_DOWNLOADER_TIMEOUT", "90"))
    ytdlp_attempts = max(
        1,
        int(
            os.getenv(
                "WORKBENCH_YTDLP_DOWNLOAD_ATTEMPTS",
                str(public_download_attempts()),
            )
        ),
    )
    ytdlp, ytdlp_discovery_message = ytdlp_command(url, output_dir)
    ytdlp_failure_detail = ""
    ytdlp_timed_out = False
    if ytdlp:
        for attempt in range(1, ytdlp_attempts + 1):
            recovered_files: list[Path] = []
            try:
                completed = subprocess.run(
                    ytdlp,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                ytdlp_timed_out = False
                files = media_files_in(output_dir)
                recovered_files = (
                    recover_playable_partial_media(output_dir) if not files else []
                )
                files = files or recovered_files
                if not files:
                    ytdlp_failure_detail = (
                        clean_text(completed.stderr or completed.stdout)[-220:]
                        or "yt-dlp 未找到可下载媒体。"
                    )
            except subprocess.TimeoutExpired:
                ytdlp_timed_out = True
                files = media_files_in(output_dir)
                recovered_files = (
                    recover_playable_partial_media(output_dir) if not files else []
                )
                files = files or recovered_files
                ytdlp_failure_detail = (
                    f"yt-dlp 第 {attempt}/{ytdlp_attempts} 次下载超时（{timeout}s）；"
                    "已保留临时分片用于续传。"
                )

            if files:
                metadata = douyin_download_metadata(output_dir)
                return DouyinDownloadResult(
                    status="completed",
                    provider=(
                        "yt-dlp"
                        if not recovered_files
                        else "yt-dlp（已恢复完整临时视频）"
                    ),
                    output_dir=str(output_dir),
                    downloaded_files=[str(path) for path in files],
                    selected_video_path=str(files[0]),
                    message=(
                        f"yt-dlp 已下载 {len(files)} 个媒体文件，继续进入本地视频处理链路。"
                        if not recovered_files
                        else f"yt-dlp 下载任务虽未正常收尾，但已验证并恢复 {len(files)} 个完整视频，继续进入本地处理链路。"
                    ),
                    metadata_title=metadata.get("title"),
                    metadata_author=metadata.get("author"),
                    metadata_publish_time=metadata.get("publish_time"),
                )
            if attempt >= ytdlp_attempts or not is_transient_public_download_failure(
                ytdlp_failure_detail, ytdlp_timed_out
            ):
                break
            wait_before_public_download_retry(attempt)
    else:
        ytdlp_failure_detail = ytdlp_discovery_message

    config_path = output_dir / "config.yml"
    create_douyin_downloader_config(config_path, url, output_dir)
    command, cwd, discovery_message = douyin_downloader_command(config_path, url, output_dir)
    if not command:
        status: Literal["skipped", "failed"] = (
            "failed" if mode == "required" else "skipped"
        )
        detail = f"{ytdlp_failure_detail} {discovery_message}".strip()
        error_code, error_title, error_detail, action_items = (
            classify_douyin_download_error(
                detail,
                timeout=ytdlp_timed_out,
                missing=not ytdlp and not ytdlp_timed_out,
            )
        )
        return DouyinDownloadResult(
            status=status,
            provider="yt-dlp -> jiji262/douyin-downloader",
            output_dir=str(output_dir),
            error_code=error_code,
            error_title=error_title,
            error_detail=error_detail,
            action_items=action_items,
            message=f"{detail} 当前链接任务停止，不生成分析。",
        )

    fallback_attempts = public_download_attempts()
    fallback_timed_out = False
    fallback_output = ""
    fallback_returncode = 1
    files: list[Path] = []
    for attempt in range(1, fallback_attempts + 1):
        try:
            completed = subprocess.run(
                command,
                cwd=str(cwd) if cwd else None,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            fallback_timed_out = False
            fallback_returncode = completed.returncode
            fallback_output = clean_text(completed.stderr or completed.stdout)
            files = media_files_in(output_dir)
        except subprocess.TimeoutExpired:
            fallback_timed_out = True
            fallback_output = (
                f"douyin-downloader 第 {attempt}/{fallback_attempts} 次下载超时（{timeout}s）。"
            )
            files = media_files_in(output_dir)

        if files:
            break
        if attempt >= fallback_attempts or not is_transient_public_download_failure(
            fallback_output, fallback_timed_out
        ):
            break
        wait_before_public_download_retry(attempt)

    if fallback_returncode != 0 or not files:
        detail = (
            clean_text(f"{ytdlp_failure_detail} {fallback_output}")[-420:]
            or "未找到下载后的视频文件。"
        )
        error_code, error_title, error_detail, action_items = (
            classify_douyin_download_error(
                detail, timeout=ytdlp_timed_out or fallback_timed_out
            )
        )
        return DouyinDownloadResult(
            status="failed" if mode == "required" else "skipped",
            provider="yt-dlp -> jiji262/douyin-downloader",
            output_dir=str(output_dir),
            downloaded_files=[str(path) for path in files],
            error_code=error_code,
            error_title=error_title,
            error_detail=error_detail,
            action_items=action_items,
            message=f"douyin-downloader 未完成下载：{detail} 当前链接任务停止，不生成分析。",
        )

    metadata = douyin_download_metadata(output_dir)
    return DouyinDownloadResult(
        status="completed",
        provider="jiji262/douyin-downloader",
        output_dir=str(output_dir),
        downloaded_files=[str(path) for path in files],
        selected_video_path=str(files[0]),
        message=f"douyin-downloader 已下载 {len(files)} 个媒体文件，继续进入本地视频处理链路。",
        metadata_title=metadata.get("title"),
        metadata_author=metadata.get("author"),
        metadata_publish_time=metadata.get("publish_time"),
    )


def create_link_task(payload: LinkTaskRequest) -> LinkTaskResponse:
    normalized_url = normalize_douyin_url_input(payload.url)
    share_context = parse_douyin_share_source_context(payload.url)
    source = SourceVideo(
        id=new_id("source"),
        input_type="douyin_url",
        title=(
            clean_text(share_context.get("title", ""))
            or "抖音链接解析任务"
        ),
        url=normalized_url,
        author=share_context.get("author"),
        status="processing",
        created_at=now_utc(),
    )
    download = run_douyin_downloader(normalized_url, source.id)
    source_title = (
        clean_text(download.metadata_title or "")
        or source.title
        or Path(download.selected_video_path or "").stem
    )
    source_author = clean_text(download.metadata_author or "") or source.author
    video_upload = (
        create_video_upload_result(
            Path(download.selected_video_path).name,
            Path(download.selected_video_path),
            run_extractors=True,
            context_text=payload.url,
            source_title=source_title,
            source_url=normalized_url,
            source_author=source_author,
            source_publish_time=download.metadata_publish_time,
            source_created_at=source.created_at,
        )
        if download.selected_video_path
        else None
    )
    transcript_extracted = bool(
        video_upload
        and video_upload.transcript
        and video_upload.transcript.content_text.strip()
    )
    manuscript_ready = bool(
        transcript_extracted
        and video_upload
        and video_upload.correction_status == "completed"
    )
    source = source.model_copy(
        update={
            "status": "completed" if manuscript_ready else "failed",
            "material_path": download.selected_video_path,
            "title": video_upload.source_video.title
            if video_upload is not None
            else source_title,
            "author": video_upload.source_video.author
            if video_upload is not None
            else source_author,
            "publish_time": video_upload.source_video.publish_time
            if video_upload is not None
            else download.metadata_publish_time,
        }
    )
    SOURCES.insert(0, source)
    if manuscript_ready and video_upload:
        message = f"{download.message} 已真实提取视频稿件。{video_upload.asr_message} {video_upload.ocr_message}"
    elif transcript_extracted and video_upload:
        message = (
            f"{download.message} 已提取语音稿，但自动校正未通过质量门禁；"
            f"本次停止拆解。{video_upload.transcript_quality_message}"
        )
    elif video_upload:
        message = f"{download.message} 但没有识别出足够的视频稿件文本；本次不生成分析，不使用标题猜测。{video_upload.asr_message} {video_upload.ocr_message}"
    else:
        message = f"{download.message} 未能从抖音链接取得视频稿件；本次不生成分析，不使用兜底内容。"
    parser_status: Literal["completed", "skipped", "failed"] = (
        "completed"
        if manuscript_ready
        else "skipped"
        if download.status == "skipped"
        else "failed"
    )
    fallback_inputs = (
        []
        if manuscript_ready
        else ["上传视频文件", "上传字幕文件", "粘贴转写文本"]
    )
    response = LinkTaskResponse(
        source_video=source,
        parser_status=parser_status,
        parser_provider=download.provider,
        output_dir=download.output_dir,
        downloaded_files=download.downloaded_files,
        video_upload=video_upload,
        parser_error_code=download.error_code
        if download.error_code
        else (
            None
            if manuscript_ready
            else "transcript_quality"
            if transcript_extracted
            else "no_media"
        ),
        parser_error_title=download.error_title
        if download.error_title
        else (
            None
            if manuscript_ready
            else "稿件校正未通过"
            if transcript_extracted
            else "未识别出视频稿件"
        ),
        parser_error_detail=download.error_detail
        if download.error_detail
        else (
            None
            if manuscript_ready
            else video_upload.transcript_quality_message
            if transcript_extracted and video_upload
            else "链接提取链路未产出足够视频稿件；系统不会用标题、描述或手动文本伪装分析。"
        ),
        parser_action_items=download.action_items
        if download.error_code
        else (
            []
            if manuscript_ready
            else ["检查自动标记的待确认片段后重新提取"]
            if transcript_extracted
            else ["确认分享文案里包含完整短链后重试", "更换公开视频链接后重新提取"]
        ),
        message=message,
        fallback_inputs=fallback_inputs,
    )
    record_link_diagnostic(response)
    return response


def extract_audio(
    source_path: Path, source_id: str
) -> tuple[Literal["completed", "skipped", "failed"], Optional[Path], str]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return (
            "skipped",
            None,
            "视频已保存，但当前环境未检测到 FFmpeg。请先上传字幕/转写文本继续分析，或安装 FFmpeg 后重试抽音频。",
        )

    audio_dir = media_root() / "audios"
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_path = audio_dir / f"{source_id}.wav"
    command = [
        ffmpeg,
        "-y",
        "-i",
        str(source_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(audio_path),
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return (
            "failed",
            None,
            "视频已保存，但 FFmpeg 抽音频超时。请上传字幕/转写文本继续分析。",
        )

    if completed.returncode != 0 or not audio_path.exists():
        detail = clean_text(completed.stderr)[-180:] or "FFmpeg 未能识别该视频文件。"
        return (
            "failed",
            None,
            f"视频已保存，但抽音频失败：{detail} 请上传字幕/转写文本继续分析。",
        )

    return (
        "completed",
        audio_path,
        "视频已保存并完成音频抽取。",
    )


def asr_mode() -> Literal["auto", "off", "required"]:
    mode = os.getenv("WORKBENCH_ASR_MODE", "auto").strip().lower()
    if mode not in {"auto", "off", "required"}:
        mode = "auto"
    return mode  # type: ignore[return-value]


def parse_funasr_text(result: object) -> tuple[str, list[str]]:
    if not isinstance(result, list):
        return "", []

    texts: list[str] = []
    timestamps: list[str] = []
    for item in result:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or item.get("raw_text") or "").strip()
        if text:
            texts.append(text)
        sentence_info = item.get("sentence_info")
        if isinstance(sentence_info, list):
            for sentence in sentence_info:
                if not isinstance(sentence, dict):
                    continue
                sentence_text = str(sentence.get("text") or "").strip()
                if not sentence_text:
                    continue
                start = sentence.get("start")
                end = sentence.get("end")
                if start is not None and end is not None:
                    timestamps.append(f"{start}-{end}: {sentence_text}")
                else:
                    timestamps.append(sentence_text)
    return clean_text(" ".join(texts)), timestamps


def get_funasr_model(hotword_enabled: bool = False) -> object:
    model_name = (
        os.getenv(
            "WORKBENCH_FUNASR_HOTWORD_MODEL",
            "iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
        ).strip()
        if hotword_enabled
        else os.getenv("WORKBENCH_FUNASR_MODEL", "paraformer-zh").strip()
    )
    if model_name in _FUNASR_MODELS:
        return _FUNASR_MODELS[model_name]

    from funasr import AutoModel

    kwargs: dict[str, object] = {
        "model": model_name,
    }
    vad_model = os.getenv("WORKBENCH_FUNASR_VAD_MODEL", "fsmn-vad").strip()
    punc_model = os.getenv("WORKBENCH_FUNASR_PUNC_MODEL", "ct-punc").strip()
    device = os.getenv("WORKBENCH_FUNASR_DEVICE", "cpu").strip()
    if vad_model:
        kwargs["vad_model"] = vad_model
    if punc_model:
        kwargs["punc_model"] = punc_model
    if device:
        kwargs["device"] = device

    _FUNASR_MODELS[model_name] = AutoModel(**kwargs)
    return _FUNASR_MODELS[model_name]


def transcribe_audio(
    audio_path: Optional[Path], hotwords: Optional[list[str]] = None
) -> AsrTranscriptionResult:
    mode = asr_mode()
    if audio_path is None:
        return AsrTranscriptionResult(
            status="skipped",
            text="",
            message="未生成音频文件，ASR 暂不执行。请上传字幕/转写文本继续分析。",
        )
    if mode == "off":
        return AsrTranscriptionResult(
            status="skipped",
            text="",
            message="ASR 已通过 WORKBENCH_ASR_MODE=off 关闭。请上传字幕/转写文本继续分析。",
        )
    if find_spec("funasr") is None:
        status: Literal["skipped", "failed"] = (
            "failed" if mode == "required" else "skipped"
        )
        return AsrTranscriptionResult(
            status=status,
            text="",
            message="当前 Python 环境未安装 FunASR。音频已保留，请安装 FunASR 或上传字幕/转写文本继续分析。",
        )

    try:
        model = get_funasr_model(hotword_enabled=bool(hotwords))
        generate_options: dict[str, object] = {"input": str(audio_path)}
        if hotwords:
            generate_options["hotword"] = " ".join(hotwords)
        result = model.generate(**generate_options)
        text, timestamps = parse_funasr_text(result)
    except Exception as exc:
        status = "failed" if mode == "required" else "skipped"
        return AsrTranscriptionResult(
            status=status,
            text="",
            message=f"FunASR 转写未完成：{clean_text(str(exc))[:180]}。请上传字幕/转写文本继续分析。",
        )

    if len(text) < 10:
        return AsrTranscriptionResult(
            status="failed" if mode == "required" else "skipped",
            text=text,
            timestamps=timestamps,
            message="FunASR 未得到足够可分析文本。请上传字幕/转写文本继续分析。",
        )

    return AsrTranscriptionResult(
        status="completed",
        text=text,
        timestamps=timestamps,
        message="FunASR 已生成转写文本，可直接开始结构分析，也可以继续上传字幕/OCR 文本校准。",
    )


def ocr_mode() -> Literal["auto", "off", "required"]:
    mode = os.getenv("WORKBENCH_OCR_MODE", "auto").strip().lower()
    if mode not in {"auto", "off", "required"}:
        mode = "auto"
    return mode  # type: ignore[return-value]


def model_worker_timeout() -> int:
    try:
        return max(30, int(os.getenv("WORKBENCH_MODEL_WORKER_TIMEOUT", "300")))
    except ValueError:
        return 300


def model_worker_candidates() -> list[str]:
    configured = os.getenv("WORKBENCH_MODEL_WORKER_PYTHON", "").strip()
    project_model_python = (
        Path(__file__).resolve().parents[2] / ".venv-model" / "bin" / "python"
    )
    candidates = [configured, str(project_model_python), sys.executable]
    if os.getenv("WORKBENCH_ALLOW_SYSTEM_MODEL_PYTHON", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        candidates.append("/usr/bin/python3")
    unique: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in unique and Path(candidate).exists():
            unique.append(candidate)
    return unique


def model_worker_python(module: str) -> str | None:
    if module in MODEL_WORKER_PYTHON:
        return MODEL_WORKER_PYTHON[module]

    for candidate in model_worker_candidates():
        try:
            probe = subprocess.run(
                [
                    candidate,
                    "-c",
                    (
                        "import importlib.util, sys; "
                        f"sys.exit(0 if importlib.util.find_spec({module!r}) else 1)"
                    ),
                ],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if probe.returncode == 0:
            MODEL_WORKER_PYTHON[module] = candidate
            return candidate

    MODEL_WORKER_PYTHON[module] = None
    return None


def run_model_worker(
    kind: str,
    inputs: list[Path] | None = None,
    hotwords: list[str] | None = None,
) -> tuple[dict[str, object] | None, str]:
    module = "funasr" if kind.endswith("asr") else "paddleocr"
    executable = model_worker_python(module)
    if executable is None:
        return None, f"当前环境未找到可运行 {module} 的模型工作进程。"

    worker = (
        Path(__file__).resolve().parents[1] / "scripts" / "workbench_model_worker.py"
    )
    if not worker.exists():
        return None, "模型工作进程脚本缺失。"

    result_dir = media_root() / "worker-results"
    result_dir.mkdir(parents=True, exist_ok=True)
    result_path = result_dir / f"{kind}-{uuid.uuid4().hex}.json"
    command = [executable, str(worker), "--kind", kind, "--output", str(result_path)]
    for item in inputs or []:
        command.extend(["--input", str(item)])
    for hotword in hotwords or []:
        command.extend(["--hotword", hotword])

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=model_worker_timeout(),
            check=False,
        )
        raw = result_path.read_text(encoding="utf-8") if result_path.exists() else ""
    except subprocess.TimeoutExpired:
        return None, "模型工作进程超时，已保留媒体文件，可上传字幕或转写文本继续分析。"
    except OSError as exc:
        return None, f"模型工作进程无法启动：{clean_text(str(exc))[:160]}。"
    finally:
        result_path.unlink(missing_ok=True)

    if not raw:
        detail = clean_text(completed.stderr or completed.stdout)[:160]
        return None, f"模型工作进程异常退出（code {completed.returncode}）。{detail}"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None, "模型工作进程返回了无法解析的结果。"
    if not isinstance(payload, dict):
        return None, "模型工作进程返回格式不正确。"
    if completed.returncode != 0 and "error" in payload:
        return None, clean_text(str(payload.get("error") or "模型工作进程执行失败。"))[
            :200
        ]
    return payload, ""


def transcribe_audio_isolated(
    audio_path: Optional[Path], hotwords: Optional[list[str]] = None
) -> AsrTranscriptionResult:
    if audio_path is None or asr_mode() == "off":
        return transcribe_audio(audio_path, hotwords=hotwords)
    payload, error = run_model_worker("asr", [audio_path], hotwords=hotwords)
    if payload is not None:
        try:
            return AsrTranscriptionResult.model_validate(payload)
        except Exception:
            error = "FunASR 工作进程返回格式不正确。"
    status: Literal["skipped", "failed"] = (
        "failed" if asr_mode() == "required" else "skipped"
    )
    return AsrTranscriptionResult(
        status=status,
        message=f"FunASR 在隔离进程中未完成：{error} 请上传字幕/转写文本继续分析。",
    )


def run_paddle_ocr_isolated(frames: list[Path]) -> OcrExtractionResult:
    if not frames or ocr_mode() == "off":
        return run_paddle_ocr(frames)
    payload, error = run_model_worker("ocr", frames)
    if payload is not None:
        try:
            return OcrExtractionResult.model_validate(payload)
        except Exception:
            error = "PaddleOCR 工作进程返回格式不正确。"
    status: Literal["skipped", "failed"] = (
        "failed" if ocr_mode() == "required" else "skipped"
    )
    return OcrExtractionResult(
        status=status,
        frame_paths=[str(frame) for frame in frames],
        message=f"PaddleOCR 在隔离进程中未完成：{error} 请上传字幕/转写文本继续分析。",
    )


def extract_video_frames(
    source_path: Path, source_id: str
) -> tuple[Literal["completed", "skipped", "failed"], list[Path], str]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return "skipped", [], "当前环境未检测到 FFmpeg，无法抽取 OCR 关键帧。"

    frame_dir = media_root() / "frames" / source_id
    frame_dir.mkdir(parents=True, exist_ok=True)
    frame_count = max(1, min(12, int(os.getenv("WORKBENCH_OCR_FRAME_COUNT", "4"))))
    frame_pattern = frame_dir / "frame-%03d.jpg"
    command = [
        ffmpeg,
        "-y",
        "-i",
        str(source_path),
        "-vf",
        "fps=1",
        "-frames:v",
        str(frame_count),
        str(frame_pattern),
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return "failed", [], "FFmpeg 抽取 OCR 关键帧超时。"

    frames = sorted(frame_dir.glob("frame-*.jpg"))
    if completed.returncode != 0 or not frames:
        detail = clean_text(completed.stderr)[-180:] or "FFmpeg 未能抽出关键帧。"
        return "failed", [], f"OCR 关键帧抽取失败：{detail}"
    return "completed", frames, f"已抽取 {len(frames)} 张 OCR 关键帧。"


def get_paddle_ocr_model() -> object:
    global _PADDLE_OCR_MODEL
    if _PADDLE_OCR_MODEL is not None:
        return _PADDLE_OCR_MODEL

    from paddleocr import PaddleOCR

    engine = os.getenv("WORKBENCH_PADDLEOCR_ENGINE", "paddle").strip()
    kwargs: dict[str, object] = {
        "use_doc_orientation_classify": False,
        "use_doc_unwarping": False,
        "use_textline_orientation": False,
    }
    if engine:
        kwargs["engine"] = engine
    try:
        _PADDLE_OCR_MODEL = PaddleOCR(**kwargs)
    except TypeError:
        _PADDLE_OCR_MODEL = PaddleOCR(
            use_angle_cls=True,
            lang=os.getenv("WORKBENCH_PADDLEOCR_LANG", "ch"),
        )
    return _PADDLE_OCR_MODEL


def asr_runtime_item() -> ModelRuntimeItem:
    mode = asr_mode()
    available = model_worker_python("funasr") is not None
    initialized = False
    if mode == "off":
        status: Literal["ready", "not_loaded", "disabled", "missing", "failed"] = (
            "disabled"
        )
        detail = "ASR 已通过 WORKBENCH_ASR_MODE=off 关闭。"
    elif not available:
        status = "missing"
        detail = "当前 Python 环境未安装 FunASR，无法执行中文口播转写。"
    else:
        status = "not_loaded"
        detail = "FunASR 会在隔离进程中按任务加载，模型异常不会中断工作台。"
    return ModelRuntimeItem(
        key="asr",
        label="FunASR 中文口播转写",
        available=available and mode != "off",
        mode=mode,
        initialized=initialized,
        status=status,
        detail=detail,
        action_items=[
            "如需真实口播转写，先确认网络可访问 ModelScope 或已缓存模型。",
            "不需要口播时可关闭 ASR，只运行 OCR 或上传字幕/转写文本。",
        ],
    )


def ocr_runtime_item() -> ModelRuntimeItem:
    mode = ocr_mode()
    available = model_worker_python("paddleocr") is not None
    initialized = False
    if mode == "off":
        status: Literal["ready", "not_loaded", "disabled", "missing", "failed"] = (
            "disabled"
        )
        detail = "OCR 已通过 WORKBENCH_OCR_MODE=off 关闭。"
    elif not available:
        status = "missing"
        detail = "当前 Python 环境未安装 PaddleOCR，无法识别硬字幕和画面文字。"
    else:
        status = "not_loaded"
        detail = "PaddleOCR 会在隔离进程中按任务加载，模型异常不会中断工作台。"
    return ModelRuntimeItem(
        key="ocr",
        label="PaddleOCR 硬字幕识别",
        available=available and mode != "off",
        mode=mode,
        initialized=initialized,
        status=status,
        detail=detail,
        action_items=[
            "如需真实硬字幕识别，建议先用短视频测试 OCR 初始化耗时。",
            "没有硬字幕时可关闭 OCR，只运行 ASR 或上传字幕/转写文本。",
        ],
    )


def model_runtime_status() -> ModelRuntimeStatus:
    items = [asr_runtime_item(), ocr_runtime_item()]
    ready_count = sum(1 for item in items if item.available)
    return ModelRuntimeStatus(
        items=items,
        ready_count=ready_count,
        total_count=len(items),
        message="模型状态只做本机可用性和当前进程加载状态判断；真实下载进度由模型库自身控制。",
    )


def warmup_models(payload: ModelWarmupRequest) -> ModelWarmupResponse:
    if not payload.execute:
        return ModelWarmupResponse(
            items=model_runtime_status().items,
            executed=False,
            message="已完成预热检查，未执行真实模型加载。勾选执行预热后才可能触发模型下载。",
        )

    messages: list[str] = []
    if payload.run_asr:
        result, error = run_model_worker("warmup-asr")
        if result is not None:
            messages.append(str(result.get("message") or "FunASR 模型加载验证完成。"))
        else:
            messages.append(f"FunASR 预热失败：{error}")
    if payload.run_ocr:
        result, error = run_model_worker("warmup-ocr")
        if result is not None:
            messages.append(
                str(result.get("message") or "PaddleOCR 模型加载验证完成。")
            )
        else:
            messages.append(f"PaddleOCR 预热失败：{error}")
    if not messages:
        messages.append("未选择 ASR 或 OCR，未执行模型加载。")
    return ModelWarmupResponse(
        items=model_runtime_status().items,
        executed=True,
        message=f"{' '.join(messages)} 模型在隔离任务进程中运行，预热只验证可加载性，不占用 API 主进程。",
    )


def collect_ocr_texts(value: object, texts: list[str], depth: int = 0) -> None:
    if depth > 6 or value is None:
        return
    if isinstance(value, str):
        stripped = value.strip()
        if stripped and len(stripped) > 1:
            texts.append(stripped)
        return
    if isinstance(value, dict):
        for key in ("rec_texts", "texts"):
            maybe_texts = value.get(key)
            if isinstance(maybe_texts, list):
                for text in maybe_texts:
                    collect_ocr_texts(text, texts, depth + 1)
        for key in ("rec_text", "text"):
            maybe_text = value.get(key)
            if isinstance(maybe_text, str):
                collect_ocr_texts(maybe_text, texts, depth + 1)
        for key in ("res", "overall_ocr_res", "ocr_res"):
            collect_ocr_texts(value.get(key), texts, depth + 1)
        return
    if isinstance(value, (list, tuple)):
        if (
            len(value) == 2
            and isinstance(value[1], (list, tuple))
            and value[1]
            and isinstance(value[1][0], str)
        ):
            collect_ocr_texts(value[1][0], texts, depth + 1)
            return
        for item in value:
            collect_ocr_texts(item, texts, depth + 1)
        return

    json_value = getattr(value, "json", None)
    if callable(json_value):
        try:
            collect_ocr_texts(json_value(), texts, depth + 1)
            return
        except Exception:
            pass
    if isinstance(json_value, dict):
        collect_ocr_texts(json_value, texts, depth + 1)
        return
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            collect_ocr_texts(to_dict(), texts, depth + 1)
        except Exception:
            return


def dedupe_texts(texts: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for text in texts:
        normalized = clean_text(text)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def run_paddle_ocr(frames: list[Path]) -> OcrExtractionResult:
    mode = ocr_mode()
    frame_paths = [str(frame) for frame in frames]
    if not frames:
        return OcrExtractionResult(
            status="skipped",
            frame_paths=[],
            message="未抽取到关键帧，OCR 暂不执行。",
        )
    if mode == "off":
        return OcrExtractionResult(
            status="skipped",
            frame_paths=frame_paths,
            message="OCR 已通过 WORKBENCH_OCR_MODE=off 关闭。",
        )
    if find_spec("paddleocr") is None:
        status: Literal["skipped", "failed"] = (
            "failed" if mode == "required" else "skipped"
        )
        return OcrExtractionResult(
            status=status,
            frame_paths=frame_paths,
            message="当前 Python 环境未安装 PaddleOCR。关键帧已保留，请安装 PaddleOCR 或上传字幕/转写文本继续分析。",
        )

    try:
        model = get_paddle_ocr_model()
        texts: list[str] = []
        for frame in frames:
            if hasattr(model, "predict"):
                result = model.predict(str(frame))
            else:
                result = model.ocr(str(frame), cls=True)
            collect_ocr_texts(result, texts)
        subtitle_texts = [
            item for item in dedupe_texts(texts) if is_likely_subtitle_text(item)
        ]
        text = clean_text(" ".join(subtitle_texts))
    except Exception as exc:
        status = "failed" if mode == "required" else "skipped"
        return OcrExtractionResult(
            status=status,
            frame_paths=frame_paths,
            message=f"PaddleOCR 识别未完成：{clean_text(str(exc))[:180]}。请上传字幕/转写文本继续分析。",
        )

    if len(text) < 4:
        return OcrExtractionResult(
            status="failed" if mode == "required" else "skipped",
            text=text,
            frame_paths=frame_paths,
            message="PaddleOCR 未识别到足够字幕文本。请上传字幕/转写文本继续分析。",
        )

    return OcrExtractionResult(
        status="completed",
        text=text,
        frame_paths=frame_paths,
        message="PaddleOCR 已识别关键帧文字，可与 ASR/字幕文本合并分析。",
    )


def remember_video_upload(response: VideoUploadResponse) -> None:
    VIDEO_UPLOADS[response.source_video.id] = response


def replace_source(source: SourceVideo) -> None:
    for index, current in enumerate(SOURCES):
        if current.id == source.id:
            SOURCES[index] = source
            return
    SOURCES.insert(0, source)


def skipped_asr_message(enabled: bool) -> AsrTranscriptionResult:
    if enabled:
        return AsrTranscriptionResult(
            status="skipped",
            message="ASR 未启动。请检查音频抽取结果，或上传字幕/转写文本继续分析。",
        )
    return AsrTranscriptionResult(
        status="skipped",
        message="本次后台任务未勾选 FunASR，仅保留音频文件。",
    )


def skipped_ocr_message(enabled: bool, frames: list[Path]) -> OcrExtractionResult:
    if enabled:
        return OcrExtractionResult(
            status="skipped",
            frame_paths=[str(frame) for frame in frames],
            message="OCR 未启动。请检查关键帧抽取结果，或上传字幕/转写文本继续分析。",
        )
    return OcrExtractionResult(
        status="skipped",
        frame_paths=[str(frame) for frame in frames],
        message="本次后台任务未勾选 PaddleOCR，仅保留关键帧。",
    )


def cleanup_processed_media(
    source: SourceVideo,
    audio_path: Optional[Path],
    frames: list[Path],
) -> tuple[
    SourceVideo, Optional[Path], list[Path], Literal["completed", "failed"], str
]:
    root = media_root()
    candidates = [Path(source.material_path)] if source.material_path else []
    if audio_path:
        candidates.append(audio_path)
    candidates.extend(frames)

    removed = 0
    errors: list[str] = []
    for path in {candidate.resolve() for candidate in candidates if candidate.exists()}:
        try:
            path.relative_to(root)
        except ValueError:
            errors.append(f"拒绝清理媒体目录外文件：{path.name}")
            continue
        try:
            path.unlink()
            removed += 1
        except OSError as exc:
            errors.append(f"{path.name}：{clean_text(str(exc))[:80]}")

    if errors:
        return (
            source,
            audio_path,
            frames,
            "failed",
            f"转写已完成，但临时媒体清理未完成：{'；'.join(errors)}",
        )

    cleaned_source = source.model_copy(update={"material_path": None})
    return (
        cleaned_source,
        None,
        [],
        "completed",
        f"已清理 {removed} 个临时媒体文件，仅保留转写、分析和模板资产。",
    )


def build_video_upload_from_extraction(
    upload: VideoUploadResponse,
    audio_path: Optional[Path],
    frames: list[Path],
    extraction_status: Literal["completed", "skipped", "failed"],
    extraction_message: str,
    asr: AsrTranscriptionResult,
    ocr: OcrExtractionResult,
) -> VideoUploadResponse:
    merged_text, transcript_source = build_primary_transcript(asr.text, ocr.text)
    corrections: list[TranscriptCorrection] = []
    unresolved_fragments: list[str] = []
    quality_score = 0
    quality_message = "未生成足够稿件，无法执行自动校正。"
    context_terms: list[str] = []
    if len(merged_text) >= 10:
        (
            merged_text,
            corrections,
            unresolved_fragments,
            quality_score,
            quality_message,
            context_terms,
        ) = correct_primary_transcript(merged_text, "", ocr.text)
    correction_status: Literal["completed", "needs_review", "skipped", "failed"] = (
        "needs_review"
        if unresolved_fragments
        else "completed"
        if len(merged_text) >= 10
        else "skipped"
    )
    transcript = (
        Transcript(
            id=new_id("transcript"),
            source_video_id=upload.source_video.id,
            asr_text=asr.text,
            ocr_text=ocr.text,
            content_text=merged_text,
            timestamps=asr.timestamps,
            confidence=quality_score / 100,
            source=transcript_source,
        )
        if len(merged_text) >= 10
        else None
    )
    source = upload.source_video.model_copy(
        update={"status": "completed" if transcript else "needs_upload"}
    )
    cleanup_status: Literal["retained", "completed", "failed"] = "retained"
    cleanup_message = "未生成足够文本，临时媒体保留以便重试或补充字幕。"
    if transcript is not None:
        source, audio_path, frames, cleanup_status, cleanup_message = (
            cleanup_processed_media(source, audio_path, frames)
        )
    next_step = (
        "ASR/OCR 已生成可分析文本，可直接开始结构分析。"
        if transcript
        else "后台提取未得到足够文本。请上传字幕/转写文本，或手动粘贴口播文案继续分析。"
    )
    return VideoUploadResponse(
        source_video=source,
        audio_path=str(audio_path) if audio_path else None,
        frame_paths=[str(frame) for frame in frames],
        extraction_status=extraction_status,
        asr_status=asr.status,
        asr_provider=asr.provider,
        asr_text=asr.text,
        ocr_status=ocr.status,
        ocr_provider=ocr.provider,
        ocr_text=ocr.text,
        transcript=transcript,
        correction_status=correction_status,
        corrections=corrections,
        unresolved_fragments=unresolved_fragments,
        transcript_quality_score=quality_score,
        transcript_quality_message=quality_message,
        context_terms=context_terms,
        message=extraction_message,
        asr_message=asr.message,
        ocr_message=ocr.message,
        next_step=next_step,
        fallback_inputs=["上传字幕文件", "上传转写文本", "粘贴口播文案"],
        media_cleanup_status=cleanup_status,
        media_cleanup_message=cleanup_message,
    )


def video_extraction_state_path() -> Path:
    return media_root() / "video-extraction-tasks.json"


def persist_video_extraction_state() -> None:
    path = video_extraction_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "tasks": [
            task.model_dump(mode="json") for task in VIDEO_EXTRACTION_TASKS.values()
        ],
        "options": {
            task_id: options.model_dump(mode="json")
            for task_id, options in VIDEO_EXTRACTION_OPTIONS.items()
        },
    }
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    tmp_path.replace(path)


def load_video_extraction_state() -> None:
    global VIDEO_EXTRACTION_STATE_LOADED
    if VIDEO_EXTRACTION_STATE_LOADED:
        return
    VIDEO_EXTRACTION_STATE_LOADED = True
    path = video_extraction_state_path()
    if not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return

    loaded_tasks: dict[str, VideoExtractionTask] = {}
    for raw_task in payload.get("tasks", []):
        try:
            task = VideoExtractionTask.model_validate(raw_task)
        except Exception:
            continue
        if task.status in {"queued", "processing"}:
            task = task.model_copy(
                update={
                    "status": "failed",
                    "stage": "服务重启后任务已停止",
                    "progress": 100,
                    "error": "后台任务所在进程已重启，无法继续原任务。",
                    "next_step": "请点击重试 ASR/OCR，或上传字幕/转写文本继续分析。",
                    "updated_at": now_utc(),
                }
            )
        loaded_tasks[task.id] = task
        if task.video_upload is not None:
            VIDEO_UPLOADS[task.video_upload.source_video.id] = task.video_upload
            replace_source(task.video_upload.source_video)

    loaded_options: dict[str, VideoExtractionRequest] = {}
    raw_options = payload.get("options", {})
    if isinstance(raw_options, dict):
        for task_id, value in raw_options.items():
            try:
                loaded_options[task_id] = VideoExtractionRequest.model_validate(value)
            except Exception:
                continue

    VIDEO_EXTRACTION_TASKS.update(loaded_tasks)
    VIDEO_EXTRACTION_OPTIONS.update(loaded_options)
    if loaded_tasks:
        persist_video_extraction_state()


def persist_link_diagnostics_state() -> None:
    path = link_diagnostics_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "records": [
            record.model_dump(mode="json") for record in LINK_DIAGNOSTICS[:100]
        ],
    }
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    tmp_path.replace(path)


def load_link_diagnostics_state() -> None:
    global LINK_DIAGNOSTICS_STATE_LOADED
    if LINK_DIAGNOSTICS_STATE_LOADED:
        return
    LINK_DIAGNOSTICS_STATE_LOADED = True
    path = link_diagnostics_path()
    if not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return

    loaded: list[LinkDiagnosticRecord] = []
    for raw_record in payload.get("records", []):
        try:
            loaded.append(LinkDiagnosticRecord.model_validate(raw_record))
        except Exception:
            continue
    loaded.sort(key=lambda record: record.created_at, reverse=True)
    LINK_DIAGNOSTICS[:] = loaded[:100]


def recommended_link_next_step(response: LinkTaskResponse) -> str:
    if response.parser_status == "completed" and response.video_upload:
        return "继续检查音频、关键帧和转写文本，确认是否可以进入结构分析。"
    if response.parser_error_code == "cookie_required":
        return "该链接需要有效抖音会话；系统会优先读取本机 Chrome Cookie，确认浏览器能正常打开后再试。"
    if response.parser_error_code == "downloader_missing":
        return "安装 yt-dlp 或配置 douyin-downloader 后重试。"
    if response.parser_error_code == "timeout":
        return "下载已自动续传仍超时；稍后重试，当前不会用标题或描述伪造稿件。"
    if response.parser_error_code == "transcript_quality":
        return "视频与语音稿已提取；检查待确认片段后，再进入写作结构拆解。"
    return "确认分享文案里包含完整短链后重试，并保留此链接作为后续诊断样本。"


def create_link_diagnostic_record(response: LinkTaskResponse) -> LinkDiagnosticRecord:
    return LinkDiagnosticRecord(
        id=new_id("diag"),
        url=response.source_video.url or "",
        source_video_id=response.source_video.id,
        parser_status=response.parser_status,
        parser_provider=response.parser_provider,
        parser_error_code=response.parser_error_code,
        parser_error_title=response.parser_error_title,
        parser_error_detail=response.parser_error_detail,
        parser_action_items=response.parser_action_items,
        fallback_inputs=response.fallback_inputs,
        output_dir=response.output_dir,
        downloaded_file_count=len(response.downloaded_files),
        has_video_upload=response.video_upload is not None,
        cookie_configured=has_douyin_cookie_config(),
        downloader_mode=douyin_downloader_mode(),
        recommended_next_step=recommended_link_next_step(response),
        message=response.message,
        created_at=now_utc(),
    )


def record_link_diagnostic(response: LinkTaskResponse) -> LinkDiagnosticRecord:
    load_link_diagnostics_state()
    record = create_link_diagnostic_record(response)
    with LINK_DIAGNOSTICS_LOCK:
        LINK_DIAGNOSTICS.insert(0, record)
        del LINK_DIAGNOSTICS[100:]
        persist_link_diagnostics_state()
    return record


def replace_link_diagnostic_records(records: list[LinkDiagnosticRecord]) -> None:
    if not records:
        return
    load_link_diagnostics_state()
    replacements = {record.id: record for record in records}
    with LINK_DIAGNOSTICS_LOCK:
        for index, record in enumerate(LINK_DIAGNOSTICS):
            if record.id in replacements:
                LINK_DIAGNOSTICS[index] = replacements[record.id]
        LINK_DIAGNOSTICS.sort(key=lambda record: record.created_at, reverse=True)
        persist_link_diagnostics_state()


def list_link_diagnostics(limit: int = 20) -> list[LinkDiagnosticRecord]:
    load_link_diagnostics_state()
    return LINK_DIAGNOSTICS[:limit]


def is_video_extraction_cancelled(task_id: str) -> bool:
    task = VIDEO_EXTRACTION_TASKS.get(task_id)
    return bool(task and (task.cancel_requested or task.status == "cancelled"))


def finish_cancelled_video_extraction_task(task_id: str) -> VideoExtractionTask:
    return update_video_extraction_task(
        task_id,
        status="cancelled",
        stage="后台提取已取消",
        progress=100,
        cancel_requested=True,
        next_step="任务已取消。可点击重试 ASR/OCR，或上传字幕/转写文本继续分析。",
        fallback_inputs=["上传字幕文件", "上传转写文本", "粘贴口播文案"],
    )


def update_video_extraction_task(
    task_id: str, **updates: object
) -> VideoExtractionTask:
    with VIDEO_EXTRACTION_LOCK:
        task = VIDEO_EXTRACTION_TASKS[task_id].model_copy(
            update={**updates, "updated_at": now_utc()}
        )
        VIDEO_EXTRACTION_TASKS[task_id] = task
        persist_video_extraction_state()
        return task


def process_video_extraction_task(task_id: str) -> None:
    load_video_extraction_state()
    task = VIDEO_EXTRACTION_TASKS[task_id]
    options = VIDEO_EXTRACTION_OPTIONS[task_id]
    upload = VIDEO_UPLOADS[task.source_video_id]
    try:
        if is_video_extraction_cancelled(task_id):
            finish_cancelled_video_extraction_task(task_id)
            return
        update_video_extraction_task(
            task_id, status="processing", stage="准备音频和关键帧", progress=12
        )
        material_path = (
            Path(upload.source_video.material_path)
            if upload.source_video.material_path
            else None
        )
        if material_path is None or not material_path.exists():
            raise FileNotFoundError("未找到已上传视频文件。")

        audio_path = Path(upload.audio_path) if upload.audio_path else None
        frames = [Path(path) for path in upload.frame_paths if Path(path).exists()]
        extraction_status = upload.extraction_status
        extraction_message = upload.message
        if audio_path is None or not audio_path.exists():
            extraction_status, audio_path, extraction_message = extract_audio(
                material_path, upload.source_video.id
            )
        if not frames:
            frame_status, frames, frame_message = extract_video_frames(
                material_path, upload.source_video.id
            )
            if extraction_status != "failed" and frame_status == "failed":
                extraction_status = "failed"
            extraction_message = f"{extraction_message} {frame_message}"

        if is_video_extraction_cancelled(task_id):
            finish_cancelled_video_extraction_task(task_id)
            return
        update_video_extraction_task(
            task_id,
            stage="FunASR 转写中" if options.run_asr else "跳过 FunASR",
            stage_detail=(
                asr_runtime_item().detail
                if options.run_asr
                else "本次任务未选择 ASR，不会加载 FunASR。"
            ),
            progress=35,
            audio_path=str(audio_path) if audio_path else None,
            frame_paths=[str(frame) for frame in frames],
        )
        asr = (
            transcribe_audio_isolated(audio_path)
            if options.run_asr
            else skipped_asr_message(enabled=False)
        )

        if is_video_extraction_cancelled(task_id):
            finish_cancelled_video_extraction_task(task_id)
            return
        update_video_extraction_task(
            task_id,
            stage="PaddleOCR 识别中" if options.run_ocr else "跳过 PaddleOCR",
            stage_detail=(
                ocr_runtime_item().detail
                if options.run_ocr
                else "本次任务未选择 OCR，不会加载 PaddleOCR。"
            ),
            progress=70,
            asr_status=asr.status,
            asr_message=asr.message,
        )
        ocr = (
            run_paddle_ocr_isolated(frames)
            if options.run_ocr
            else skipped_ocr_message(enabled=False, frames=frames)
        )

        if is_video_extraction_cancelled(task_id):
            finish_cancelled_video_extraction_task(task_id)
            return
        result = build_video_upload_from_extraction(
            upload=upload,
            audio_path=audio_path,
            frames=frames,
            extraction_status=extraction_status,
            extraction_message=extraction_message,
            asr=asr,
            ocr=ocr,
        )
        VIDEO_UPLOADS[result.source_video.id] = result
        replace_source(result.source_video)
        update_video_extraction_task(
            task_id,
            status="completed",
            stage="后台提取完成",
            progress=100,
            source_video=result.source_video,
            audio_path=result.audio_path,
            frame_paths=result.frame_paths,
            asr_status=result.asr_status,
            asr_message=result.asr_message,
            ocr_status=result.ocr_status,
            ocr_message=result.ocr_message,
            transcript=result.transcript,
            video_upload=result,
            next_step=result.next_step,
            fallback_inputs=result.fallback_inputs,
            media_cleanup_status=result.media_cleanup_status,
            media_cleanup_message=result.media_cleanup_message,
        )
    except Exception as exc:
        update_video_extraction_task(
            task_id,
            status="failed",
            stage="后台提取失败",
            progress=100,
            error=clean_text(str(exc))[:240],
            next_step="请上传字幕/转写文本，或手动粘贴口播文案继续分析。",
            fallback_inputs=["上传字幕文件", "上传转写文本", "粘贴口播文案"],
        )


def create_video_extraction_task(
    source_video_id: str,
    options: VideoExtractionRequest,
    retry_of: Optional[str] = None,
) -> VideoExtractionTask:
    load_video_extraction_state()
    if source_video_id not in VIDEO_UPLOADS:
        raise KeyError(source_video_id)
    with VIDEO_EXTRACTION_LOCK:
        for current in VIDEO_EXTRACTION_TASKS.values():
            if current.source_video_id == source_video_id and current.status in {
                "queued",
                "processing",
            }:
                return current
        upload = VIDEO_UPLOADS[source_video_id]
        task = VideoExtractionTask(
            id=new_id("extract"),
            source_video_id=source_video_id,
            status="queued",
            stage="等待后台提取",
            progress=0,
            source_video=upload.source_video,
            audio_path=upload.audio_path,
            frame_paths=upload.frame_paths,
            asr_status=upload.asr_status,
            asr_message=upload.asr_message,
            ocr_status=upload.ocr_status,
            ocr_message=upload.ocr_message,
            transcript=upload.transcript,
            video_upload=upload,
            retry_of=retry_of,
            run_asr=options.run_asr,
            run_ocr=options.run_ocr,
            stage_detail="后台任务已排队，上传文本兜底仍可继续使用。",
            next_step="后台任务已创建，可继续上传字幕/转写文本作为兜底。",
            fallback_inputs=["上传字幕文件", "上传转写文本", "粘贴口播文案"],
            media_cleanup_status=upload.media_cleanup_status,
            media_cleanup_message=upload.media_cleanup_message,
            created_at=now_utc(),
            updated_at=now_utc(),
        )
        VIDEO_EXTRACTION_TASKS[task.id] = task
        VIDEO_EXTRACTION_OPTIONS[task.id] = options
        persist_video_extraction_state()

    thread = threading.Thread(
        target=process_video_extraction_task, args=(task.id,), daemon=True
    )
    thread.start()
    return task


def get_video_extraction_task(task_id: str) -> VideoExtractionTask:
    load_video_extraction_state()
    if task_id not in VIDEO_EXTRACTION_TASKS:
        raise KeyError(task_id)
    return VIDEO_EXTRACTION_TASKS[task_id]


def list_video_extraction_tasks(limit: int = 20) -> list[VideoExtractionTask]:
    load_video_extraction_state()
    tasks = sorted(
        VIDEO_EXTRACTION_TASKS.values(), key=lambda task: task.updated_at, reverse=True
    )
    return tasks[: max(1, min(limit, 100))]


def cancel_video_extraction_task(task_id: str) -> VideoExtractionTask:
    load_video_extraction_state()
    if task_id not in VIDEO_EXTRACTION_TASKS:
        raise KeyError(task_id)
    task = VIDEO_EXTRACTION_TASKS[task_id]
    if task.status in {"completed", "failed", "cancelled"}:
        return task
    if task.status == "queued":
        return finish_cancelled_video_extraction_task(task_id)
    return update_video_extraction_task(
        task_id,
        cancel_requested=True,
        stage="正在取消后台提取",
        next_step="取消请求已提交；如果本机模型正在推理，会在当前阶段结束后停止。",
    )


def retry_video_extraction_task(task_id: str) -> VideoExtractionTask:
    load_video_extraction_state()
    if task_id not in VIDEO_EXTRACTION_TASKS:
        raise KeyError(task_id)
    task = VIDEO_EXTRACTION_TASKS[task_id]
    upload = task.video_upload or VIDEO_UPLOADS.get(task.source_video_id)
    if upload is None:
        raise KeyError(task.source_video_id)
    if upload.media_cleanup_status == "completed":
        raise ValueError(
            "转写已完成，原视频、音频和关键帧已按临时保存规则清理。请重新上传素材后再提取。"
        )
    VIDEO_UPLOADS[upload.source_video.id] = upload
    options = VIDEO_EXTRACTION_OPTIONS.get(task_id, VideoExtractionRequest())
    return create_video_extraction_task(
        upload.source_video.id, options, retry_of=task_id
    )


def create_video_upload_result(
    file_name: str,
    material_path: Path,
    run_extractors: bool = False,
    context_text: str = "",
    source_title: Optional[str] = None,
    source_url: Optional[str] = None,
    source_author: Optional[str] = None,
    source_publish_time: Optional[str] = None,
    source_created_at: Optional[datetime] = None,
) -> VideoUploadResponse:
    source = SourceVideo(
        id=new_id("source"),
        input_type="video",
        title=clean_text(source_title or "") or file_name,
        url=source_url,
        author=source_author,
        publish_time=source_publish_time,
        status="needs_upload",
        material_path=str(material_path),
        created_at=source_created_at or now_utc(),
    )
    extraction_status, audio_path, message = extract_audio(material_path, source.id)
    frame_status, frames, frame_message = extract_video_frames(material_path, source.id)
    context_terms, _ = extract_share_context_terms(context_text)
    if run_extractors:
        asr = transcribe_audio_isolated(
            audio_path if extraction_status == "completed" else None,
            hotwords=context_terms,
        )
        ocr = run_paddle_ocr_isolated(frames if frame_status == "completed" else [])
    else:
        asr = AsrTranscriptionResult(
            status="skipped",
            message=(
                "视频已完成保存和音频抽取；本次未启动 FunASR。"
                "如需真实转写，请点击启动 ASR/OCR，或上传字幕/转写文本继续分析。"
            ),
        )
        ocr = OcrExtractionResult(
            status="skipped",
            frame_paths=[str(frame) for frame in frames],
            message=(
                f"{frame_message} 本次未启动 PaddleOCR，避免首次模型下载阻塞上传。"
                "如需真实 OCR，请点击启动 ASR/OCR，或上传字幕/转写文本继续分析。"
            ),
        )
    if run_extractors and ocr.status == "skipped" and frame_message:
        ocr.message = f"{frame_message} {ocr.message}"
    merged_text, transcript_source = build_primary_transcript(asr.text, ocr.text)
    corrections: list[TranscriptCorrection] = []
    unresolved_fragments: list[str] = []
    quality_score = 0
    quality_message = "未生成足够稿件，无法执行自动校正。"
    if len(merged_text) >= 10:
        (
            merged_text,
            corrections,
            unresolved_fragments,
            quality_score,
            quality_message,
            context_terms,
        ) = correct_primary_transcript(merged_text, context_text, ocr.text)
    correction_status: Literal["completed", "needs_review", "skipped", "failed"] = (
        "needs_review"
        if unresolved_fragments
        else "completed"
        if len(merged_text) >= 10
        else "skipped"
    )
    transcript = (
        Transcript(
            id=new_id("transcript"),
            source_video_id=source.id,
            asr_text=asr.text,
            ocr_text=ocr.text,
            content_text=merged_text,
            timestamps=asr.timestamps,
            confidence=quality_score / 100,
            source=transcript_source,
        )
        if len(merged_text) >= 10
        else None
    )
    cleanup_status: Literal["retained", "completed", "failed"] = "retained"
    cleanup_message = "未生成足够文本，临时媒体保留以便重试或补充字幕。"
    if transcript is not None:
        source = source.model_copy(update={"status": "completed"})
        source, audio_path, frames, cleanup_status, cleanup_message = (
            cleanup_processed_media(source, audio_path, frames)
        )
    SOURCES.insert(0, source)
    next_step = (
        "ASR 已生成转写文本，可直接开始结构分析；也可以继续上传字幕或粘贴修正文案。"
        if transcript
        else (
            "视频素材已进入兜底池。继续上传字幕/转写文本，或粘贴口播文案进入结构分析；"
            "需要本机模型提取时再显式启动 ASR/OCR。"
        )
    )
    response = VideoUploadResponse(
        source_video=source,
        audio_path=str(audio_path) if audio_path else None,
        frame_paths=[str(frame) for frame in frames],
        extraction_status=extraction_status,
        asr_status=asr.status,
        asr_provider=asr.provider,
        asr_text=asr.text,
        ocr_status=ocr.status,
        ocr_provider=ocr.provider,
        ocr_text=ocr.text,
        transcript=transcript,
        correction_status=correction_status,
        corrections=corrections,
        unresolved_fragments=unresolved_fragments,
        transcript_quality_score=quality_score,
        transcript_quality_message=quality_message,
        context_terms=context_terms,
        message=message,
        asr_message=asr.message,
        ocr_message=ocr.message,
        next_step=next_step,
        fallback_inputs=["上传字幕文件", "上传转写文本", "粘贴口播文案"],
        media_cleanup_status=cleanup_status,
        media_cleanup_message=cleanup_message,
    )
    remember_video_upload(response)
    return response


def generate_hotspot(payload: GenerateHotspotRequest) -> GenerateHotspotResponse:
    bootstrap_templates()
    if not payload.template_id:
        raise ValueError("请先选择一个已保存的写作预设。")
    selected_template = pick_template_by_id(payload.template_id, payload.account_type)
    if not skill_is_routable(selected_template):
        raise ValueError("当前 Skill 仍是候选、暂停或退役状态，不能用于热点生成。")
    from app.workbench_llm import generate_hotspot_structured

    result = generate_hotspot_structured(
        hotspot=payload.hotspot,
        account_type=payload.account_type,
        duration_seconds=payload.duration_seconds,
        tone=payload.tone,
        goal=payload.goal,
        template_id=payload.template_id,
    )
    brief = result.brief.model_copy(update={"id": result.brief.id or new_id("hotspot")})
    scripts = [
        script.model_copy(
            update={
                "id": script.id or new_id("script"),
                "template_used": selected_template.name,
                "preset_application": script.preset_application
                or preset_application_summary(selected_template),
            }
        )
        for script in result.scripts
    ]
    GENERATED[:0] = scripts
    return GenerateHotspotResponse(
        brief=brief,
        matched_templates=result.matched_templates,
        scripts=scripts,
    )


def demo_analyses() -> list[ScriptAnalysis]:
    return [
        ScriptAnalysis(
            id="demo_analysis_public_response",
            source_video_id="demo_source_public_response",
            hook="你以为这只是一次普通回应吗？真正值得看的不是谁赢了，而是表达里的细节。",
            conflict="表面是明星回应，实际冲突是粉丝期待、路人观感和公开表达边界。",
            structure=[
                ScriptSegment(
                    name="爆点开场",
                    start="00:00",
                    duration="4s",
                    summary="用反问把用户注意力从热闹拉到细节。",
                ),
                ScriptSegment(
                    name="时间线整理",
                    start="00:04",
                    duration="12s",
                    summary="只复述公开节点，不补充未经证实信息。",
                ),
                ScriptSegment(
                    name="情绪对照",
                    start="00:16",
                    duration="14s",
                    summary="拆粉丝和路人的不同情绪来源。",
                ),
                ScriptSegment(
                    name="观点升维",
                    start="00:30",
                    duration="10s",
                    summary="把事件落到公开表达是否体面。",
                ),
                ScriptSegment(
                    name="评论引导",
                    start="00:40",
                    duration="5s",
                    summary="抛出态度问题，鼓励用户讨论。",
                ),
            ],
            emotion_curve=["惊讶", "怀疑", "代入", "判断", "互动"],
            reversal="大家争的不是一句回应，而是谁承担了沟通成本。",
            ending_cta="你觉得这次回应体面吗？评论区说说。",
            account_type="娱乐吃瓜号",
            reusable_template="公开回应反差拆解模板",
            template_suggestions=["反差开场", "公开时间线", "情绪对照", "态度升维"],
            content_angle="公开回应里的表达细节",
        ),
        ScriptAnalysis(
            id="demo_analysis_brand_crisis",
            source_video_id="demo_source_brand_crisis",
            hook="这不是一次普通热搜，而是品牌公关最怕的连锁反应。",
            conflict="品牌想快速止损，用户却在追问态度、责任和后续补救。",
            structure=[
                ScriptSegment(
                    name="事件一句话",
                    start="00:00",
                    duration="5s",
                    summary="先交代公开事实和争议对象。",
                ),
                ScriptSegment(
                    name="利益关系",
                    start="00:05",
                    duration="12s",
                    summary="解释品牌、代言和消费者情绪之间的关系。",
                ),
                ScriptSegment(
                    name="传播后果",
                    start="00:17",
                    duration="13s",
                    summary="拆评论区扩散点和二次传播风险。",
                ),
                ScriptSegment(
                    name="行业规律",
                    start="00:30",
                    duration="10s",
                    summary="把个案归纳成公关处理规律。",
                ),
                ScriptSegment(
                    name="风险提示",
                    start="00:40",
                    duration="5s",
                    summary="提醒不要做确定性商业判断。",
                ),
            ],
            emotion_curve=["理性", "信息增量", "判断", "风险意识"],
            reversal="用户真正关注的不是道歉文案，而是补救动作能不能落地。",
            ending_cta="这类事件你更看重态度，还是处理速度？",
            account_type="商业分析号",
            reusable_template="品牌危机背景拆解模板",
            template_suggestions=["事件一句话", "利益关系", "传播后果", "行业规律"],
            content_angle="品牌危机里的传播风险",
        ),
        ScriptAnalysis(
            id="demo_analysis_daily_debate",
            source_video_id="demo_source_daily_debate",
            hook="你以为大家是在吵对错，其实是在吵自己的生活经验。",
            conflict="同一个生活选择，在不同人群里会触发完全不同的价值判断。",
            structure=[
                ScriptSegment(
                    name="开头反问",
                    start="00:00",
                    duration="4s",
                    summary="提出一个常见误解。",
                ),
                ScriptSegment(
                    name="痛点放大",
                    start="00:04",
                    duration="10s",
                    summary="放大用户熟悉的生活矛盾。",
                ),
                ScriptSegment(
                    name="分步解释",
                    start="00:14",
                    duration="16s",
                    summary="分两类人群解释判断差异。",
                ),
                ScriptSegment(
                    name="结果展示",
                    start="00:30",
                    duration="9s",
                    summary="给出可复用观点结论。",
                ),
                ScriptSegment(
                    name="评论引导",
                    start="00:39",
                    duration="6s",
                    summary="把问题抛回用户经历。",
                ),
            ],
            emotion_curve=["疑问", "共鸣", "获得感", "轻互动"],
            reversal="争议不是因为信息少，而是每个人代入的处境不一样。",
            ending_cta="你遇到过这种情况吗？评论区聊聊。",
            account_type="泛娱乐观点号",
            reusable_template="生活争议问题解决模板",
            template_suggestions=["反问开头", "痛点放大", "人群拆解", "轻互动收尾"],
            content_angle="生活争议背后的人群处境",
        ),
    ]


def demo_generated_scripts() -> list[GeneratedScript]:
    bootstrap_templates()
    samples = [
        (
            "demo_script_public_response",
            "某明星公开回应后，粉丝和路人围绕态度产生争议",
            "娱乐吃瓜号",
            "tpl_reversal",
            1,
        ),
        (
            "demo_script_brand_crisis",
            "某品牌联名活动被质疑后引发评论区争议",
            "商业分析号",
            "tpl_context",
            3,
        ),
        (
            "demo_script_daily_debate",
            "年轻人对生活方式选择产生两极讨论",
            "泛娱乐观点号",
            "tpl_problem_solution",
            2,
        ),
    ]
    return [
        build_script(
            hotspot=hotspot,
            account_type=account_type,
            duration_seconds=45,
            tone="克制、有信息增量，不编造细节",
            goal="引发评论",
            template=pick_template_by_id(template_id, account_type),
            variant=variant,
        ).model_copy(update={"id": script_id})
        for script_id, hotspot, account_type, template_id, variant in samples
    ]


def overview() -> WorkbenchOverview:
    bootstrap_templates()
    fixtures_enabled = os.getenv("WORKBENCH_SKILL_EVAL_FIXTURES") == "1"
    if fixtures_enabled and not ANALYSES:
        ANALYSES.extend(demo_analyses())
    if fixtures_enabled and not GENERATED:
        GENERATED.extend(demo_generated_scripts())
    return WorkbenchOverview(
        tasks={
            "processing": 0,
            "queued": 0,
            "completed": len(ANALYSES),
            "failed": 0,
        },
        templates=deduplicate_templates(TEMPLATES)[:20],
        recent_analyses=ANALYSES[:5],
        generated_scripts=GENERATED[:5],
    )


def capabilities() -> WorkbenchCapabilities:
    ffmpeg_ready = shutil.which("ffmpeg") is not None
    media_ready = True
    media_detail = f"{media_root()} 可写，用于临时保存视频、音频和关键帧。"
    try:
        media_root().mkdir(parents=True, exist_ok=True)
        probe = media_root() / ".capability-check"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except Exception as exc:
        media_ready = False
        media_detail = f"{media_root()} 不可写：{clean_text(str(exc))[:120]}"
    funasr_ready = model_worker_python("funasr") is not None
    paddleocr_ready = model_worker_python("paddleocr") is not None
    litellm_ready = find_spec("litellm") is not None
    instructor_ready = find_spec("instructor") is not None
    douyin_ready = is_douyin_downloader_configured()
    items = [
        WorkbenchCapability(
            key="ffmpeg",
            label="FFmpeg",
            available=ffmpeg_ready,
            status="ready" if ffmpeg_ready else "missing",
            detail="用于抽音频、转码和后续视频预处理。",
        ),
        WorkbenchCapability(
            key="media_dir",
            label="媒体目录",
            available=media_ready,
            status="ready" if media_ready else "missing",
            detail=media_detail,
        ),
        WorkbenchCapability(
            key="funasr",
            label="FunASR",
            available=funasr_ready,
            status="ready" if funasr_ready else "reserved",
            detail=f"中文口播转写主选组件；当前 ASR 模式为 {asr_mode()}。",
        ),
        WorkbenchCapability(
            key="paddleocr",
            label="PaddleOCR",
            available=paddleocr_ready,
            status="ready" if paddleocr_ready else "reserved",
            detail=f"硬字幕和画面文字 OCR 主选组件；当前 OCR 模式为 {ocr_mode()}。",
        ),
        WorkbenchCapability(
            key="litellm",
            label="LiteLLM",
            available=litellm_ready,
            status="ready" if litellm_ready else "reserved",
            detail=f"模型调用网关；当前 LLM 模式为 {workbench_llm_mode()}。",
        ),
        WorkbenchCapability(
            key="instructor",
            label="Instructor",
            available=instructor_ready,
            status="ready" if instructor_ready else "reserved",
            detail="结构化 JSON 输出校验组件；未安装时使用本地 Pydantic fallback。",
        ),
        WorkbenchCapability(
            key="douyin_downloader",
            label="douyin-downloader",
            available=douyin_ready,
            status="ready" if douyin_ready else "reserved",
            detail=f"抖音公开链接免登录提取主路径；当前下载器模式为 {douyin_downloader_mode()}。",
        ),
    ]
    return WorkbenchCapabilities(
        items=items,
        ready_count=sum(1 for item in items if item.available),
        total_count=len(items),
    )
