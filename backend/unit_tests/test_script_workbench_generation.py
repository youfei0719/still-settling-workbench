"""Phase 4：完整成稿的证据边界、证据检查、材料缺口与结构执行。"""

from app import script_workbench as sw


def _materials():
    return [
        sw.MaterialCard(
            id="material-1",
            type="fact",
            title="官方活动周期",
            content="官方页面显示该活动持续三个月。",
            source_url="https://example.com/a",
            verification_status="verified",
            claim_id="fact-1",
            selected=True,
        ),
        sw.MaterialCard(
            id="material-2",
            type="data",
            title="官方公布参与人数",
            content="官方页面显示首周参与人数为 12 万。",
            source_url="https://example.com/b",
            verification_status="verified",
            claim_id="fact-2",
            selected=True,
        ),
        sw.MaterialCard(
            id="material-3",
            type="opinion",
            title="网友观点",
            content="不少网友认为定价偏高。",
            verification_status="uncertain",
            selected=True,
        ),
        sw.MaterialCard(
            id="material-4",
            type="fact",
            title="未被选中的争议材料",
            content="有说法称该品牌老用户大量流失。",
            verification_status="uncertain",
            selected=False,
        ),
    ]


def _brief():
    return sw.ResearchBrief(
        input_type="hotspot",
        summary="测试用研究简报",
        verification_status="verified",
        verification_note="已联网核对 2 个来源",
        verified_facts=["官方页面显示该活动持续三个月。", "官方页面显示首周参与人数为 12 万。"],
        verified_claims=[
            sw.FactClaim(
                id="fact-1",
                claim="官方页面显示该活动持续三个月。",
                source_ids=["src-1"],
                confidence="high",
                verification_status="verified",
            ),
            sw.FactClaim(
                id="fact-2",
                claim="官方页面显示首周参与人数为 12 万。",
                source_ids=["src-2"],
                confidence="high",
                verification_status="verified",
            ),
        ],
        uncertain_claims=["有说法称该品牌老用户大量流失。"],
        sources=[
            sw.FactSource(id="src-1", title="官方页面 A", url="https://example.com/a", publisher="官方"),
            sw.FactSource(id="src-2", title="官方页面 B", url="https://example.com/b", publisher="官方"),
        ],
    )


def _request(**overrides):
    base = {
        "topic": "某品牌活动引发讨论",
        "user_material": "用户自己补充的背景。",
        "selected_angle": "从公开数据看，关键是执行细节而不是立场",
        "structure_name": "通用写作骨架",
        "structure_steps": ["开头钩子", "事实与细节", "推进与转折", "观点收束", "互动引导"],
        "structure_mapping": [
            sw.StructureMaterialMapping(step="事实与细节", material_ids=["material-1", "material-2"], note="")
        ],
        "structure_gaps": ["还缺复购数据。"],
        "materials": _materials(),
        "research_brief": _brief(),
    }
    base.update(overrides)
    return sw.ScriptGenerationRequest(**base)


