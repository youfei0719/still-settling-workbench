import json
import io
import shutil
import subprocess
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from app import workbench_llm
from app.script_workbench import (
    SEED_TEMPLATES,
    CodexSkillPublishResponse,
    DraftRewriteRequest,
    DraftRewriteActivity,
    DraftRewriteTask,
    DRAFT_REWRITE_TASKS,
    FactSource,
    FactVerification,
    GeneratedScript,
    ScriptAnalysis,
    ScriptSegment,
    SkillEvaluationSummary,
    SkillEvidence,
    SkillGovernanceUpdateRequest,
    SkillReviewRecord,
    SourceVideo,
    SkillSourceRecord,
    PresetDraft,
    Transcript,
    WritingPresetCreateRequest,
    _operator_skill_name,
    _append_draft_rewrite_activity,
    apply_skill_governance,
    build_codex_skill_pack,
    build_preset_draft_from_analysis,
    create_writing_preset_from_draft,
    draft_rewrite_timeout_seconds,
    local_skill_library_path,
    publishable_skill_templates,
    publish_codex_skill_pack_to_github,
    read_local_skill_templates,
    rewrite_draft,
    risk_check,
    skill_promotion_errors,
    skill_promotion_readiness,
    upsert_local_skill_template,
    validate_codex_skill_pack_for_publish,
)
from app.workbench_llm import LLMCallStatus


def approved_skill(template, **updates):
    return template.model_copy(
        update={
            "status": "active",
            "source_count": 3,
            "evaluation_summary": SkillEvaluationSummary(
                routing_accuracy=0.9,
                no_match_accuracy=0.95,
                safety_block_rate=1,
                citation_coverage=1,
                human_score=4,
                minimum_dimension_score=4,
                passed=True,
            ),
            "reviews": [
                SkillReviewRecord(
                    reviewer="内容主审",
                    accuracy=4,
                    structure=4,
                    douyin_fit=4,
                    shootability=4,
                    distinctiveness=4,
                    approved=True,
                )
            ],
            **updates,
        }
    )


def test_saved_source_creates_structure_evidence_and_readiness_check(monkeypatch) -> None:
    from app import script_workbench

    monkeypatch.setattr(script_workbench, "bootstrap_templates", lambda: None)
    monkeypatch.setattr(script_workbench, "TEMPLATES", [])
    draft = PresetDraft(
        id="draft-evidence",
        source_analysis_id="analysis-evidence",
        source_video_id="source-evidence",
        source_title="授权结构样本",
        source_url="https://v.douyin.com/evidence/",
        source_transcript="这是一段经过授权、可以用于拆解结构的口播文本。",
        name="测试结构 Skill",
        account_type="观点号",
        hotspot_types=["反差切入"],
        match_signals=["先给冲突"],
        skeleton=["钩子", "解释", "收束"],
        hook_formula="先给冲突。",
        emotion_rhythm="疑问 -> 判断",
        ending_formula="收束观点。",
        risk_boundary="只迁移结构。",
        created_at=datetime.now(timezone.utc),
    )

    template = create_writing_preset_from_draft(
        WritingPresetCreateRequest(preset_draft=draft), existing_skills=[]
    )
    readiness = skill_promotion_readiness(template.model_copy(update={"evidence": []}))

    assert template.evidence[0].scope == "structure"
    assert template.evidence[0].source_url == "https://v.douyin.com/evidence/"
    assert readiness.has_structure_evidence is True
    assert "缺少可追溯来源证据。" not in readiness.blockers
    assert "至少需要 3 个授权来源案例。" in readiness.blockers


def test_saved_source_can_be_assigned_to_a_selected_candidate(monkeypatch) -> None:
    from app import script_workbench

    monkeypatch.setattr(script_workbench, "bootstrap_templates", lambda: None)
    candidate = SEED_TEMPLATES[0].model_copy(
        update={"id": "chosen-candidate", "source_count": 1, "sources": []}
    )
    draft = PresetDraft(
        id="draft-chosen-candidate",
        source_analysis_id="analysis-chosen-candidate",
        source_video_id="source-chosen-candidate",
        source_title="第二个授权结构样本",
        source_url="https://v.douyin.com/chosen-candidate/",
        source_transcript="授权样本用于补充同一写法的第二个结构证据。",
        name="不应按名称自动决定归属",
        account_type="观点号",
        hotspot_types=["反差切入"],
        match_signals=["先给冲突"],
        skeleton=["钩子", "解释", "收束"],
        hook_formula="先给冲突。",
        emotion_rhythm="疑问 -> 判断",
        ending_formula="收束观点。",
        risk_boundary="只迁移结构。",
        created_at=datetime.now(timezone.utc),
    )

    saved = create_writing_preset_from_draft(
        WritingPresetCreateRequest(
            preset_draft=draft, merge_target_id=candidate.id
        ),
        existing_skills=[candidate],
    )

    assert saved.id == candidate.id
    assert saved.source_count == 2
    assert [source.source_video_id for source in saved.sources] == [
        "source-chosen-candidate"
    ]


def test_saved_source_can_force_a_new_candidate_instead_of_auto_merge(monkeypatch) -> None:
    from app import script_workbench

    monkeypatch.setattr(script_workbench, "bootstrap_templates", lambda: None)
    candidate = SEED_TEMPLATES[0].model_copy(
        update={"id": "similar-candidate", "source_count": 1, "sources": []}
    )
    draft = PresetDraft(
        id="draft-force-new",
        source_analysis_id="analysis-force-new",
        source_video_id="source-force-new",
        source_title="同结构但独立沉淀的授权样本",
        source_url="https://v.douyin.com/force-new/",
        source_transcript="这是另一套需要单独管理的授权结构样本。",
        name="独立候选 Skill",
        account_type="观点号",
        hotspot_types=["反差切入"],
        match_signals=["先给冲突"],
        skeleton=["钩子", "解释", "收束"],
        hook_formula="先给冲突。",
        emotion_rhythm="疑问 -> 判断",
        ending_formula="收束观点。",
        risk_boundary="只迁移结构。",
        similar_skill_id=candidate.id,
        created_at=datetime.now(timezone.utc),
    )

    saved = create_writing_preset_from_draft(
        WritingPresetCreateRequest(preset_draft=draft, merge_as_new=True),
        existing_skills=[candidate],
    )

    assert saved.id != candidate.id
    assert saved.status == "candidate"
    assert saved.source_count == 1


def test_promotion_errors_distinguish_unrun_and_failed_evaluation() -> None:
    unrun = SEED_TEMPLATES[0]
    evaluated_but_failed = unrun.model_copy(
        update={
            "evaluation_summary": SkillEvaluationSummary(
                evaluated_at=datetime.now(timezone.utc), passed=False
            )
        }
    )

    assert "真实模型发布评测尚未运行。" in skill_promotion_errors(unrun)
    assert "真实模型发布评测未达到发布门槛。" in skill_promotion_errors(
        evaluated_but_failed
    )


