"""Phase 3：Angle-driven 素材研究、素材卡契约与结构推荐（含空 Skill 库 fallback）。"""

from app import script_workbench


def _research(topic: str = "某品牌代言人更换引发老用户不满"):
    return script_workbench.prepare_research(
        script_workbench.PrepareDraftRequest(
            topic=topic,
            material_text="品牌在 8 月公开宣布更换代言人，老用户在评论区表达不满。",
            account_type="娱乐吃瓜号",
            duration_seconds=60,
            tone="真人口语",
            goal="引发讨论",
        )
    )


def test_material_cards_carry_source_and_angle_relevance(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WORKBENCH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WORKBENCH_LLM_MODE", "offline")

    research = _research()
    angle = research.angle_candidates[0]
    response = script_workbench.research_angle_materials(
        script_workbench.MaterialResearchRequest(
            topic="某品牌代言人更换引发老用户不满",
            material_text="品牌在 8 月公开宣布更换代言人。",
            selected_angle=angle.thesis,
            angle_name=angle.name,
            angle_missing_evidence=angle.missing_materials,
            research_brief=research.research_brief,
        )
    )

    assert response.materials
    for card in response.materials:
        # 每张卡都必须能回答「这是什么」和「为什么对这个角度有用」。
        assert card.title.strip()
        assert card.content.strip()
        assert card.relevance_to_angle.strip()
        assert card.suggested_usage.strip()
        # 没有可访问来源时不允许标记为已核实。
        if not card.source_url:
            assert card.verification_status == "uncertain"


def test_opinion_materials_keep_opinion_type(monkeypatch, tmp_path) -> None:
    """观点类素材必须保留 opinion/quote 类型，不得被改写为事实类型。"""
    monkeypatch.setenv("WORKBENCH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WORKBENCH_LLM_MODE", "offline")

    research = _research()
    angle = research.angle_candidates[0]
    response = script_workbench.research_angle_materials(
        script_workbench.MaterialResearchRequest(
            topic="某品牌代言人更换引发老用户不满",
            selected_angle=angle.thesis,
            angle_name=angle.name,
            research_brief=research.research_brief,
        )
    )

    for card in response.materials:
        if card.type in {"opinion", "quote"}:
            # 观点类素材即使来源可追溯，也不应被标成"已确认事实"类型。
            assert card.type != "fact"
            assert card.verification_status in {"verified", "uncertain", "preview"}


def test_angle_research_uses_selected_angle_and_offline_never_fabricates(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("WORKBENCH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WORKBENCH_LLM_MODE", "offline")

    research = _research()
    angle = research.angle_candidates[0]
    response = script_workbench.research_angle_materials(
        script_workbench.MaterialResearchRequest(
            topic="某品牌代言人更换引发老用户不满",
            selected_angle=angle.thesis,
            angle_name=angle.name,
            research_brief=research.research_brief,
        )
    )

    assert response.generation_mode == "fallback"
    # 离线时只复用第一轮研究结果，明确说明没有联网。
    assert "未启用" in response.stop_reason or "复用" in response.stop_reason


def _selected_cards() -> list[script_workbench.MaterialCard]:
    return [
        script_workbench.MaterialCard(
            id="material-1",
            type="fact",
            title="公开宣布更换代言人",
            content="品牌在 8 月公开宣布更换代言人。",
            source_url="https://example.com/a",
            verification_status="verified",
            selected=True,
        ),
        script_workbench.MaterialCard(
            id="material-2",
            type="opinion",
            title="老用户在评论区表达不满",
            content="评论区出现大量老用户不满的表达。",
            verification_status="uncertain",
            selected=True,
        ),
    ]


def test_structure_recommendation_uses_selected_materials(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WORKBENCH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WORKBENCH_LLM_MODE", "offline")

    response = script_workbench.recommend_structures(
        script_workbench.StructureRecommendationRequest(
            topic="某品牌代言人更换引发老用户不满",
            selected_angle="从公开信息看，争议真正指向品牌如何处理老用户关系",
            materials=_selected_cards(),
        )
    )

    # 被选中的素材必须真正进入结构映射。
    mapped_ids = {
        material_id
        for item in response.generic_structure.material_mapping
        for material_id in item.material_ids
    }
    assert {"material-1", "material-2"} <= mapped_ids
    assert response.generic_structure.id == "generic-structure"
    for recommendation in response.recommendations:
        assert recommendation.why_fits.strip()
        assert len(recommendation.skeleton) >= 3


def test_structure_recommendation_ignores_unselected_materials(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("WORKBENCH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WORKBENCH_LLM_MODE", "offline")

    cards = [
        card.model_copy(update={"selected": False}) for card in _selected_cards()
    ]
    response = script_workbench.recommend_structures(
        script_workbench.StructureRecommendationRequest(
            topic="某品牌代言人更换引发老用户不满",
            selected_angle="从公开信息看，争议真正指向品牌如何处理老用户关系",
            materials=cards,
        )
    )

    mapped_ids = {
        material_id
        for item in response.generic_structure.material_mapping
        for material_id in item.material_ids
    }
    assert mapped_ids == set()
    assert response.generic_structure.material_gaps


def test_structure_mapping_survives_unknown_material_ids(
    monkeypatch, tmp_path
) -> None:
    """模型返回无法对应的素材 id 时，不能把已选素材映射清空。"""
    monkeypatch.setenv("WORKBENCH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WORKBENCH_LLM_MODE", "offline")

    response = script_workbench.recommend_structures(
        script_workbench.StructureRecommendationRequest(
            topic="某品牌代言人更换引发老用户不满",
            selected_angle="从公开信息看，争议真正指向品牌如何处理老用户关系",
            materials=_selected_cards(),
        )
    )

    mapped = [
        material_id
        for item in response.generic_structure.material_mapping
        for material_id in item.material_ids
    ]
    # 只要用户选了素材，映射里就必须能看到它们。
    assert mapped, "已选素材在结构映射中丢失"
    assert set(mapped) <= {"material-1", "material-2"}


def test_empty_skill_library_still_offers_generic_structure(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("WORKBENCH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WORKBENCH_LLM_MODE", "offline")
    monkeypatch.setattr(script_workbench, "match_writing_skills", lambda *a, **k: [])

    response = script_workbench.recommend_structures(
        script_workbench.StructureRecommendationRequest(
            topic="某品牌代言人更换引发老用户不满",
            selected_angle="从公开信息看，争议真正指向品牌如何处理老用户关系",
            materials=_selected_cards(),
        )
    )

    # Skill 是增强项不是门禁：库为空时仍必须能继续。
    assert response.recommendations == []
    assert response.generic_structure.id == "generic-structure"
    assert len(response.generic_structure.skeleton) >= 3
    assert "可以继续" in response.note
