"""Phase 2：研究阶段契约（研究 + 角度，不含结构匹配；未核验不得称“已确认事实”）。"""

from app import script_workbench


def _payload(**overrides):
    base = {
        "topic": "某品牌代言人更换引发老用户不满",
        "material_text": "品牌在 8 月公开宣布更换代言人，老用户在评论区表达不满。",
        "account_type": "娱乐吃瓜号",
        "duration_seconds": 60,
        "tone": "真人口语",
        "goal": "引发讨论",
    }
    base.update(overrides)
    return script_workbench.PrepareDraftRequest(**base)


def test_preview_research_never_claims_verified_facts(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WORKBENCH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WORKBENCH_LLM_MODE", "offline")

    response = script_workbench.prepare_research(_payload())
    brief = response.research_brief

    # 没有联网核验时，不允许出现“已确认事实”。
    assert brief.verification_status == "preview"
    assert brief.verified_facts == []
    assert brief.verification_note
    # 用户提供的信息进入待核验，而不是事实。
    assert brief.uncertain_claims
    assert any("核验" in item for item in brief.research_gap)


def test_preview_research_returns_distinct_angle_candidates(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WORKBENCH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WORKBENCH_LLM_MODE", "offline")

    response = script_workbench.prepare_research(_payload())

    assert 4 <= len(response.angle_candidates) <= 8
    names = [angle.name for angle in response.angle_candidates]
    assert len(names) == len(set(names))
    for angle in response.angle_candidates:
        assert angle.thesis.strip()
        assert angle.reason.strip()
        assert angle.missing_materials or angle.required_facts
        assert angle.overlap_risk or angle.main_risks


def test_prepare_research_does_not_return_structure_matches(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WORKBENCH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WORKBENCH_LLM_MODE", "offline")

    response = script_workbench.prepare_research(_payload())

    # 结构匹配必须在 SelectedAngle 之后单独发生。
    assert not hasattr(response, "matched_skills")
    assert "matched_skills" not in response.model_dump()
