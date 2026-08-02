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
