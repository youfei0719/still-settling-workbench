from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


CONNECTOR_PATH = Path(__file__).parents[1] / "still_settling_connector.py"
SPEC = importlib.util.spec_from_file_location(
    "still_settling_connector", CONNECTOR_PATH
)
assert SPEC and SPEC.loader
connector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(connector)


def test_extract_douyin_url_accepts_share_copy() -> None:
    value = "复制后打开抖音 https://v.douyin.com/HDFKsRngq0E/ 直接观看"

    assert connector.extract_douyin_url(value) == "https://v.douyin.com/HDFKsRngq0E/"


@pytest.mark.parametrize(
    "value",
    [
        "https://example.com/video.mp4",
        "https://douyin.com.evil.example/video",
        "not a url",
    ],
)
def test_extract_douyin_url_rejects_non_douyin_targets(value: str) -> None:
    with pytest.raises(connector.ConnectorError):
        connector.extract_douyin_url(value)


def test_downloader_prefers_chrome_session_and_baocut_compatible_mp4_format(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    commands: list[list[str]] = []

    monkeypatch.setattr(connector, "ytdlp_binary", lambda: "yt-dlp")

    def fake_run(command: list[str], **_kwargs: object) -> None:
        commands.append(command)
        (tmp_path / "source.mp4").write_bytes(b"video")

    monkeypatch.setattr(connector.subprocess, "run", fake_run)

    media = connector.download_attempt(
        "https://v.douyin.com/example/", tmp_path, browser="chrome"
    )

    assert media == tmp_path / "source.mp4"
    assert commands[0][commands[0].index("--cookies-from-browser") + 1] == "chrome"
    assert (
        commands[0][commands[0].index("--format") + 1] == connector.PREFERRED_MP4_FORMAT
    )
    assert commands[0][commands[0].index("--socket-timeout") + 1] == str(
        connector.DOWNLOAD_SOCKET_TIMEOUT_SECONDS
    )


def test_downloader_tries_anonymous_session_before_browser_recovery(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    attempts: list[tuple[str | None, str | None]] = []
    media = tmp_path / "source.mp4"
    media.write_bytes(b"video")

    monkeypatch.setattr(connector, "system_http_proxy", lambda: "http://127.0.0.1:7897")

    def fake_attempt(
        _url: str, _output_dir: Path, browser: str | None, proxy: str | None = None
    ) -> Path | None:
        attempts.append((browser, proxy))
        return media if browser is None else None

    monkeypatch.setattr(connector, "download_attempt", fake_attempt)

    result, temporary_directory = connector.download_media(
        "https://v.douyin.com/example/"
    )
    try:
        assert result == media
        assert attempts == [(None, "http://127.0.0.1:7897")]
    finally:
        temporary_directory.cleanup()


def test_parses_enabled_macos_system_proxy() -> None:
    output = """
    HTTPEnable : 1
    HTTPPort : 7897
    HTTPProxy : 127.0.0.1
    """
    assert connector.proxy_from_scutil(output) == "http://127.0.0.1:7897"


def test_transcription_keeps_media_local_and_returns_only_transcript(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "workbench"
    worker = root / "backend" / "scripts" / "workbench_model_worker.py"
    worker.parent.mkdir(parents=True)
    worker.write_text("# worker", encoding="utf-8")
    model_python = root / ".venv-model" / "bin" / "python"
    model_python.parent.mkdir(parents=True)
    model_python.write_text("", encoding="utf-8")
    model_python.chmod(0o700)
    media = tmp_path / "source.mp4"
    media.write_bytes(b"video")
    audio = tmp_path / "source.wav"
    audio.write_bytes(b"audio")

    monkeypatch.setenv("STILL_SETTLING_PROJECT_ROOT", str(root))
    monkeypatch.setattr(connector, "extract_audio", lambda *_args: audio)

    def fake_run(command: list[str], **kwargs: object) -> object:
        assert str(media) not in command
        assert command[0] == str(model_python)
        assert kwargs["env"]["WORKBENCH_ASR_MODE"] == "required"
        output = Path(command[command.index("--output") + 1])
        output.write_text(
            '{"status":"completed","provider":"FunASR","text":"这是一段可分析的本机转写文稿。","timestamps":["0-1: 这是一段"]}',
            encoding="utf-8",
        )
        return type("Completed", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(connector.subprocess, "run", fake_run)

    result = connector.transcribe_media(media, tmp_path)

    assert result == {
        "text": "这是一段可分析的本机转写文稿。",
        "timestamps": ["0-1: 这是一段"],
        "provider": "FunASR",
    }
