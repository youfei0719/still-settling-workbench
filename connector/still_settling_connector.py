#!/usr/bin/env python3
"""Local-only media connector for the Still Settling workbench.

The connector deliberately keeps browser cookies on the user's computer.  It
only downloads public Douyin media to a temporary directory and streams that
media back to the calling CPM workbench page on localhost.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Final
from urllib.parse import urlparse


DEFAULT_PORT: Final = 8765
MAX_REQUEST_BYTES: Final = 16 * 1024
MAX_MEDIA_BYTES: Final = 512 * 1024 * 1024
ALLOWED_HOSTS: Final = ("douyin.com", "iesdouyin.com")
DEFAULT_ORIGINS: Final = {
    "http://127.0.0.1:5174",
    "http://localhost:5174",
    "http://170.106.75.116",
}
SUPPORTED_EXTENSIONS: Final = {".m4v", ".mkv", ".mov", ".mp4", ".webm"}
BROWSER_RETRY_ORDER: Final = (
    "chrome",
    "safari",
    "firefox",
    "brave",
    "edge",
    "chromium",
    "opera",
    "vivaldi",
)


class ConnectorError(RuntimeError):
    """A user-actionable local extraction failure."""


def allowed_origins() -> set[str]:
    configured = os.getenv("STILL_SETTLING_CONNECTOR_ORIGINS", "").strip()
    if not configured:
        return set(DEFAULT_ORIGINS)
    return {item.strip().rstrip("/") for item in configured.split(",") if item.strip()}


def extract_douyin_url(value: str) -> str:
    match = re.search(r"https?://[^\s]+", value.strip())
    if not match:
        raise ConnectorError("请输入完整的抖音分享链接或短链。")
    url = match.group(0).rstrip("，。；;,.!?！？”’\")]}>")
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not parsed.scheme.startswith("http") or not any(
        host == domain or host.endswith(f".{domain}") for domain in ALLOWED_HOSTS
    ):
        raise ConnectorError("本机连接器仅处理 douyin.com 的分享链接。")
    return url


def ytdlp_binary() -> str:
    configured = os.getenv("STILL_SETTLING_YTDLP", "").strip()
    candidates = [
        configured,
        shutil.which("yt-dlp") or "",
        "/opt/homebrew/bin/yt-dlp",
        "/usr/local/bin/yt-dlp",
    ]
    for executable in candidates:
        if executable and Path(executable).is_file() and os.access(executable, os.X_OK):
            return executable
    raise ConnectorError("未找到 yt-dlp。请先安装 BaoCut 所使用的 yt-dlp。")


def downloaded_media_path(output_dir: Path) -> Path | None:
    files = [
        path
        for path in output_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    return max(files, key=lambda path: path.stat().st_size, default=None)


def download_attempt(url: str, output_dir: Path, browser: str | None) -> Path | None:
    command = [
        ytdlp_binary(),
        "--no-playlist",
        "--max-downloads",
        "1",
        "--no-progress",
        "--no-warnings",
        "--merge-output-format",
        "mp4",
        "--output",
        str(output_dir / "source.%(ext)s"),
    ]
    if browser:
        command.extend(["--cookies-from-browser", browser])
    command.append(url)
    try:
        subprocess.run(
            command,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=300,
        )
    except subprocess.TimeoutExpired as exc:
        raise ConnectorError("本机下载超时，请稍后重试。") from exc
    return downloaded_media_path(output_dir)


def download_media(url: str) -> tuple[Path, tempfile.TemporaryDirectory[str]]:
    temporary_directory = tempfile.TemporaryDirectory(prefix="still-settling-")
    output_dir = Path(temporary_directory.name)
    try:
        media = download_attempt(url, output_dir, browser=None)
        if media is None:
            for browser in BROWSER_RETRY_ORDER:
                media = download_attempt(url, output_dir, browser=browser)
                if media is not None:
                    break
        if media is None:
            raise ConnectorError("本机浏览器会话没有返回可用的抖音视频。")
        if media.stat().st_size > MAX_MEDIA_BYTES:
            raise ConnectorError("视频超过 512 MB 上传限制。")
        return media, temporary_directory
    except Exception:
        temporary_directory.cleanup()
        raise


class ConnectorHandler(BaseHTTPRequestHandler):
    server_version = "StillSettlingConnector/1.0"

    def log_message(self, _format: str, *_args: object) -> None:
        # Do not write request URLs or downloader details to a shared terminal.
        return

    def origin_is_allowed(self) -> bool:
        origin = self.headers.get("Origin", "").rstrip("/")
        return bool(origin and origin in allowed_origins())

    def send_cors_headers(self) -> None:
        origin = self.headers.get("Origin", "").rstrip("/")
        if origin in allowed_origins():
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header(
                "Access-Control-Expose-Headers", "Content-Disposition, Content-Type"
            )

    def send_json(self, status: HTTPStatus, payload: dict[str, str]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        if not self.origin_is_allowed():
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/health" or not self.origin_is_allowed():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self.send_json(HTTPStatus.OK, {"status": "ready"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/extract":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not self.origin_is_allowed():
            self.send_json(HTTPStatus.FORBIDDEN, {"error": "来源页面未获授权。"})
            return
        try:
            declared_size = int(self.headers.get("Content-Length", "0"))
            if declared_size < 1 or declared_size > MAX_REQUEST_BYTES:
                raise ConnectorError("本机连接器请求无效。")
            payload = json.loads(self.rfile.read(declared_size))
            if not isinstance(payload, dict) or not isinstance(payload.get("url"), str):
                raise ConnectorError("本机连接器请求缺少抖音链接。")
            url = extract_douyin_url(payload["url"])
            media, temporary_directory = download_media(url)
        except (ConnectorError, ValueError, json.JSONDecodeError) as exc:
            self.send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(exc)})
            return

        try:
            content_type = mimetypes.guess_type(media.name)[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_cors_headers()
            self.send_header("Content-Type", content_type)
            self.send_header(
                "Content-Disposition", f'attachment; filename="{media.name}"'
            )
            self.send_header("Content-Length", str(media.stat().st_size))
            self.end_headers()
            with media.open("rb") as stream:
                shutil.copyfileobj(stream, self.wfile)
        finally:
            temporary_directory.cleanup()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start the Still Settling local connector.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), ConnectorHandler)
    print(f"Still Settling local connector listening on 127.0.0.1:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