def write_release_report(tmp_path, monkeypatch, *skills):
    """Create a required-mode report fixture, mirroring the publish API contract."""
    monkeypatch.setattr("app.script_workbench.skill_release_report_root", lambda: tmp_path)
    report = {
        "generated_at": "2026-07-31T12:00:00+00:00",
        "passed": True,
        "model_mode": "required",
        "model": "openai/test-release-model",
        "skill_results": [
            {
                "template_id": skill.id,
                "passed": True,
                "metrics": {
                    "routing_accuracy": 0.90,
                    "no_match_accuracy": 0.95,
                    "safety_block_rate": 1.0,
                    "citation_coverage": 1.0,
                    "human_score": 4.2,
                    "minimum_dimension_score": 3.5,
                },
            }
            for skill in skills
        ],
    }
    path = tmp_path / "skill-release-report.json"
    path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    return str(path)


def test_skill_governance_requires_release_evidence_before_activation(tmp_path, monkeypatch) -> None:
    candidate = SEED_TEMPLATES[0].model_copy(
        update={
            "source_titles": ["A", "B", "C"],
            "source_count": 3,
            "evidence": [
                SkillEvidence(
                    claim="该结构可复用", source_title="来源 A", source_url="https://example.com/a"
                )
            ],
        }
    )
    blocked = SkillGovernanceUpdateRequest(status="active")
    try:
        apply_skill_governance(candidate, blocked)
    except ValueError as exc:
        assert "发布评测报告" in str(exc)
    else:
        raise AssertionError("candidate without evaluation must not activate")

    report_path = write_release_report(tmp_path, monkeypatch, candidate)
    approved = apply_skill_governance(
        candidate,
        SkillGovernanceUpdateRequest(
            status="active",
            release_report_path=report_path,
            review=SkillReviewRecord(
                accuracy=4,
                structure=4,
                douyin_fit=4,
                shootability=4,
                distinctiveness=4,
                approved=True,
            ),
        ),
    )
    assert approved.status == "active"
    assert approved.version == 1


def test_skill_governance_records_main_review_while_candidate() -> None:
    candidate = SEED_TEMPLATES[0]
    reviewed = apply_skill_governance(
        candidate,
        SkillGovernanceUpdateRequest(
            status="candidate",
            review=SkillReviewRecord(
                reviewer="内容主审",
                accuracy=4,
                structure=4,
                douyin_fit=4,
                shootability=4,
                distinctiveness=4,
                approved=True,
                note="主审确认候选结构可复用。",
            ),
        ),
    )

    assert reviewed.status == "candidate"
    assert len(reviewed.reviews) == len(candidate.reviews) + 1
    assert reviewed.reviews[-1].approved is True


def test_approve_and_publish_persists_only_after_github_publish(monkeypatch) -> None:
    from app.api.routes import script_workbench as routes

    candidate = SEED_TEMPLATES[0].model_copy(update={"source_count": 3})
    activated = approved_skill(candidate)
    published = CodexSkillPublishResponse(
        status="published",
        repository="example-org/douyin-writing-skills",
        url="https://github.com/example-org/douyin-writing-skills",
        branch="main",
        version="test-version",
        message="已推送",
    )
    persisted: list[str] = []
    monkeypatch.setattr(
        routes,
        "persisted_overview_or_fallback",
        lambda: SimpleNamespace(templates=[candidate]),
    )
    monkeypatch.setattr(routes, "skill_promotion_errors", lambda _: [])
    monkeypatch.setattr(
        routes,
        "run_skill_release_evaluation",
        lambda: SimpleNamespace(passed=True, report_path="skill-release-report.json"),
    )
    monkeypatch.setattr(routes, "apply_skill_governance", lambda *_: activated)
    monkeypatch.setattr(routes, "publishable_skill_templates", lambda items: items)
    monkeypatch.setattr(routes, "build_codex_skill_pack", lambda _: object())
    monkeypatch.setattr(
        routes, "publish_codex_skill_pack_to_github", lambda _: published
    )
    monkeypatch.setattr(routes, "optional_database_session", lambda: nullcontext(None))
    monkeypatch.setattr(
        routes,
        "update_skill_governance",
        lambda template_id, _: persisted.append(template_id),
    )
    monkeypatch.setattr(
        routes, "upsert_local_skill_template", lambda template: persisted.append(template.id)
    )

    result = routes.approve_and_publish_writing_skill(
        candidate.id,
        SkillGovernanceUpdateRequest(
            status="active",
            review=SkillReviewRecord(
                accuracy=4,
                structure=4,
                douyin_fit=4,
                shootability=4,
                distinctiveness=4,
                approved=True,
            ),
        ),
    )

    assert result.skill.status == "active"
    assert result.publish.status == "published"
    assert persisted == [candidate.id, candidate.id]


