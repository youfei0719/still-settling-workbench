from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


CONNECTOR_PATH = Path(__file__).parents[1] / "still_settling_connector.py"
SPEC = importlib.util.spec_from_file_location("still_settling_connector", CONNECTOR_PATH)
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
    assert commands[0][commands[0].index("--format") + 1] == connector.PREFERRED_MP4_FORMAT
