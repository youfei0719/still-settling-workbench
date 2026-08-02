from __future__ import annotations

import json


def test_local_settings_persist_public_values_without_secret_echo(
    monkeypatch, tmp_path
) -> None:
    from app import script_workbench, workbench_settings

    monkeypatch.setenv("WORKBENCH_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(workbench_settings, "_keyring", lambda: None)
    monkeypatch.delenv("WORKBENCH_LLM_MODEL", raising=False)
    monkeypatch.delenv("WORKBENCH_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    workbench_settings._SESSION_SECRETS.clear()
    workbench_settings._APPLIED_ENV_VALUES.clear()

    result = script_workbench.update_local_settings(
        script_workbench.LocalSettingsUpdateRequest(
            llm_mode="optional",
            llm_model="openai/test-model",
            llm_api_base="https://api.example.test/v1",
            llm_api_key="test-secret-value",
            skill_remote_url="https://github.com/example/skills.git",
        )
    )

    assert result.llm_api_key_configured is True
    assert result.llm_api_key_source == "session"
    assert result.secret_storage == "session_only"
    assert "test-secret-value" not in result.model_dump_json()
    saved = json.loads((tmp_path / "settings.json").read_text())
    assert saved["llm_model"] == "openai/test-model"
    assert "llm_api_key" not in saved


def test_clearing_session_secret_removes_runtime_value(monkeypatch, tmp_path) -> None:
    from app import script_workbench, workbench_settings

    monkeypatch.setenv("WORKBENCH_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(workbench_settings, "_keyring", lambda: None)
    monkeypatch.delenv("WORKBENCH_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    workbench_settings._SESSION_SECRETS.clear()
    workbench_settings._APPLIED_ENV_VALUES.clear()

    script_workbench.update_local_settings(
        script_workbench.LocalSettingsUpdateRequest(llm_api_key="session-test-value")
    )
    result = script_workbench.update_local_settings(
        script_workbench.LocalSettingsUpdateRequest(clear_llm_key=True)
    )

    assert result.llm_api_key_configured is False
    assert "WORKBENCH_LLM_API_KEY" not in workbench_settings.os.environ
    assert "OPENAI_API_KEY" not in workbench_settings.os.environ


def test_keyring_secret_is_persisted_without_api_echo(monkeypatch, tmp_path) -> None:
    from app import script_workbench, workbench_settings

    class FakeKeyring:
        value: str | None = None

        def get_password(self, service: str, account: str) -> str | None:
            assert service == workbench_settings.KEYRING_SERVICE
            assert account == workbench_settings.KEYRING_ACCOUNT
            return self.value

        def set_password(self, service: str, account: str, value: str) -> None:
            assert service == workbench_settings.KEYRING_SERVICE
            assert account == workbench_settings.KEYRING_ACCOUNT
            self.value = value

        def delete_password(self, service: str, account: str) -> None:
            assert service == workbench_settings.KEYRING_SERVICE
            assert account == workbench_settings.KEYRING_ACCOUNT
            self.value = None

    fake_keyring = FakeKeyring()
    monkeypatch.setenv("WORKBENCH_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(workbench_settings, "_keyring", lambda: fake_keyring)
    monkeypatch.delenv("WORKBENCH_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    workbench_settings._SESSION_SECRETS.clear()
    workbench_settings._APPLIED_ENV_VALUES.clear()

    result = script_workbench.update_local_settings(
        script_workbench.LocalSettingsUpdateRequest(llm_api_key="keyring-test-value")
    )

    assert result.llm_api_key_configured is True
    assert result.llm_api_key_source == "keyring"
    assert result.secrets_persisted is True
    assert "keyring-test-value" not in result.model_dump_json()
    assert fake_keyring.value is not None


def test_environment_values_override_saved_local_values(monkeypatch, tmp_path) -> None:
    from app import workbench_settings

    monkeypatch.setenv("WORKBENCH_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(workbench_settings, "_keyring", lambda: None)
    monkeypatch.setenv("WORKBENCH_LLM_MODEL", "openai/environment-model")
    (tmp_path / "settings.json").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "settings.json").write_text(
        json.dumps({"llm_model": "openai/local-model"}), encoding="utf-8"
    )

    status = workbench_settings.local_settings_status()

    assert status["llm_model"] == "openai/gpt-4.1-mini"
    assert status["sources"]["llm_model"] == "environment"


def test_public_data_root_does_not_read_legacy_skill_library(monkeypatch, tmp_path) -> None:
    from app import script_workbench

    public_root = tmp_path / "public"
    legacy_root = tmp_path / "legacy"
    legacy_root.mkdir()
    (legacy_root / "writing-skills.json").write_text(
        json.dumps({"templates": [script_workbench.SEED_TEMPLATES[0].model_dump(mode="json")]}),
        encoding="utf-8",
    )
    monkeypatch.setenv("WORKBENCH_DATA_DIR", str(public_root))
    monkeypatch.delenv("WORKBENCH_SKILL_LIBRARY_PATH", raising=False)
    monkeypatch.delenv("WORKBENCH_ALLOW_LEGACY_DATA", raising=False)
    monkeypatch.setattr(script_workbench, "LEGACY_SKILL_LIBRARY_ROOT", legacy_root)
    monkeypatch.setattr(script_workbench, "LEGACY_MEDIA_ROOT", legacy_root)

    assert script_workbench.read_local_skill_templates() == []
    assert script_workbench.local_skill_library_path() == public_root / "writing-skills.json"


def test_public_diagnostics_do_not_include_physical_paths(monkeypatch, tmp_path) -> None:
    from app import script_workbench

    monkeypatch.setenv("WORKBENCH_DATA_DIR", str(tmp_path / "public"))
    monkeypatch.delenv("WORKBENCH_ALLOW_LEGACY_DATA", raising=False)
    result = script_workbench.external_gate_report()

    assert result.report_path == ""
    assert "review_file" not in result.human_review_gate
    assert "template_file" not in result.human_review_gate


def test_external_gate_never_returns_key_hints(monkeypatch) -> None:
    from app import script_workbench

    monkeypatch.setenv("WORKBENCH_LLM_MODE", "optional")
    monkeypatch.setenv("WORKBENCH_LLM_MODEL", "gpt-test-model")
    monkeypatch.setenv("WORKBENCH_LLM_API_KEY", "gate-test-value")

    result = script_workbench.external_llm_gate(expect_model=True)

    assert result["api_key_configured"] is True
    assert result["model"] == "gpt-test-model"
    assert "由启动环境管理" not in str(result)
    assert "api_key_hint" not in result
    assert "gate-test-value" not in str(result)


def test_model_discovery_recommends_a_text_model_without_echoing_credentials(
    monkeypatch,
) -> None:
    from app import script_workbench, workbench_llm

    class FakeResponse:
        def read(self) -> bytes:
            return json.dumps(
                {"data": [{"id": "text-mini"}, {"id": "gpt-5"}, {"id": "text-embedding-3"}]}
            ).encode()

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setenv("WORKBENCH_LLM_API_KEY", "model-catalog-secret")
    monkeypatch.setattr(
        workbench_llm,
        "get_llm_config",
        lambda: workbench_llm.LLMRuntimeConfig(
            mode="optional", model="manual", api_base="https://api.example.test/v1"
        ),
    )
    monkeypatch.setattr(script_workbench, "urlopen", lambda *_args, **_kwargs: FakeResponse())

    result = script_workbench.discover_configured_models()

    assert result.recommended_model == "gpt-5"
    assert [item.id for item in result.models] == ["gpt-5", "text-mini", "text-embedding-3"]
    assert "model-catalog-secret" not in result.model_dump_json()


def test_local_skill_repository_setup_is_git_only_and_empty(monkeypatch, tmp_path) -> None:
    from app import script_workbench, workbench_settings

    monkeypatch.setenv("WORKBENCH_CONFIG_DIR", str(tmp_path / "config"))
    for env_name in workbench_settings.PUBLIC_ENV_BY_SETTING.values():
        monkeypatch.delenv(env_name, raising=False)
    workbench_settings._APPLIED_ENV_VALUES.clear()
    destination_parent = tmp_path / "repositories"

    result = script_workbench.create_local_skill_repository(
        script_workbench.LocalRepositoryCreateRequest(
            repository_name="team-writing-skills",
            local_parent_path=str(destination_parent),
        )
    )
    repository = destination_parent / "team-writing-skills"

    assert result.settings.skill_sync_mode == "local"
    assert result.settings.publish_configured is True
    assert (repository / ".git").is_dir()
    assert (repository / "scripts" / "sync_from_workbench.py").is_file()
    assert not (repository / "published").exists()
    assert script_workbench.verify_local_settings().publish_ready is True
