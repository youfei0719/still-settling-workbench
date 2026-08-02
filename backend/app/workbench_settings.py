"""Local-only configuration for the open-source workbench.

Repository configuration is deliberately kept outside the project tree. Secrets
are stored in the operating system credential store when it is available and
are never returned by the API.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

APP_NAME = "douyin-script-workbench"
KEYRING_SERVICE = "douyin-script-workbench"
KEYRING_ACCOUNT = "runtime-secrets"

PUBLIC_ENV_BY_SETTING = {
    "llm_mode": "WORKBENCH_LLM_MODE",
    "llm_model": "WORKBENCH_LLM_MODEL",
    "llm_api_base": "WORKBENCH_LLM_API_BASE",
    "skill_repository_path": "DOUYIN_WRITING_SKILLS_REPO",
    "skill_remote": "DOUYIN_WRITING_SKILLS_REMOTE",
    "skill_remote_url": "DOUYIN_WRITING_SKILLS_REMOTE_URL",
    "skill_branch": "DOUYIN_WRITING_SKILLS_BRANCH",
    "skill_sync_mode": "DOUYIN_WRITING_SKILLS_SYNC_MODE",
}
SECRET_ENV_BY_SETTING = {
    "llm_api_key": "WORKBENCH_LLM_API_KEY",
    "douyin_cookie_string": "WORKBENCH_DOUYIN_COOKIE_STRING",
}
DEFAULTS = {
    "llm_mode": "offline",
    "llm_model": "openai/gpt-4.1-mini",
    "skill_remote": "origin",
    "skill_branch": "main",
    "skill_sync_mode": "github",
}

_SESSION_SECRETS: dict[str, str] = {}
# Values injected from the local settings store. Keeping this distinction lets
# explicit deployment environment variables retain priority without making a
# user-saved value appear to be an administrator-provided environment value.
_APPLIED_ENV_VALUES: dict[str, str] = {}


def config_path() -> Path:
    configured = os.getenv("WORKBENCH_CONFIG_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve() / "settings.json"
    xdg_config = os.getenv("XDG_CONFIG_HOME", "").strip()
    root = Path(xdg_config).expanduser() if xdg_config else Path.home() / ".config"
    return root / APP_NAME / "settings.json"


def _keyring() -> Any | None:
    try:
        import keyring

        backend = keyring.get_keyring()
        if backend.__class__.__module__.startswith("keyring.backends.fail"):
            return None
        return keyring
    except Exception:
        return None


def secret_storage_available() -> bool:
    return _keyring() is not None


def _read_public_settings() -> dict[str, str]:
    path = config_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        key: value.strip()
        for key, value in payload.items()
        if key in PUBLIC_ENV_BY_SETTING and isinstance(value, str) and value.strip()
    }


def _write_public_settings(settings: dict[str, str]) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    tmp_path.chmod(0o600)
    tmp_path.replace(path)
    path.chmod(0o600)


def _read_keyring_secrets() -> dict[str, str]:
    keyring = _keyring()
    if keyring is None:
        return {}
    try:
        raw = keyring.get_password(KEYRING_SERVICE, KEYRING_ACCOUNT)
        payload = json.loads(raw) if raw else {}
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        key: value
        for key, value in payload.items()
        if key in SECRET_ENV_BY_SETTING and isinstance(value, str) and value
    }


def _write_keyring_secrets(secrets: dict[str, str]) -> bool:
    keyring = _keyring()
    if keyring is None:
        return False
    try:
        if secrets:
            keyring.set_password(
                KEYRING_SERVICE,
                KEYRING_ACCOUNT,
                json.dumps(secrets, ensure_ascii=False),
            )
        else:
            try:
                keyring.delete_password(KEYRING_SERVICE, KEYRING_ACCOUNT)
            except Exception:
                pass
        return True
    except Exception:
        return False


def apply_local_settings_to_environment() -> None:
    """Load local settings only when an explicit environment value is absent."""
    for setting, value in _read_public_settings().items():
        env_name = PUBLIC_ENV_BY_SETTING[setting]
        if not os.getenv(env_name, "").strip():
            os.environ[env_name] = value
            _APPLIED_ENV_VALUES[env_name] = value
    for setting, value in {**_read_keyring_secrets(), **_SESSION_SECRETS}.items():
        env_name = SECRET_ENV_BY_SETTING[setting]
        if not os.getenv(env_name, "").strip():
            os.environ[env_name] = value
            _APPLIED_ENV_VALUES[env_name] = value


def _effective_value(setting: str) -> tuple[str, str]:
    env_name = PUBLIC_ENV_BY_SETTING[setting]
    env_value = os.getenv(env_name, "").strip()
    if env_value and _APPLIED_ENV_VALUES.get(env_name) != env_value:
        return env_value, "environment"
    stored = _read_public_settings().get(setting, "")
    return stored, "local" if stored else "default"


def _secret_configured(setting: str) -> tuple[bool, str]:
    env_name = SECRET_ENV_BY_SETTING[setting]
    if (
        os.getenv(env_name, "").strip()
        and _APPLIED_ENV_VALUES.get(env_name) != os.getenv(env_name, "").strip()
    ) or (
        setting == "llm_api_key" and os.getenv("OPENAI_API_KEY", "").strip()
        and _APPLIED_ENV_VALUES.get("OPENAI_API_KEY")
        != os.getenv("OPENAI_API_KEY", "").strip()
    ):
        return True, "environment"
    if _SESSION_SECRETS.get(setting):
        return True, "session"
    if _read_keyring_secrets().get(setting):
        return True, "keyring"
    return False, "none"


def _api_base_label(value: str) -> str:
    if not value.strip():
        return ""
    parsed = urlparse(value)
    return parsed.netloc or "已配置"


def local_settings_status(
    message: str = "本机设置状态已读取。", *, reveal_environment: bool = False
) -> dict[str, Any]:
    values = {setting: _effective_value(setting)[0] for setting in PUBLIC_ENV_BY_SETTING}
    sources = {setting: _effective_value(setting)[1] for setting in PUBLIC_ENV_BY_SETTING}
    runtime_mode = os.getenv("WORKBENCH_LLM_MODE", "offline").strip().lower()
    if runtime_mode not in {"offline", "optional", "required"}:
        runtime_mode = "offline"
    runtime_model = os.getenv("WORKBENCH_LLM_MODEL", "").strip()
    runtime_base_label = _api_base_label(os.getenv("WORKBENCH_LLM_API_BASE", ""))
    publish_values = dict(values)
    for setting, default in DEFAULTS.items():
        if not values[setting]:
            values[setting] = default
        if not publish_values[setting]:
            publish_values[setting] = default
    # Deployment values may include private gateways and local paths. The
    # runtime can keep using them, but this local status endpoint must not echo
    # them back into the browser or a diagnostic export.
    if not reveal_environment:
        for setting, source in sources.items():
            if source == "environment":
                values[setting] = DEFAULTS.get(setting, "")
    llm_key_configured, llm_key_source = _secret_configured("llm_api_key")
    cookie_configured, cookie_source = _secret_configured("douyin_cookie_string")
    sync_mode = publish_values.get("skill_sync_mode", "github")
    publish_ready = bool(
        publish_values.get("skill_repository_path")
        and publish_values.get("skill_branch")
        and (sync_mode == "local" or publish_values.get("skill_remote_url"))
    )
    return {
        **values,
        "sources": sources,
        "llm_connection_managed": any(
            sources.get(setting) == "environment"
            for setting in ("llm_mode", "llm_model", "llm_api_base")
        ) or llm_key_source == "environment",
        "llm_runtime_mode": runtime_mode,
        "llm_runtime_model": runtime_model,
        "llm_api_base_label": runtime_base_label,
        "llm_api_key_configured": llm_key_configured,
        "llm_api_key_source": llm_key_source,
        "douyin_cookie_configured": cookie_configured,
        "douyin_cookie_source": cookie_source,
        "secret_storage": "system_keyring" if secret_storage_available() else "session_only",
        "secrets_persisted": secret_storage_available(),
        "publish_configured": publish_ready,
        "message": message,
    }


def save_local_settings(
    updates: dict[str, str | None],
    clear_llm_key: bool = False,
    clear_douyin_cookie: bool = False,
) -> dict[str, Any]:
    public_settings = _read_public_settings()
    for setting in PUBLIC_ENV_BY_SETTING:
        if setting not in updates or updates[setting] is None:
            continue
        value = (updates[setting] or "").strip()
        if value:
            public_settings[setting] = value
        else:
            public_settings.pop(setting, None)
    _write_public_settings(public_settings)

    secrets = _read_keyring_secrets()
    session_updates: dict[str, str] = {}
    for setting in SECRET_ENV_BY_SETTING:
        if setting not in updates or updates[setting] is None:
            continue
        value = (updates[setting] or "").strip()
        if value:
            secrets[setting] = value
            session_updates[setting] = value
        else:
            secrets.pop(setting, None)
            _SESSION_SECRETS.pop(setting, None)
            env_name = SECRET_ENV_BY_SETTING[setting]
            if env_name in _APPLIED_ENV_VALUES:
                os.environ.pop(env_name, None)
                _APPLIED_ENV_VALUES.pop(env_name, None)
            if setting == "llm_api_key" and "OPENAI_API_KEY" in _APPLIED_ENV_VALUES:
                os.environ.pop("OPENAI_API_KEY", None)
                _APPLIED_ENV_VALUES.pop("OPENAI_API_KEY", None)
    if clear_llm_key:
        secrets.pop("llm_api_key", None)
        _SESSION_SECRETS.pop("llm_api_key", None)
        if "WORKBENCH_LLM_API_KEY" in _APPLIED_ENV_VALUES:
            os.environ.pop("WORKBENCH_LLM_API_KEY", None)
            _APPLIED_ENV_VALUES.pop("WORKBENCH_LLM_API_KEY", None)
        if "OPENAI_API_KEY" in _APPLIED_ENV_VALUES:
            os.environ.pop("OPENAI_API_KEY", None)
            _APPLIED_ENV_VALUES.pop("OPENAI_API_KEY", None)
    if clear_douyin_cookie:
        secrets.pop("douyin_cookie_string", None)
        _SESSION_SECRETS.pop("douyin_cookie_string", None)
        if "WORKBENCH_DOUYIN_COOKIE_STRING" in _APPLIED_ENV_VALUES:
            os.environ.pop("WORKBENCH_DOUYIN_COOKIE_STRING", None)
            _APPLIED_ENV_VALUES.pop("WORKBENCH_DOUYIN_COOKIE_STRING", None)

    persisted_secrets = _write_keyring_secrets(secrets)
    if not persisted_secrets:
        _SESSION_SECRETS.update(session_updates)

    # A user action should take effect immediately unless an administrator set
    # an explicit environment value before the process started.
    for setting, value in public_settings.items():
        env_name = PUBLIC_ENV_BY_SETTING[setting]
        if not os.getenv(env_name, "").strip() or env_name in _APPLIED_ENV_VALUES:
            os.environ[env_name] = value
            _APPLIED_ENV_VALUES[env_name] = value
    for setting, value in session_updates.items():
        env_name = SECRET_ENV_BY_SETTING[setting]
        if not os.getenv(env_name, "").strip() or env_name in _APPLIED_ENV_VALUES:
            os.environ[env_name] = value
            _APPLIED_ENV_VALUES[env_name] = value
    if "llm_api_key" in session_updates and (
        not os.getenv("OPENAI_API_KEY", "").strip()
        or "OPENAI_API_KEY" in _APPLIED_ENV_VALUES
    ):
        os.environ["OPENAI_API_KEY"] = session_updates["llm_api_key"]
        _APPLIED_ENV_VALUES["OPENAI_API_KEY"] = session_updates["llm_api_key"]

    message = (
        "本机设置已保存；敏感信息已保存到系统钥匙串。"
        if persisted_secrets or not session_updates
        else "普通设置已保存；系统钥匙串不可用，敏感信息只在本次运行有效。"
    )
    return local_settings_status(message)
