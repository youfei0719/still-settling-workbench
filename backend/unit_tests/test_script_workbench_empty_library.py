from app import script_workbench


def test_empty_skill_library_uses_a_temporary_analysis_template(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WORKBENCH_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("WORKBENCH_SKILL_EVAL_FIXTURES", raising=False)
    # bootstrap_templates() 会尝试重新加载本地与已发布 Skill 模板；
    # 这个用例要验证的是“两者都为空”时的兜底模板，因此把加载器一并隔离。
    monkeypatch.setattr(script_workbench, "read_local_skill_templates", lambda: [])
    monkeypatch.setattr(
        script_workbench, "read_published_douyin_skill_templates", lambda: []
    )
    monkeypatch.setattr(script_workbench, "TEMPLATES", [])

    template = script_workbench.pick_template("商业分析号")

    assert template.id == "system-analysis-draft"
    assert template.account_type == "商业分析号"
    assert script_workbench.TEMPLATES == []
