#!/usr/bin/env python3
"""Local-only media and transcription connector for the Still Settling workbench.

The connector deliberately keeps browser cookies and media on the user's
computer. It returns only the resulting transcript to the workbench page;
videos, audio and frames never cross into the cloud workbench service.
"""

from __future__ import annotations

import argparse
import json
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
DOWNLOAD_TIMEOUT_SECONDS: Final = 180
DOWNLOAD_SOCKET_TIMEOUT_SECONDS: Final = 25
TRANSCRIPTION_TIMEOUT_SECONDS: Final = 600
PREFERRED_MP4_FORMAT: Final = (
    "bv*[ext=mp4][vcodec^=avc1]+ba[ext=m4a]/"
    "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b"
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
    url = match.group(0).rstrip('，。；;,.!?！？”’")]}>')
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


def proxy_from_scutil(output: str) -> str | None:
    values = dict(re.findall(r"^\s*([A-Za-z]+)\s*:\s*(.+?)\s*$", output, re.M))
    if values.get("HTTPEnable") != "1":
        return None
    host = values.get("HTTPProxy", "")
    port = values.get("HTTPPort", "")
    if not host or not port.isdecimal() or not 1 <= int(port) <= 65535:
        return None
    return f"http://{host}:{port}"


def system_http_proxy() -> str | None:
    """Read, but never change, the macOS HTTP proxy used by desktop apps."""
    try:
        result = subprocess.run(
            ["/usr/sbin/scutil", "--proxy"],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proxy_from_scutil(result.stdout)


def download_attempt(
    url: str, output_dir: Path, browser: str | None, proxy: str | None = None
) -> Path | None:
    command = [
        ytdlp_binary(),
        "--no-playlist",
        "--max-downloads",
        "1",
        "--no-progress",
        "--no-warnings",
        "--retries",
        "2",
        "--fragment-retries",
        "2",
        "--retry-sleep",
        "http:linear=1:2",
        "--socket-timeout",
        str(DOWNLOAD_SOCKET_TIMEOUT_SECONDS),
        "--format",
        PREFERRED_MP4_FORMAT,
        "--merge-output-format",
        "mp4",
        "--output",
        str(output_dir / "source.%(ext)s"),
    ]
    if browser:
        command.extend(["--cookies-from-browser", browser])
    if proxy:
        command.extend(["--proxy", proxy])
    command.append(url)
    try:
        subprocess.run(
            command,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=DOWNLOAD_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise ConnectorError("本机下载超时，请稍后重试。") from exc
    return downloaded_media_path(output_dir)


def download_media(url: str) -> tuple[Path, tempfile.TemporaryDirectory[str]]:
    temporary_directory = tempfile.TemporaryDirectory(prefix="still-settling-")
    output_dir = Path(temporary_directory.name)
    try:
        # Public links must work without requiring a Douyin account. Use the
        # anonymous downloader first; a local browser visitor session is only a
        # best-effort recovery for a temporary anti-bot response and is never
        # sent to the workbench server.
        proxy = system_http_proxy()
        media = download_attempt(url, output_dir, browser=None, proxy=proxy)
        if media is None:
            for browser in BROWSER_RETRY_ORDER:
                media = download_attempt(url, output_dir, browser=browser, proxy=proxy)
                if media is not None:
                    break
        if media is None:
            raise ConnectorError(
                "抖音暂未接受本机的匿名访问，已自动重试；无需登录，请稍后重试。"
            )
        if media.stat().st_size > MAX_MEDIA_BYTES:
            raise ConnectorError("视频超过 512 MB 上传限制。")
        return media, temporary_directory
    except Exception:
        temporary_directory.cleanup()
        raise


def ffmpeg_binary() -> str:
    configured = os.getenv("STILL_SETTLING_FFMPEG", "").strip()
    candidates = [
        configured,
        shutil.which("ffmpeg") or "",
        "/opt/homebrew/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
    ]
    for executable in candidates:
        if executable and Path(executable).is_file() and os.access(executable, os.X_OK):
            return executable
    raise ConnectorError("本机未找到 FFmpeg，无法从视频生成转写音频。")


def project_root() -> Path | None:
    configured = os.getenv("STILL_SETTLING_PROJECT_ROOT", "").strip()
    candidates = [configured, str(Path(__file__).resolve().parents[1])]
    for candidate in candidates:
        root = Path(candidate).expanduser()
        if (root / "backend" / "scripts" / "workbench_model_worker.py").is_file():
            return root
    return None


def model_python(root: Path | None) -> str:
    configured = os.getenv("STILL_SETTLING_MODEL_PYTHON", "").strip()
    candidates = [configured]
    if root is not None:
        candidates.append(str(root / ".venv-model" / "bin" / "python"))
    for executable in candidates:
        if executable and Path(executable).is_file() and os.access(executable, os.X_OK):
            return executable
    raise ConnectorError(
        "本机转写模型未准备好。请在工作台项目目录运行 npm run model-env:workbench 后重试。"
    )


def extract_audio(media: Path, output_dir: Path) -> Path:
    audio_path = output_dir / "source.wav"
    command = [
        ffmpeg_binary(),
        "-y",
        "-i",
        str(media),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(audio_path),
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        raise ConnectorError("本机 FFmpeg 抽取音频超时，请稍后重试。") from exc
    if completed.returncode != 0 or not audio_path.exists():
        detail = (completed.stderr or "").strip()[-180:]
        raise ConnectorError(f"本机 FFmpeg 未能抽取音频。{detail}")
    return audio_path


def transcribe_media(media: Path, output_dir: Path) -> dict[str, object]:
    root = project_root()
    if root is None:
        raise ConnectorError(
            "本机连接器未找到工作台项目，无法启动本地转写。请重新安装连接器。"
        )
    audio = extract_audio(media, output_dir)
    result_path = output_dir / "transcript.json"
    environment = {
        **os.environ,
        "WORKBENCH_ASR_MODE": "required",
        "WORKBENCH_OCR_MODE": "off",
    }
    command = [
        model_python(root),
        str(root / "backend" / "scripts" / "workbench_model_worker.py"),
        "--kind",
        "asr",
        "--input",
        str(audio),
        "--output",
        str(result_path),
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=TRANSCRIPTION_TIMEOUT_SECONDS,
            env=environment,
        )
    except subprocess.TimeoutExpired as exc:
        raise ConnectorError("本机转写超时，临时媒体已清理，请稍后重试。") from exc
    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        detail = (completed.stderr or completed.stdout or "").strip()[-180:]
        raise ConnectorError(f"本机转写进程没有返回有效结果。{detail}") from exc
    if not isinstance(payload, dict) or completed.returncode != 0:
        detail = (
            str(payload.get("error", "本机转写执行失败。"))
            if isinstance(payload, dict)
            else ""
        )
        raise ConnectorError(f"本机转写未完成。{detail[:180]}")
    text = str(payload.get("text") or "").strip()
    if payload.get("status") != "completed" or len(text) < 10:
        message = str(payload.get("message") or "本机没有得到足够的可分析文稿。")
        raise ConnectorError(message)
    return {
        "text": text,
        "timestamps": payload.get("timestamps")
        if isinstance(payload.get("timestamps"), list)
        else [],
        "provider": str(payload.get("provider") or "FunASR"),
    }


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
            if self.headers.get("Access-Control-Request-Private-Network") == "true":
                self.send_header("Access-Control-Allow-Private-Network", "true")
            self.send_header(
                "Access-Control-Expose-Headers", "Content-Disposition, Content-Type"
            )

    def send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
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
        if self.path != "/v1/extract-and-transcribe":
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
            source_input = payload["url"]
            url = extract_douyin_url(source_input)
            media, temporary_directory = download_media(url)
        except (ConnectorError, ValueError, json.JSONDecodeError) as exc:
            self.send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(exc)})
            return

        try:
            transcript = transcribe_media(media, Path(temporary_directory.name))
            self.send_json(
                HTTPStatus.OK,
                {
                    "source_url": url,
                    "title": "本机转写的抖音视频",
                    "text": transcript["text"],
                    "timestamps": transcript["timestamps"],
                    "provider": transcript["provider"],
                    "media_retention": "deleted_after_transcription",
                    "message": "视频、音频和浏览器会话仅在本机临时处理，已在转写后清理；云端仅接收文稿。",
                },
            )
        except ConnectorError as exc:
            self.send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(exc)})
        finally:
            temporary_directory.cleanup()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start the Still Settling local connector."
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), ConnectorHandler)
    print(f"Still Settling local connector listening on 127.0.0.1:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