def test_allowed_evidence_excludes_unselected_and_uncertain(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WORKBENCH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WORKBENCH_LLM_MODE", "offline")

    evidence, material_ids, claim_ids, notes = sw._allowed_evidence(_request())

    assert material_ids == {"material-1", "material-2", "material-3"}
    # 未选中的 material-4 不得进入允许清单
    assert "material-4" not in material_ids
    # 只有与已选素材关联的已核验事实才被允许
    assert claim_ids == {"fact-1", "fact-2"}
    blob = str(evidence)
    assert "material-4" not in blob
    # 未核验 / 观点类素材必须带限制说明
    assert any(
        "未完全核实" in note or "只能作为观点" in note for note in notes
    )


def test_materials_sent_with_selected_flag_are_usable(monkeypatch, tmp_path) -> None:
    """前端必须显式标记 selected=true；否则后端会（正确地）拒绝使用该素材。"""
    monkeypatch.setenv("WORKBENCH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WORKBENCH_LLM_MODE", "offline")

    # 未标记 selected 的素材不应进入 Allowed Evidence
    unflagged = _request(
        materials=[card.model_copy(update={"selected": False}) for card in _materials()]
    )
    _evidence, material_ids, claim_ids, _notes = sw._allowed_evidence(unflagged)
    assert material_ids == set()
    assert claim_ids == set()

    # 显式标记后可用
    flagged = _request(materials=_materials())
    _evidence2, material_ids2, claim_ids2, _notes2 = sw._allowed_evidence(flagged)
    assert material_ids2
    assert claim_ids2 == {"fact-1", "fact-2"}


def test_generated_draft_is_complete_and_has_no_placeholders(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WORKBENCH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WORKBENCH_LLM_MODE", "offline")

    script = sw.generate_complete_script(_request()).script

    assert script.spoken_script.strip()
    assert len(script.spoken_script.replace("\n", "")) > 30
    for marker in ["【", "材料不足", "你来填写", "结构工作稿", "待补"]:
        assert marker not in script.spoken_script
    # 只生成一篇主稿（compat 字段不承载多篇）
    assert script.version_label == "v1"
    assert script.used_material_ids
    assert script.used_claim_ids == ["fact-1", "fact-2"]


def test_material_gap_and_evidence_policy_are_outside_body(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WORKBENCH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WORKBENCH_LLM_MODE", "offline")

    script = sw.generate_complete_script(_request()).script

    assert script.material_gaps
    for gap in script.material_gaps:
        assert gap.handling.strip()
        assert gap.gap not in script.spoken_script
    assert script.evidence_policy
    assert any("uncertain_claims" in item for item in script.evidence_policy)


def test_unsupported_claims_are_detected_and_removed(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WORKBENCH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WORKBENCH_LLM_MODE", "offline")

    evidence, _materials, _claims, _notes = sw._allowed_evidence(_request())
    draft = (
        "官方页面显示该活动持续三个月。"
        "此外该品牌还有一份内部文件显示复购率下降三成。"
    )
    unsupported = sw._deterministic_unsupported_claims(draft, evidence)
    assert any("复购率下降三成" in item.text for item in unsupported)

    cleaned = sw._drop_unsupported_sentences(draft, unsupported)
    assert "复购率下降三成" not in cleaned
    assert "持续三个月" in cleaned


def test_adversarial_angle_without_evidence_never_fabricates(
    monkeypatch, tmp_path
) -> None:
    """对抗测试：故意选择一个证据不足的角度（未选任何素材）。"""
    monkeypatch.setenv("WORKBENCH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WORKBENCH_LLM_MODE", "offline")

    empty = _request(
        materials=[card.model_copy(update={"selected": False}) for card in _materials()],
        selected_angle="这个品牌的老用户已经大规模流失，内部数据可以证明",
        structure_mapping=[],
        structure_gaps=["没有可用素材证明老用户流失。"],
    )
    evidence, material_ids, claim_ids, _notes = sw._allowed_evidence(empty)
    assert material_ids == set()
    assert claim_ids == set()

    script = sw.generate_complete_script(empty).script
    # 不允许把没有证据的判断写成事实
    assert "大规模流失" not in script.spoken_script
    assert "内部数据" not in script.spoken_script
    # 缺口必须记录在正文之外
    assert any("流失" in gap.gap for gap in script.material_gaps)
    for marker in ["【", "材料不足", "你来填写"]:
        assert marker not in script.spoken_script
    assert script.risk_check.level in {"low", "medium", "high"}


def test_body_is_never_empty_even_when_everything_is_unsupported(
    monkeypatch, tmp_path
) -> None:
    """极端情况：证据不足 + 无任何可用素材时，正文也必须完整可读。"""
    monkeypatch.setenv("WORKBENCH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WORKBENCH_LLM_MODE", "offline")

    empty = _request(
        materials=[card.model_copy(update={"selected": False}) for card in _materials()],
        selected_angle="这个品牌的老用户已经大规模流失，内部数据可以证明",
        structure_mapping=[],
        structure_gaps=["没有可用素材证明老用户流失。"],
    )
    script = sw.generate_complete_script(empty).script

    assert len(sw._normalize_for_match(script.spoken_script)) >= 20
    assert script.spoken_script.strip()
    assert "大规模流失" not in script.spoken_script
    for marker in ["【", "材料不足", "你来填写"]:
        assert marker not in script.spoken_script


def test_question_and_hedge_sentences_are_not_flagged(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WORKBENCH_DATA_DIR", str(tmp_path))

    evidence, _materials, _claims, _notes = sw._allowed_evidence(_request())
    draft = "你怎么看这件事？\n\n这条判断可能还需要更多公开材料。"
    assert sw._deterministic_unsupported_claims(draft, evidence) == []


def test_ai_path_removes_unsupported_fact_and_keeps_body(
    monkeypatch, tmp_path
) -> None:
    """AI 路径：模型写了无证据事实时，必须删除且保留完整正文。"""
    monkeypatch.setenv("WORKBENCH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WORKBENCH_LLM_MODE", "optional")

    from app import workbench_llm

    class _Status:
        used_model = True
        mode = "optional"
        model = "test-model"
        error = None

    class _Output:
        title = "测试标题"
        title_candidates = ["候选标题一", "候选标题二"]
        spoken_script = (
            "官方页面显示该活动持续三个月。"
            "另外有内部文件显示复购率下降三成。"
            "你怎么看这件事？"
        )
        shot_suggestions = ["开场用活动画面"]
        subtitle_rhythm = ["一句话一屏"]
        comment_cta = "你怎么看这件事？"
        used_material_ids = ["material-1", "material-999"]
        used_claim_ids = ["fact-1", "fact-999"]
        evidence_map: list = []
        material_gaps: list = []
        structure_coverage = ["开头钩子：已执行"]

    monkeypatch.setattr(
        workbench_llm,
        "get_llm_config",
        lambda: type("C", (), {"mode": "optional", "model": "test-model"})(),
    )
    monkeypatch.setattr(
        workbench_llm,
        "generate_complete_script_structured",
        lambda *a, **k: type("R", (), {"status": _Status(), "output": _Output(), "error": ""})(),
    )
    monkeypatch.setattr(
        workbench_llm,
        "repair_script_evidence_structured",
        lambda **k: None,
    )

    script = sw.generate_complete_script(_request()).script

    # 无证据事实被删除，有证据的事实与提问保留
    assert "复购率下降三成" not in script.spoken_script
    assert "持续三个月" in script.spoken_script
    assert "你怎么看" in script.spoken_script
    assert len(sw._normalize_for_match(script.spoken_script)) >= 20
    # 虚报的 id 被过滤
    assert script.used_material_ids == ["material-1"]
    assert script.used_claim_ids == ["fact-1"]
    # 只输出一篇主稿 + 标题候选
    assert len(script.title_candidates) == 2
    assert script.version_label == "v1"


def test_placeholders_are_stripped_from_body(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WORKBENCH_DATA_DIR", str(tmp_path))

    dirty = "开头先说结论。【这里补充一个案例】第二段用数据支撑。[待补数据] 结尾提问。"
    cleaned, removed = sw.strip_placeholders(dirty)
    for marker in ["【", "】", "[待补数据]"]:
        assert marker not in cleaned
    assert removed
    assert "开头先说结论" in cleaned


def test_final_body_check_runs_even_when_model_reports_nothing(
    monkeypatch, tmp_path
) -> None:
    """模型复核没报问题，但正文里仍有无依据事实时，必须由确定性检查兜住。"""
    monkeypatch.setenv("WORKBENCH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WORKBENCH_LLM_MODE", "optional")

    from app import workbench_llm

    class _Status:
        used_model = True
        mode = "optional"
        model = "test-model"
        error = None

    class _Output:
        title = "测试标题"
        title_candidates: list = []
        spoken_script = (
            "官方页面显示该活动持续三个月。"
            "有内部文件显示该品牌复购率下降三成。"
            "你怎么看这件事？"
        )
        shot_suggestions: list = []
        subtitle_rhythm: list = []
        comment_cta = "你怎么看这件事？"
        used_material_ids = ["material-1"]
        used_claim_ids = ["fact-1"]
        evidence_map: list = []
        material_gaps: list = []
        structure_coverage: list = []

    monkeypatch.setattr(
        workbench_llm, "get_llm_config",
        lambda: type("C", (), {"mode": "optional", "model": "test-model"})(),
    )
    monkeypatch.setattr(
        workbench_llm, "generate_complete_script_structured",
        lambda *a, **k: type("R", (), {"status": _Status(), "output": _Output(), "error": ""})(),
    )
    # 模型复核“什么都没发现”
    monkeypatch.setattr(
        workbench_llm, "repair_script_evidence_structured", lambda **k: None
    )

    script = sw.generate_complete_script(_request()).script
    assert "复购率下降" not in script.spoken_script
    assert "持续三个月" in script.spoken_script
    assert script.evidence_check.unsupported_claims


def test_uncertain_claim_made_factual_raises_risk(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WORKBENCH_DATA_DIR", str(tmp_path))

    risk = sw._script_risk_check(
        "可以确认该品牌老用户大量流失，这是最好的结果。",
        uncertain_claims=["有说法称该品牌老用户大量流失。"],
        unsupported=[],
        forbidden_phrases=["最好"],
    )
    labels = {item.label for item in risk.items}
    assert "uncertain-as-fact" in labels
    assert "客户禁用表达" in labels
    assert risk.passed is False