def test_headless_codex_disables_plugins_but_keeps_browser_search(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    class FakePopen:
        def __init__(self, command, **kwargs):
            captured["command"] = command
            output_path = Path(command[command.index("--output-last-message") + 1])
            output_path.write_text(
                json.dumps(
                    {
                        "replacement": "替换后的口播文字。",
                        "change_summary": "让表达更具体。",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            self.stdin = io.StringIO()
            self.stdout = io.StringIO(
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {"type": "web_search", "query": "作者 讣告"},
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            self.stderr = io.StringIO()

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

        def kill(self):
            return None

    monkeypatch.setattr(workbench_llm.shutil, "which", lambda _: "/usr/bin/codex")
    monkeypatch.setattr(workbench_llm.subprocess, "Popen", FakePopen)
    config = workbench_llm.LLMRuntimeConfig(
        mode="optional",
        model="openai/test-model",
        api_base="https://example.com/v1",
    )

    activities = []
    result = workbench_llm.codex_cli_structured_completion(
        workbench_llm.StructuredSelectionRewriteOutput,
        [{"role": "user", "content": "改写这句话"}],
        config,
        "test-key",
        allow_web_search=True,
        activity_callback=activities.append,
        activity_phase="research",
    )

    command = captured["command"]
    assert isinstance(command, list)
    assert command[command.index("--disable") + 1] == "plugins"
    assert command[command.index("--enable") + 1] == "browser_use"
    assert "--json" in command
    assert activities[0]["kind"] == "search"
    assert activities[0]["detail"] == "作者 讣告"
    assert result.replacement == "替换后的口播文字。"


def test_codex_process_timeout_returns_stage_friendly_error(monkeypatch) -> None:
    class HangingPopen:
        def __init__(self, command, **kwargs):
            self.stdin = io.StringIO()
            self.stdout = io.StringIO()
            self.stderr = io.StringIO()
            self.returncode = None

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            self.returncode = -9
            return self.returncode

        def kill(self):
            self.returncode = -9

    clock = iter([0.0, 181.0, 181.0])

    monkeypatch.setattr(workbench_llm.shutil, "which", lambda _: "/usr/bin/codex")
    monkeypatch.setattr(workbench_llm.subprocess, "Popen", HangingPopen)
    monkeypatch.setattr(workbench_llm.time, "monotonic", lambda: next(clock))
    config = workbench_llm.LLMRuntimeConfig(
        mode="optional",
        model="openai/test-model",
        api_base="https://example.com/v1",
    )

    try:
        workbench_llm.codex_cli_structured_completion(
            workbench_llm.StructuredSelectionRewriteOutput,
            [{"role": "user", "content": "改写这句话"}],
            config,
            "test-key",
        )
    except RuntimeError as exc:
        assert str(exc) == "Codex 在 180 秒内未完成当前阶段。"
    else:
        raise AssertionError("expected Codex timeout to raise RuntimeError")


def test_draft_task_budget_covers_single_research_and_writing_workflow(
    monkeypatch,
) -> None:
    monkeypatch.setenv("WORKBENCH_LLM_TIMEOUT_SECONDS", "60")
    assert draft_rewrite_timeout_seconds() == 240


def test_skill_draft_prompt_requires_reusable_structure_not_source_summary(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_completion(response_model, messages, config):
        captured["messages"] = messages
        return workbench_llm.StructuredSkillDraftOutput(
            name="细节反差递进",
            solves_problems=["开头缺少结构抓力", "中段只有事实堆叠"],
            match_signals=["宏大主题", "普通人细节", "认知反差", "结尾升维"],
            writing_tasks=["细节切入", "反差递进", "观点收束"],
            applicable_scenes=[
                "人物故事：用细节承接人物命运变化",
                "品牌故事：用小动作解释品牌长期投入",
                "作品解读：用场景细节带出主题判断",
                "社会现象：用普通人视角解释宏观变化",
                "职场故事：用具体选择承接价值判断",
            ],
            unsuitable_scenes=["纯信息播报", "事实未确认爆料"],
            skeleton=["微小细节", "认知反差", "背景补足", "情绪递进", "观点收束"],
            hook_formula="先用一个反常识细节打开主题。",
            emotion_rhythm="疑问 -> 不安 -> 理解 -> 判断",
            ending_formula="回到一个可讨论的问题。",
            risk_boundary="只抽象结构，不复述来源事件。",
            borrowable_moves=[
                "用微小细节承接宏大命题",
                "先压低认知，再用细节完成翻转",
                "把公共事实转成普通人能感知的情绪入口",
            ],
        )

    monkeypatch.setenv("WORKBENCH_LLM_MODE", "optional")
    monkeypatch.setattr(workbench_llm, "structured_completion", fake_completion)
    transcript = Transcript(
        id="transcript_prompt",
        source_video_id="source_prompt",
        content_text="这是一个来源视频稿件，用来验证提示词不会沉淀成一次性总结。",
        source="asr",
    )
    analysis = ScriptAnalysis(
        id="analysis_prompt",
        source_video_id="source_prompt",
        hook="用一个小细节切入宏大事件。",
        conflict="中段从细节推进到背景，再回到普通人感受。",
        structure=[
          ScriptSegment(name="细节切入", start="0s", duration="5s", summary="先给细节"),
          ScriptSegment(name="背景解释", start="5s", duration="20s", summary="解释背景"),
          ScriptSegment(name="观点收束", start="25s", duration="10s", summary="回到判断"),
        ],
        emotion_curve=["好奇", "不安", "理解", "判断"],
        reversal="从宏大叙事落到个人感受。",
        ending_cta="你怎么看这种写法？",
        account_type="泛娱乐观点号",
        reusable_template="细节反差结构",
        template_suggestions=["细节切入", "反差递进"],
        content_angle="结构抽象",
    )

    output = workbench_llm.extract_skill_draft_structured(
        "来源视频标题", transcript, analysis
    )

    assert output is not None
    prompt_text = "\n".join(
        str(message["content"]) for message in captured["messages"]  # type: ignore[index]
    )
    assert "不得复述来源视频主题、人物、事件、标题或价值观" in prompt_text
    assert "长期可复用结构能力" in prompt_text
    assert "可迁移写法动作" in prompt_text
    assert "不得写电商、职场、品牌、客服、作品等具体领域" in prompt_text


def test_skill_draft_converts_topical_applicable_scenes_to_structure_conditions(
    monkeypatch,
) -> None:
    def fake_skill_draft(*args, **kwargs):
        return workbench_llm.StructuredSkillDraftOutput(
            name="结果反转收束",
            solves_problems=["开头缺少抓力", "原因解释太平"],
            match_signals=["结果先行", "原因后置", "有反差", "缺少收束"],
            writing_tasks=["结果钩子", "反差解释", "观点收束"],
            applicable_scenes=[
                "电商售后与退换货争议：有明确结果，适合先抛判定再补过程",
                "职场审批与绩效争议：目标被流程卡住，适合写成权限冲突",
                "品牌客服补偿事件：先给赔付结果，再交代沟通失败过程",
                "合作对账与合同纠纷：先亮出结算结果，再倒叙谈判拉扯",
                "已有明确结果，但缺少解释路径，需要先给结果再拆原因",
            ],
            unsuitable_scenes=["纯知识科普", "没有冲突和结果反转"],
            skeleton=["结果先行", "倒叙补因", "冲突推进", "观点收束"],
            hook_formula="先给最终结果，再反问为什么会这样。",
            emotion_rhythm="疑问 -> 反差 -> 理解 -> 判断",
            ending_formula="把争议收束成一个可回答的问题。",
            risk_boundary="只抽象结构，不复述来源事件。",
            borrowable_moves=[
                "结果先行，把最强信息放在开头",
                "用倒叙补齐原因，避免平铺直叙",
                "把个人遭遇写成规则或流程冲突",
            ],
        )

    monkeypatch.setattr(workbench_llm, "extract_skill_draft_structured", fake_skill_draft)
    source = SourceVideo(
        id="source_topical",
        input_type="video",
        title="具体来源视频标题",
        status="completed",
        created_at=datetime.now(timezone.utc),
    )
    transcript = Transcript(
        id="transcript_topical",
        source_video_id=source.id,
        content_text="具体来源视频稿件内容。",
        source="asr",
    )
    analysis = ScriptAnalysis(
        id="analysis_topical",
        source_video_id=source.id,
        hook="先给最终结果。",
        conflict="用倒叙解释原因。",
        structure=[
            ScriptSegment(name="结果先行", start="0s", duration="5s", summary="先给结果"),
            ScriptSegment(name="倒叙补因", start="5s", duration="20s", summary="解释原因"),
            ScriptSegment(name="观点收束", start="25s", duration="10s", summary="回到判断"),
        ],
        emotion_curve=["疑问", "反差", "判断"],
        reversal="从结果回到原因。",
        ending_cta="你怎么看？",
        account_type="泛娱乐观点号",
        reusable_template="结果反差结构",
        template_suggestions=[],
        content_angle="结构抽象",
    )

    draft = build_preset_draft_from_analysis(
        source, transcript, analysis, existing_skills=[]
    )

    joined = " ".join(draft.applicable_scenes)
    assert "电商" not in joined
    assert "职场" not in joined
    assert "品牌客服" not in joined
    assert any("已有明确事实或结论" in item for item in draft.applicable_scenes)
    assert any("表面结果和真实原因存在错位" in item for item in draft.applicable_scenes)


def test_fallback_skill_draft_uses_abstract_borrowable_moves(monkeypatch) -> None:
    monkeypatch.setattr(
        workbench_llm, "extract_skill_draft_structured", lambda *args, **kwargs: None
    )
    source = SourceVideo(
        id="source_fallback",
        input_type="video",
        title="某个具体来源视频标题",
        status="completed",
        created_at=datetime.now(timezone.utc),
    )
    transcript = Transcript(
        id="transcript_fallback",
        source_video_id=source.id,
        content_text="具体来源视频稿件内容。",
        source="asr",
    )
    analysis = ScriptAnalysis(
        id="analysis_fallback",
        source_video_id=source.id,
        hook="先抛出一个小细节。",
        conflict="从细节转入背景冲突。",
        structure=[
            ScriptSegment(name="细节切入", start="0s", duration="5s", summary="先给细节"),
            ScriptSegment(name="背景解释", start="5s", duration="20s", summary="解释背景"),
            ScriptSegment(name="观点收束", start="25s", duration="10s", summary="回到判断"),
        ],
        emotion_curve=["好奇", "共鸣", "判断"],
        reversal="从个案转为结构判断。",
        ending_cta="你怎么看？",
        account_type="泛娱乐观点号",
        reusable_template="细节反差结构",
        template_suggestions=[],
        content_angle="结构抽象",
    )

    draft = build_preset_draft_from_analysis(
        source, transcript, analysis, existing_skills=[]
    )

    assert any("用微小细节承接宏大命题" in move for move in draft.borrowable_moves)
    assert "先给公开信息，再推进评论区争议和人群情绪。" not in draft.borrowable_moves


def test_codex_skill_pack_exports_latest_active_router_package(tmp_path, monkeypatch) -> None:
    active = approved_skill(
        SEED_TEMPLATES[0],
        **{
            "id": "active-skill-001",
            "name": "命题钩子群例递进",
            "disabled_reason": None,
            "source_titles": ["来源视频 A", "来源视频 B", "来源视频 C"],
            "source_count": 3,
        }
    )
    disabled = SEED_TEMPLATES[1].model_copy(
        update={
            "id": "disabled-skill-002",
            "name": "停用写法",
            "disabled_reason": "复盘后不再适用",
            "source_count": 9,
        }
    )
    report_path = write_release_report(tmp_path, monkeypatch, active)
    active = active.model_copy(
        update={"evaluation_summary": active.evaluation_summary.model_copy(update={"report_path": report_path})}
    )

    skill_pack = build_codex_skill_pack([active, disabled])

    assert skill_pack.skill_name == "douyin-writing-skills"
    assert skill_pack.active_skill_count == 1
    assert skill_pack.total_skill_count == 2
    assert skill_pack.source_count == 3
    assert skill_pack.sync_contract == "/api/v1/script-workbench/codex-skill-pack"
    assert "SKILL.md" in skill_pack.files
    assert "references/skills.json" in skill_pack.files
    assert "references/research-playbook.md" in skill_pack.files
    assert skill_pack.install_manifest["runtime_contract"] == "SKILL.md + references/skills.json"

    manifest = json.loads(skill_pack.files["references/skills.json"])
    assert manifest["version"] == skill_pack.version
    assert manifest["sync_policy"].startswith("每次使用前读取最新版")
    assert manifest["research_rule"].startswith("先判断是否需要联网核验")
    assert "微博、抖音、小红书" in manifest["platform_source_rule"]
    assert manifest["evidence_policy"].startswith("事实型输出优先使用")
    assert "verified_facts" in manifest["research_brief_schema"]
    assert manifest["interaction_rule"].startswith("除非用户明确要求自动选择")
    assert [skill["id"] for skill in manifest["skills"]] == ["active-skill-001"]
    assert manifest["skills"][0]["source_count"] == 3
    assert manifest["skills"][0]["created_at"] == active.created_at.isoformat()
    assert "research_needs" in manifest["skills"][0]
    assert any("平台语境" in item for item in manifest["skills"][0]["research_needs"])
    assert "choose_when" in manifest["skills"][0]
    assert "writing_method" in manifest["skills"][0]
    reference_file = manifest["skills"][0]["reference_file"]
    assert reference_file.startswith("references/skills/")
    assert reference_file in skill_pack.files
    assert "## Evidence Tiers" in skill_pack.files["references/research-playbook.md"]
    assert "候选 Skill" in skill_pack.files["references/research-playbook.md"]

    changed = active.model_copy(update={"hook_formula": "改版后的开头方法"})
    changed_pack = build_codex_skill_pack([changed, disabled])
    assert changed_pack.version != skill_pack.version

    legacy_source_time = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)
    legacy = active.model_copy(
        update={
            "id": "legacy-skill-001",
            "created_at": None,
            "sources": [
                SkillSourceRecord(
                    source_video_id="source-legacy",
                    title="历史来源视频",
                    recognized_at=legacy_source_time,
                )
            ],
        }
    )
    legacy_report_path = write_release_report(tmp_path, monkeypatch, legacy)
    legacy = legacy.model_copy(
        update={"evaluation_summary": legacy.evaluation_summary.model_copy(update={"report_path": legacy_report_path})}
    )
    legacy_pack = build_codex_skill_pack([legacy])
    legacy_manifest = json.loads(legacy_pack.files["references/skills.json"])
    assert legacy_manifest["skills"][0]["created_at"] == legacy_source_time.isoformat()


def test_publish_validation_blocks_seed_only_skill_pack() -> None:
    seed_only_pack = build_codex_skill_pack(SEED_TEMPLATES)
    seed_manifest = json.loads(seed_only_pack.files["references/skills.json"])

    assert seed_manifest["skills"] == []

    try:
        validate_codex_skill_pack_for_publish(seed_only_pack)
    except RuntimeError as exc:
        assert "没有可发布的真实 Skill" in str(exc)
    else:
        raise AssertionError("expected seed-only pack to be blocked")


def test_local_skill_library_persists_source_backed_skill(
    tmp_path,
    monkeypatch,
) -> None:
    library_path = tmp_path / "writing-skills.json"
    monkeypatch.setenv("WORKBENCH_SKILL_LIBRARY_PATH", str(library_path))
    added_at = datetime(2026, 7, 31, 9, 30, tzinfo=timezone.utc)
    saved_skill = SEED_TEMPLATES[0].model_copy(
        update={
            "id": "local-skill-001",
            "name": "细节入口·观点收束",
            "source_titles": ["真实来源视频 A", "真实来源视频 B", "真实来源视频 C"],
            "sources": [
                SkillSourceRecord(
                    source_video_id="source-local",
                    source_analysis_id="analysis-local",
                    title="真实来源视频",
                    author="原视频作者",
                    url="https://v.douyin.com/example/",
                    transcript="这是从原视频提取出来的真实文稿。",
                    recognized_at=added_at,
                )
            ],
            "source_count": 1,
            "created_at": added_at,
        }
    )

    upsert_local_skill_template(saved_skill)

    assert local_skill_library_path() == library_path.resolve()
    persisted = read_local_skill_templates()
    assert [template.id for template in persisted] == ["local-skill-001"]
    assert persisted[0].sources[0].author == "原视频作者"
    assert persisted[0].sources[0].transcript == "这是从原视频提取出来的真实文稿。"


def test_publishable_skill_templates_excludes_seed_fallback(tmp_path, monkeypatch) -> None:
    real_skill = approved_skill(
        SEED_TEMPLATES[0],
        **{
            "id": "real-skill-001",
            "name": "真实沉淀 Skill",
            "source_titles": ["真实来源视频 A", "真实来源视频 B", "真实来源视频 C"],
            "source_count": 3,
        }
    )

    report_path = write_release_report(tmp_path, monkeypatch, real_skill)
    real_skill = real_skill.model_copy(
        update={"evaluation_summary": real_skill.evaluation_summary.model_copy(update={"report_path": report_path})}
    )
    publishable = publishable_skill_templates([*SEED_TEMPLATES, real_skill])
    skill_pack = build_codex_skill_pack(publishable)
    manifest = json.loads(skill_pack.files["references/skills.json"])

    assert [template.id for template in publishable] == ["real-skill-001"]
    assert [skill["id"] for skill in manifest["skills"]] == ["real-skill-001"]
    assert skill_pack.source_count == 3


def test_skill_governance_rejects_illegal_lifecycle_transitions() -> None:
    active = approved_skill(SEED_TEMPLATES[0])
    try:
        apply_skill_governance(active, SkillGovernanceUpdateRequest(status="candidate"))
    except ValueError as exc:
        assert "不能转换" in str(exc)
    else:
        raise AssertionError("active Skill must not return to candidate")

    retired = active.model_copy(update={"status": "retired"})
    try:
        apply_skill_governance(retired, SkillGovernanceUpdateRequest(status="active"))
    except ValueError as exc:
        assert "不能转换" in str(exc)
    else:
        raise AssertionError("retired Skill must not return to active")


def test_publisher_builds_and_pushes_only_a_versioned_runtime(tmp_path, monkeypatch) -> None:
    skill_source = Path(__file__).resolve().parents[3] / "douyin-writing-skills"
    distribution = tmp_path / "douyin-writing-skills"
    shutil.copytree(skill_source, distribution, ignore=shutil.ignore_patterns(".git", "__pycache__"))
    subprocess.run(["git", "init", "-b", "main"], cwd=distribution, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=distribution, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "initial"],
        cwd=distribution,
        check=True,
        capture_output=True,
    )
    bare_remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(bare_remote)], check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", str(bare_remote)], cwd=distribution, check=True, capture_output=True)
    subprocess.run(["git", "push", "-u", "origin", "main"], cwd=distribution, check=True, capture_output=True)

    skill = approved_skill(
        SEED_TEMPLATES[0],
        id="publisher-skill-001",
        name="发布链路测试 Skill",
        source_count=3,
        source_titles=["来源 A", "来源 B", "来源 C"],
    )
    report_path = write_release_report(tmp_path, monkeypatch, skill)
    skill = skill.model_copy(
        update={"evaluation_summary": skill.evaluation_summary.model_copy(update={"report_path": report_path})}
    )
    pack = build_codex_skill_pack([skill])
    monkeypatch.setenv("DOUYIN_WRITING_SKILLS_REPO", str(distribution))
    monkeypatch.setenv("DOUYIN_WRITING_SKILLS_REMOTE", "origin")
    monkeypatch.setenv("DOUYIN_WRITING_SKILLS_BRANCH", "main")
    monkeypatch.setenv("DOUYIN_WRITING_SKILLS_REMOTE_URL", str(bare_remote))

    published = publish_codex_skill_pack_to_github(pack)
    assert published.status == "published"
    assert published.commit_sha
    assert (distribution / "published" / "packages" / pack.version / "runtime" / "SKILL.md").is_file()
    assert (distribution / "published" / "stable" / "manifest.json").is_file()
    assert (distribution / "SKILL.md").read_text(encoding="utf-8").startswith("---")
    assert publish_codex_skill_pack_to_github(pack).status == "unchanged"


def test_publish_validation_blocks_empty_skill_pack() -> None:
    empty_pack = build_codex_skill_pack([])

    try:
        validate_codex_skill_pack_for_publish(empty_pack)
    except RuntimeError as exc:
        assert "没有可发布的真实 Skill" in str(exc)
    else:
        raise AssertionError("expected empty pack to be blocked")


def test_recommended_draft_selects_skill_and_writes_in_one_completion(
    monkeypatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_completion(response_model, messages, config, **kwargs):
        calls.append({"response_model": response_model, "kwargs": kwargs})
        return workbench_llm.StructuredRecommendedDraftOutput(
            matches=[
                workbench_llm.StructuredSkillChoice(
                    skill_id=SEED_TEMPLATES[0].id,
                    match_score=92,
                    reason="适合从人物选择推进到共同判断。",
                    apply_plan=["反差开场", "证据递进", "判断收束"],
                )
            ],
            draft=workbench_llm.StructuredRewriteVariant(
                content_angle="人物选择",
                positioning="适合继续精修成一条完整观点口播",
                difference_from_others="推荐稿从一个具体选择切入",
                title="人物选择初稿",
                spoken_script=("从一个具体选择开始推进。\n\n" * 8).strip(),
                shot_suggestions=["正面口播", "补充来源画面"],
                subtitle_rhythm=["短句开场", "结论单独成行"],
                comment_cta="哪一个选择最让你记住？",
                skill_application=["使用反差钩子", "按证据递进"],
                skill_coverage=[
                    workbench_llm.StructuredSkillCoverage(
                        step="反差开场", evidence="首句提出中心冲突"
                    ),
                    workbench_llm.StructuredSkillCoverage(
                        step="证据递进", evidence="中段逐层补充材料"
                    ),
                    workbench_llm.StructuredSkillCoverage(
                        step="判断收束", evidence="结尾回到共同判断"
                    ),
                ],
            ),
        )

    monkeypatch.setenv("WORKBENCH_LLM_MODE", "optional")
    monkeypatch.setattr(workbench_llm, "structured_completion", fake_completion)
    payload = DraftRewriteRequest(
        title="某作者去世",
        content="我想从人物选择切入做一条缅怀视频。",
        input_type="hotspot",
        account_type="泛娱乐观点号",
        duration_seconds=60,
        tone="克制",
        goal="引发评论",
    )
    diagnosis = workbench_llm.DraftDiagnosis(
        id="diagnosis_workflow",
        draft_title=payload.title,
        draft_type=payload.input_type,
        strengths=["意图明确"],
        problems=["缺少可口播段落"],
        rewrite_goals=["补足人物选择与情绪因果"],
        suggested_skill_types=["反差开场"],
        no_go_zones=["不编造事实"],
    )

    matches, scripts, status = (
        workbench_llm.select_skill_and_generate_recommended_draft_structured(
            payload,
            diagnosis,
            [SEED_TEMPLATES[0]],
            FactVerification(
                required=True,
                verdict="verified",
                claim="某作者去世",
                summary="官方与独立媒体已确认核心事件。",
                verified_facts=["官方已发布讣告。"],
                sources=[
                    FactSource(
                        title="官方讣告",
                        url="https://example.com/official",
                        publisher="出版社",
                    ),
                    FactSource(
                        title="独立报道",
                        url="https://example.com/report",
                        publisher="媒体",
                    ),
                ],
            ),
        )
    )

    assert len(calls) == 1
    assert calls[0]["response_model"] is workbench_llm.StructuredRecommendedDraftOutput
    assert calls[0]["kwargs"].get("allow_web_search", False) is False
    assert calls[0]["kwargs"]["process_timeout_seconds"] == 120.0
    assert matches[0].skill.id == SEED_TEMPLATES[0].id
    assert len(scripts) == 1
    assert status.used_model is True


def test_waiting_heartbeat_updates_latest_activity_in_place() -> None:
    now = datetime.now(timezone.utc)
    task_id = "rewrite-task-waiting-test"
    DRAFT_REWRITE_TASKS[task_id] = DraftRewriteTask(
        id=task_id,
        status="processing",
        stage="fact_checking",
        stage_detail="正在核验",
        progress=18,
        activities=[
            DraftRewriteActivity(
                id="activity-search",
                phase="research",
                kind="search",
                title="正在检索公开来源",
                detail="作者 讣告",
                status="completed",
                created_at=now,
            )
        ],
        created_at=now,
        updated_at=now,
    )
    try:
        _append_draft_rewrite_activity(
            task_id,
            {
                "phase": "research",
                "kind": "status",
                "title": "等待联网核验返回",
                "detail": "已等待 15 秒；最近的真实动作保留在下方记录中。",
                "status": "active",
            },
        )
        task = _append_draft_rewrite_activity(
            task_id,
            {
                "phase": "research",
                "kind": "status",
                "title": "等待联网核验返回",
                "detail": "已等待 30 秒；最近的真实动作保留在下方记录中。",
                "status": "active",
            },
        )

        waiting = [item for item in task.activities if item.title == "等待联网核验返回"]
        assert len(waiting) == 1
        assert "30 秒" in waiting[0].detail
        assert task.activities[0].title == "正在检索公开来源"
    finally:
        DRAFT_REWRITE_TASKS.pop(task_id, None)


def test_short_generated_structures_are_repaired_to_target_duration(monkeypatch) -> None:
    calls: list[str] = []
    activities: list[dict[str, str]] = []

    def build_output(script_length: int) -> workbench_llm.StructuredDraftRewriteOutput:
        variants = []
        for index, angle in enumerate(["事实叙事", "情绪共鸣", "观点升维"], start=1):
            variants.append(
                workbench_llm.StructuredRewriteVariant(
                    content_angle=angle,
                    positioning=f"适合用第 {index} 个方向完成一次完整发布",
                    difference_from_others=f"第 {index} 版使用不同证据顺序和情绪曲线",
                    title=f"第 {index} 版完整口播稿",
                    spoken_script=str(index) * script_length,
                    shot_suggestions=["正面口播", "补充公开素材"],
                    subtitle_rhythm=["短句起势", "结论单独成行"],
                    comment_cta="你更认同哪一种判断？",
                    skill_application=["使用命题钩子", "按案例递进收束"],
                    skill_coverage=[
                        workbench_llm.StructuredSkillCoverage(
                            step="命题开场", evidence="第一句直接给出中心判断"
                        ),
                        workbench_llm.StructuredSkillCoverage(
                            step="证据递进", evidence="中段使用三组材料逐层证明"
                        ),
                        workbench_llm.StructuredSkillCoverage(
                            step="观点收束", evidence="结尾压成判断并邀请评论"
                        ),
                    ],
                )
            )
        return workbench_llm.StructuredDraftRewriteOutput(variants=variants)

    outputs = iter([build_output(180), build_output(280)])

    def fake_completion(response_model, messages, config, **kwargs):
        calls.append(messages[0]["content"])
        return next(outputs)

    monkeypatch.setenv("WORKBENCH_LLM_MODE", "optional")
    monkeypatch.setattr(workbench_llm, "structured_completion", fake_completion)
    payload = DraftRewriteRequest(
        title="一位作者如何被读者记住",
        content="我想从作品和读者记忆出发，写一篇完整口播稿。",
        input_type="outline",
        account_type="泛娱乐观点号",
        duration_seconds=60,
        tone="克制",
        goal="引发评论",
    )
    diagnosis = workbench_llm.DraftDiagnosis(
        id="diagnosis_test",
        draft_title=payload.title,
        draft_type=payload.input_type,
        strengths=["主题明确"],
        problems=["缺少完整口播段落"],
        rewrite_goals=["补足具体材料和情绪因果"],
        suggested_skill_types=["命题钩子"],
        no_go_zones=["不编造事实"],
    )
    matches = [
        workbench_llm.SkillMatch(
            skill=SEED_TEMPLATES[0],
            match_score=88,
            reason="适合把主题补成完整结构",
            apply_plan=["先给判断", "再用材料递进", "最后互动收束"],
        )
    ]

    scripts, status = workbench_llm.generate_rewrite_scripts_structured(
        payload,
        diagnosis,
        matches,
        activity_callback=activities.append,
    )

    assert len(calls) == 2
    assert "结构质量编辑" in calls[1]
    assert [script.spoken_script.startswith("【写作结构工作稿】") for script in scripts] == [True, True, True]
    assert status.used_model is True
    assert any(
        item["title"] == "结构信息量明显偏离，正在校正"
        for item in activities
    )


def test_script_near_duration_reference_is_not_repaired(monkeypatch) -> None:
    calls: list[str] = []

    def fake_completion(response_model, messages, config, **kwargs):
        calls.append(messages[0]["content"])
        return workbench_llm.StructuredDraftRewriteOutput(
            variants=[
                workbench_llm.StructuredRewriteVariant(
                    content_angle=angle,
                    positioning="适合从一个具体切口继续精修",
                    difference_from_others=f"本版使用{angle}切口",
                    title=f"{angle}版初稿",
                    spoken_script=str(index) * 247,
                    shot_suggestions=["正面口播", "补充公开素材"],
                    subtitle_rhythm=["短句起势", "结论单独成行"],
                    comment_cta="哪一个细节最让你记住？",
                    skill_application=["使用命题钩子", "按材料递进收束"],
                    skill_coverage=[
                        workbench_llm.StructuredSkillCoverage(
                            step="命题开场", evidence="第一句给出中心判断"
                        ),
                        workbench_llm.StructuredSkillCoverage(
                            step="证据递进", evidence="中段用材料推进判断"
                        ),
                        workbench_llm.StructuredSkillCoverage(
                            step="观点收束", evidence="结尾压成判断"
                        ),
                    ],
                )
                for index, angle in enumerate(["书架记忆", "作品困境", "写法遗产"], start=1)
            ]
        )

    monkeypatch.setenv("WORKBENCH_LLM_MODE", "optional")
    monkeypatch.setattr(workbench_llm, "structured_completion", fake_completion)
    payload = DraftRewriteRequest(
        title="一位作者如何被读者记住",
        content="我想从作品和读者记忆出发，写一篇完整口播稿。",
        input_type="outline",
        account_type="泛娱乐观点号",
        duration_seconds=60,
        tone="克制",
        goal="引发评论",
    )
    diagnosis = workbench_llm.DraftDiagnosis(
        id="diagnosis_reference",
        draft_title=payload.title,
        draft_type=payload.input_type,
        strengths=["主题明确"],
        problems=["缺少完整口播段落"],
        rewrite_goals=["补足具体材料和情绪因果"],
        suggested_skill_types=["命题钩子"],
        no_go_zones=["不编造事实"],
    )
    matches = [
        workbench_llm.SkillMatch(
            skill=SEED_TEMPLATES[0],
            match_score=88,
            reason="适合把主题补成完整结构",
            apply_plan=["先给判断", "再用材料递进", "最后互动收束"],
        )
    ]

    scripts, _ = workbench_llm.generate_rewrite_scripts_structured(
        payload, diagnosis, matches
    )

    assert len(calls) == 1
    assert [script.content_angle for script in scripts] == [
        "书架记忆",
        "作品困境",
        "写法遗产",
    ]


def test_operator_skill_name_replaces_topic_name_with_structure_name() -> None:
    name = _operator_skill_name(
        "信念反转串讲",
        [
            "命题式金句开场",
            "多个案例并列证明",
            "低谷细节递进",
            "观点升维收束",
        ],
        "命题式金句 + 人物反差",
        "宿命感起势 -> 多案例推进 -> 热血收束",
    )

    assert name == "命题钩子·多例递进"
    assert "信念" not in name


def test_operator_skill_name_keeps_valid_structural_name() -> None:
    name = _operator_skill_name(
        "背景拆解·因果推进",
        ["补齐背景", "解释因果"],
        "先问为什么",
        "疑问 -> 信息 -> 结论",
    )

    assert name == "背景拆解·因果推进"


def test_fact_verification_hides_local_transport_configuration_details(
    monkeypatch,
) -> None:
    monkeypatch.setenv("WORKBENCH_LLM_MODE", "optional")
    monkeypatch.setattr(
        workbench_llm,
        "structured_completion",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("联网事实核验要求 WORKBENCH_LLM_TRANSPORT=codex_cli。")
        ),
    )

    result = workbench_llm.verify_major_claim_structured(
        DraftRewriteRequest(
            title="某作者去世",
            content="某作者去世，我想制作一条缅怀视频。",
            input_type="hotspot",
            account_type="泛娱乐观点号",
            duration_seconds=60,
            tone="克制",
            goal="准确发布",
        )
    )

    assert result.verdict == "failed"
    assert result.summary == (
        "Codex 联网服务配置未加载，已停止生成。请重启本地工作台服务后再试。"
    )
    assert "WORKBENCH_LLM_TRANSPORT" not in result.summary


def test_fact_verification_prompt_uses_a_bounded_stop_rule(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_completion(response_model, messages, config, **kwargs):
        captured["system"] = messages[0]["content"]
        return workbench_llm.StructuredFactVerificationOutput(
            verdict="confirmed",
            core_event_verified=True,
            claim="某作者去世",
            summary="官方来源与独立媒体已确认。",
            verified_facts=["官方公告确认该事件。"],
            sources=[
                workbench_llm.StructuredFactSource(
                    title="官方公告", url="https://example.com/official", publisher="出版社"
                ),
                workbench_llm.StructuredFactSource(
                    title="新闻报道", url="https://example.com/news", publisher="媒体"
                ),
            ],
        )

    monkeypatch.setenv("WORKBENCH_LLM_MODE", "optional")
    monkeypatch.setattr(workbench_llm, "structured_completion", fake_completion)

    result = workbench_llm.verify_major_claim_structured(
        DraftRewriteRequest(
            title="某作者去世",
            content="某作者去世，我想制作一条缅怀视频。",
            input_type="hotspot",
            account_type="泛娱乐观点号",
            duration_seconds=60,
            tone="克制",
            goal="准确发布",
        )
    )

    assert result.verdict == "verified"
    assert "最多执行3次网页检索、打开4个页面" in captured["system"]
    assert "只允许再打开1个权威人物资料" in captured["system"]
    assert "就停止事件扩搜" in captured["system"]


def test_verified_fact_result_is_reused_for_identical_retry(monkeypatch) -> None:
    calls = 0
    activities: list[dict[str, str]] = []

    def fake_completion(response_model, messages, config, **kwargs):
        nonlocal calls
        calls += 1
        return workbench_llm.StructuredFactVerificationOutput(
            verdict="confirmed",
            core_event_verified=True,
            claim="测试作者去世",
            summary="官方来源与独立媒体已确认。",
            verified_facts=["官方公告确认该事件。"],
            sources=[
                workbench_llm.StructuredFactSource(
                    title="官方公告",
                    url="https://example.com/cache-official",
                    publisher="出版社",
                ),
                workbench_llm.StructuredFactSource(
                    title="新闻报道",
                    url="https://example.com/cache-news",
                    publisher="媒体",
                ),
            ],
        )

    payload = DraftRewriteRequest(
        title="测试作者去世",
        content="测试作者去世，我想制作一条克制的缅怀视频。",
        input_type="hotspot",
        account_type="泛娱乐观点号",
        duration_seconds=60,
        tone="克制",
        goal="准确发布",
    )
    monkeypatch.setenv("WORKBENCH_LLM_MODE", "optional")
    monkeypatch.setenv("WORKBENCH_FACT_CACHE_TTL_SECONDS", "1800")
    monkeypatch.setattr(workbench_llm, "structured_completion", fake_completion)
    workbench_llm._FACT_VERIFICATION_CACHE.clear()

    first = workbench_llm.verify_major_claim_structured(payload)
    second = workbench_llm.verify_major_claim_structured(
        payload, activity_callback=activities.append
    )

    assert first.verdict == "verified"
    assert second.verdict == "verified"
    assert calls == 1
    assert activities[-1]["title"] == "已复用近期事实核验"


def test_selection_rewrite_uses_codex_context_without_touching_other_text(
    monkeypatch,
) -> None:
    captured = {}

    def fake_completion(response_model, messages, config, allow_web_search=False):
        captured["prompt"] = messages[-1]["content"]
        return workbench_llm.StructuredSelectionRewriteOutput(
            replacement="《白夜行》写的不是谜底，而是两个人如何被黑暗一步步改变。",
            change_summary="补充作品主题，并让判断更具体。",
        )

    monkeypatch.setenv("WORKBENCH_LLM_MODE", "optional")
    monkeypatch.setattr(workbench_llm, "structured_completion", fake_completion)

    result = workbench_llm.rewrite_selected_passage_structured(
        selected_text="《白夜行》陪伴了很多读者。",
        instruction="补充作品细节，观点更深入",
        full_script="开头。 《白夜行》陪伴了很多读者。 结尾。",
        account_type="泛娱乐观点号",
        duration_seconds=60,
        tone="缅怀尊敬",
        skill_name="冲突反转升维型",
        verified_facts=["《白夜行》围绕人物在案件阴影下的人生展开。"],
    )

    assert result.replacement.startswith("《白夜行》")
    assert "选中片段" in captured["prompt"]
    assert "完整文本上下文" in captured["prompt"]
    assert "补充作品细节" in captured["prompt"]


def test_selection_rewrite_can_research_emotional_evidence(monkeypatch) -> None:
    captured = {}

    def fake_completion(response_model, messages, config, **kwargs):
        captured["system"] = messages[0]["content"]
        captured["allow_web_search"] = kwargs.get("allow_web_search")
        return workbench_llm.StructuredSelectionRewriteOutput(
            replacement="他在失去最熟悉的日常后，仍把那个无法回答的问题写进了人物的选择里。",
            change_summary="用一个可核实的人生节点建立情绪因果。",
            supporting_facts=["可靠人物资料确认了这一人生节点。"],
            sources=[
                workbench_llm.StructuredFactSource(
                    title="人物访谈",
                    url="https://example.com/profile",
                    publisher="出版社",
                )
            ],
        )

    monkeypatch.setenv("WORKBENCH_LLM_MODE", "optional")
    monkeypatch.setattr(workbench_llm, "structured_completion", fake_completion)

    result = workbench_llm.rewrite_selected_passage_structured(
        selected_text="他的作品陪伴了很多人。",
        instruction="补一个最让人感触的人生细节",
        full_script="开头先讲作品。 他的作品陪伴了很多人。 最后落到读者记忆。",
        account_type="泛娱乐观点号",
        duration_seconds=60,
        tone="克制",
        skill_name="命题钩子·群例递进",
        verified_facts=[],
        research_mode="targeted",
        rewrite_intents=["补足人物处境"],
    )

    assert captured["allow_web_search"] is True
    assert "具体场景" in captured["system"]
    assert "不要堆奖项" in captured["system"]
    assert result.sources[0].publisher == "出版社"


def test_selection_rewrite_suggestions_are_generated_from_selected_text(
    monkeypatch,
) -> None:
    captured = {}

    def fake_completion(response_model, messages, config, **kwargs):
        captured["prompt"] = messages[-1]["content"]
        return workbench_llm.StructuredRewriteSuggestionOutput(
            suggestions=[
                workbench_llm.StructuredRewriteSuggestion(
                    id="scene",
                    label="写透人物处境",
                    instruction="补一个人物承受压力并作出选择的具体场景。",
                    reason="这段只有评价，没有人的处境。",
                    evidence_needed=True,
                ),
                workbench_llm.StructuredRewriteSuggestion(
                    id="rhythm",
                    label="收紧判断",
                    instruction="删除重复判断并拆成两个口播短句。",
                    reason="两句表达了同一个结论。",
                    evidence_needed=False,
                ),
                workbench_llm.StructuredRewriteSuggestion(
                    id="bridge",
                    label="承接前文",
                    instruction="增加一句承接上一段作品分析的过渡。",
                    reason="当前转折过快。",
                    evidence_needed=False,
                ),
            ]
        )

    monkeypatch.setenv("WORKBENCH_LLM_MODE", "optional")
    monkeypatch.setattr(workbench_llm, "structured_completion", fake_completion)
    result = workbench_llm.suggest_selection_rewrites_structured(
        selected_text="他的作品陪伴了很多人。",
        full_script="先讲作品主题。 他的作品陪伴了很多人。 最后回到读者。",
        account_type="泛娱乐观点号",
        duration_seconds=60,
        tone="克制",
        skill_name="命题钩子·群例递进",
        verified_facts=[],
    )

    assert "他的作品陪伴了很多人" in captured["prompt"]
    assert result.suggestions[0].evidence_needed is True


def test_rewrite_draft_uses_ai_recommended_draft_instead_of_local_template(monkeypatch) -> None:
    spoken_script = "从旧书架上的折角开始，把作品、创作阶段和读者记忆依次说清楚，最后落到一次阅读为什么会留在人身上。"

    def fake_verify(payload):
        return FactVerification(
            required=True,
            verdict="verified",
            claim="东野圭吾去世",
            summary="两家可靠媒体已确认。",
            verified_facts=["出版社已发布讣告。"],
            sources=[
                FactSource(title="讣告", url="https://example.com/a", publisher="A"),
                FactSource(title="报道", url="https://example.com/b", publisher="B"),
            ],
        )

    def fake_recommended(payload, diagnosis, candidates, fact_verification):
        assert fact_verification.verdict == "verified"
        matches = [
            workbench_llm.SkillMatch(
                skill=candidates[0],
                match_score=91,
                reason="最适合把人物记忆写成递进判断。",
                apply_plan=["反差切入", "作品推进", "判断收束"],
            )
        ]
        scripts = [
            GeneratedScript(
                id="script_ai_recommended",
                title="AI 推荐初稿",
                account_type=payload.account_type,
                content_angle="书架折角",
                duration_seconds=payload.duration_seconds,
                spoken_script=spoken_script,
                shot_suggestions=["使用可核实的公开素材。", "结尾回到人物影响。"],
                subtitle_rhythm=["短句推进。", "结论单独成行。"],
                comment_cta="哪一部作品最影响你？",
                risk_check=risk_check(spoken_script),
                template_used=matches[0].skill.name,
                preset_application=["本版重点：书架折角", "Skill 应用：使用命题钩子。"],
                version_label="V1",
            )
        ]
        return matches, scripts, LLMCallStatus(
            used_model=True,
            mode="optional",
            model="openai/test-model",
        )

    monkeypatch.setattr(
        workbench_llm,
        "select_skill_and_generate_recommended_draft_structured",
        fake_recommended,
    )
    monkeypatch.setattr(workbench_llm, "verify_major_claim_structured", fake_verify)
    response = rewrite_draft(
        DraftRewriteRequest(
            title="东野圭吾去世，我想缅怀一下他",
            content="东野圭吾去世，我想缅怀一下他",
            input_type="hotspot",
            account_type="泛娱乐观点号",
            duration_seconds=60,
            tone="温情温暖",
            goal="引发评论",
        ),
        [approved_skill(SEED_TEMPLATES[0])],
    )

    assert response.generation_mode == "ai"
    assert response.generation_model == "openai/test-model"
    assert [script.content_angle for script in response.scripts] == ["书架折角"]
    assert len(response.scripts) == 1
    assert all("按「" not in script.spoken_script for script in response.scripts)
    assert all("第一段" not in script.spoken_script for script in response.scripts)
    assert response.fact_verification.verdict == "verified"
    assert "待核实" not in response.generation_note


def test_rewrite_draft_does_not_fallback_when_fact_guard_blocks_ai(monkeypatch) -> None:
    def fake_verify(payload):
        return FactVerification(
            required=True,
            verdict="verified",
            claim="某作者去世",
            summary="公开来源已确认。",
            sources=[
                FactSource(title="来源一", url="https://example.com/a", publisher="A"),
                FactSource(title="来源二", url="https://example.com/b", publisher="B"),
            ],
        )

    def fake_blocked(payload, diagnosis, candidates, fact_verification):
        matches = [
            workbench_llm.SkillMatch(
                skill=candidates[0],
                match_score=88,
                reason="适合补齐结构。",
                apply_plan=["先给判断", "再推进证据"],
            )
        ]
        return matches, [], LLMCallStatus(
            used_model=True,
            mode="optional",
            model="openai/test-model",
            error="FACT_GUARD: unsupported death claim",
        )

    monkeypatch.setattr(
        workbench_llm,
        "select_skill_and_generate_recommended_draft_structured",
        fake_blocked,
    )
    monkeypatch.setattr(workbench_llm, "verify_major_claim_structured", fake_verify)
    response = rewrite_draft(
        DraftRewriteRequest(
            title="某作者去世",
            content="某作者去世，我想缅怀他",
            input_type="hotspot",
            account_type="泛娱乐观点号",
            duration_seconds=60,
            tone="温情",
            goal="引发评论",
        ),
        [approved_skill(SEED_TEMPLATES[0])],
    )

    assert response.generation_mode == "blocked"
    assert response.scripts == []
    assert "缺少可靠来源" in response.generation_note


def test_rewrite_draft_stops_when_public_sources_refute_claim(monkeypatch) -> None:
    def fake_refuted(payload):
        return FactVerification(
            required=True,
            verdict="refuted",
            claim="某作者去世",
            summary="当事机构已公开否认。",
            sources=[
                FactSource(
                    title="官方回应",
                    url="https://example.com/official",
                    publisher="官方",
                ),
                FactSource(
                    title="媒体核查", url="https://example.com/check", publisher="媒体"
                ),
            ],
        )

    monkeypatch.setattr(workbench_llm, "verify_major_claim_structured", fake_refuted)
    response = rewrite_draft(
        DraftRewriteRequest(
            title="某作者去世",
            content="某作者去世，我想做一期缅怀视频",
            input_type="hotspot",
            account_type="泛娱乐观点号",
            duration_seconds=60,
            tone="温情",
            goal="引发评论",
        ),
        SEED_TEMPLATES,
    )

    assert response.generation_mode == "blocked"
    assert response.fact_verification.verdict == "refuted"
    assert response.scripts == []
    assert "公开来源" in response.generation_note
