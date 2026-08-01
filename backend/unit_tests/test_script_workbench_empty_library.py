from app import script_workbench


def test_empty_skill_library_uses_a_temporary_analysis_template(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WORKBENCH_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("WORKBENCH_SKILL_EVAL_FIXTURES", raising=False)
    monkeypatch.setattr(script_workbench, "TEMPLATES", [])

    template = script_workbench.pick_template("商业分析号")

    assert template.id == "system-analysis-draft"
    assert template.account_type == "商业分析号"
    assert script_workbench.TEMPLATES == []
