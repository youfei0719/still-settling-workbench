"""Single-host media extraction tasks for the CPM workbench.

The worker deliberately keeps media ephemeral. It runs on the same host as the
workbench API, limits itself to one download at a time, and returns only a
transcript for the normal workbench persistence flow.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib import error, request
from uuid import uuid4

from pydantic import BaseModel, Field

MediaTaskStatus = Literal["queued", "processing", "completed", "failed"]


class ServerMediaTaskRequest(BaseModel):
    url: str = Field(min_length=8, max_length=4096)


class ServerMediaTaskResult(BaseModel):
    source_url: str
    title: str = "抖音视频"
    author: str | None = None
    publish_time: str | None = None
    transcript: str
    timestamps: list[str] = Field(default_factory=list)
    provider: str


class ServerMediaTask(BaseModel):
    id: str
    source_url: str
    status: MediaTaskStatus
    stage: str
    stage_detail: str = ""
    progress: int = Field(default=0, ge=0, le=100)
    result: ServerMediaTaskResult | None = None
    error_code: str | None = None
    error: str | None = None
    retry_of: str | None = None
    created_at: datetime
    updated_at: datetime


class MediaTaskError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


TASKS: dict[str, ServerMediaTask] = {}
TASKS_LOCK = threading.Lock()
TASKS_LOADED = False
MEDIA_WORKER_LOCK = threading.BoundedSemaphore(1)


def now_utc() -> datetime:
    return datetime.now(UTC)


def task_data_dir() -> Path:
    configured = os.getenv("WORKBENCH_DATA_DIR", "").strip()
    root = (
        Path(configured).expanduser()
        if configured
        else Path.home() / ".local/share/douyin-script-workbench/public"
    )
    return root.resolve() / "media-tasks"


def task_state_path() -> Path:
    return task_data_dir() / "server-media-tasks.json"


def task_temp_dir() -> Path:
    """Keep ephemeral media below the workbench state directory, not /tmp."""
    directory = task_data_dir() / "temporary-media"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def persist_tasks() -> None:
    path = task_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"tasks": [task.model_dump(mode="json") for task in TASKS.values()]}
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def load_tasks() -> None:
    global TASKS_LOADED
    if TASKS_LOADED:
        return
    TASKS_LOADED = True
    path = task_state_path()
    if not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return
    for raw in payload.get("tasks", []):
        try:
            task = ServerMediaTask.model_validate(raw)
        except Exception:
            continue
        if task.status in {"queued", "processing"}:
            task = task.model_copy(
                update={
                    "status": "failed",
                    "stage": "任务因服务重启停止",
                    "progress": 100,
                    "error_code": "service_restarted",
                    "error": "主站重启后临时媒体已清理，请点击重试。",
                    "updated_at": now_utc(),
                }
            )
        TASKS[task.id] = task
    if TASKS:
        persist_tasks()


def update_task(task_id: str, **updates: object) -> ServerMediaTask:
    with TASKS_LOCK:
        task = TASKS[task_id].model_copy(update={**updates, "updated_at": now_utc()})
        TASKS[task_id] = task
        persist_tasks()
        return task


def normalize_douyin_url(value: str) -> str:
    match = re.search(r"https?://[^\s]+", value.strip())
    if not match:
        raise MediaTaskError(
            "invalid_url", "请输入完整的抖音分享文案或 v.douyin.com 链接。"
        )
    url = match.group(0).rstrip('，。；;,.!?！？")]}>')
    host_match = re.match(r"https?://([^/:]+)", url, re.I)
    host = host_match.group(1).lower() if host_match else ""
    if not (
        host == "douyin.com"
        or host.endswith(".douyin.com")
        or host.endswith(".iesdouyin.com")
    ):
        raise MediaTaskError("invalid_url", "当前仅支持 douyin.com 的分享链接。")
    return url


def configured_binary(env_name: str, default: str) -> str:
    configured = os.getenv(env_name, "").strip()
    executable = configured or shutil.which(default)
    if not executable:
        raise MediaTaskError(
            "runtime_missing",
            f"服务器未安装 {default}，请联系管理员完成主站媒体运行时安装。",
        )
    return executable


def download_timeout() -> int:
    try:
        return max(
            60, min(int(os.getenv("WORKBENCH_MEDIA_DOWNLOAD_TIMEOUT", "600")), 1800)
        )
    except ValueError:
        return 600


def media_max_filesize() -> str:
    """Return yt-dlp's file-size expression while bounding one low-memory host."""
    configured = os.getenv("WORKBENCH_MEDIA_MAX_FILESIZE", "350M").strip()
    return configured or "350M"


def transcription_max_audio_bytes() -> int:
    try:
        return max(
            1_000_000,
            min(
                int(os.getenv("WORKBENCH_TRANSCRIPTION_MAX_AUDIO_BYTES", "52428800")),
                200_000_000,
            ),
        )
    except ValueError:
        return 52_428_800


def download_media(url: str, directory: Path) -> Path:
    ytdlp = configured_binary("WORKBENCH_YTDLP_CMD", "yt-dlp")
    output_template = str(directory / "source.%(ext)s")
    command = [
        ytdlp,
        "--no-playlist",
        "--max-downloads",
        "1",
        "--no-progress",
        "--no-warnings",
        "--retries",
        "2",
        "--fragment-retries",
        "2",
        "--socket-timeout",
        "25",
        "--max-filesize",
        media_max_filesize(),
        "--format",
        "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720][ext=mp4]/b",
        "--merge-output-format",
        "mp4",
        "--write-info-json",
        "--output",
        output_template,
    ]
    proxy = os.getenv("WORKBENCH_MEDIA_PROXY", "").strip()
    if proxy:
        command.extend(["--proxy", proxy])
    command.append(url)
    try:
        subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=download_timeout(),
        )
    except subprocess.TimeoutExpired as exc:
        raise MediaTaskError(
            "download_timeout", "媒体下载超过任务时限，临时文件已清理。"
        ) from exc
    media = sorted(
        (
            path
            for path in directory.iterdir()
            if path.suffix.lower() in {".mp4", ".mkv", ".mov", ".webm", ".m4v"}
        ),
        key=lambda path: path.stat().st_size,
        reverse=True,
    )
    if media:
        return media[0]
    raise MediaTaskError(
        "download_failed",
        "服务器未能取得公开视频。请确认链接仍可公开访问后稍后重试。",
    )


def download_metadata(directory: Path) -> dict[str, str | None]:
    """Read only yt-dlp's temporary sidecar metadata, if it is available."""
    info_files = sorted(directory.glob("*.info.json"))
    if not info_files:
        return {"title": "抖音视频", "author": None, "publish_time": None}
    try:
        payload = json.loads(info_files[0].read_text(encoding="utf-8"))
    except OSError, ValueError:
        return {"title": "抖音视频", "author": None, "publish_time": None}
    if not isinstance(payload, dict):
        return {"title": "抖音视频", "author": None, "publish_time": None}
    title = str(payload.get("title") or "抖音视频").strip() or "抖音视频"
    author = (
        str(payload.get("uploader") or payload.get("creator") or "").strip() or None
    )
    publish_time = str(payload.get("upload_date") or "").strip() or None
    return {"title": title, "author": author, "publish_time": publish_time}


def extract_audio(media: Path, directory: Path) -> Path:
    ffmpeg = configured_binary("WORKBENCH_FFMPEG_CMD", "ffmpeg")
    audio = directory / "source.wav"
    try:
        completed = subprocess.run(
            [
                ffmpeg,
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
                str(audio),
            ],
            check=False,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=180,
        )
    except subprocess.TimeoutExpired as exc:
        raise MediaTaskError(
            "audio_timeout", "音频提取超过任务时限，临时文件已清理。"
        ) from exc
    if completed.returncode != 0 or not audio.exists():
        raise MediaTaskError("audio_failed", "服务器无法从该视频提取可转写的音频。")
    return audio


def transcription_config() -> tuple[str, str, str]:
    api_base = os.getenv("WORKBENCH_TRANSCRIPTION_API_BASE", "").strip().rstrip("/")
    model = os.getenv("WORKBENCH_TRANSCRIPTION_MODEL", "").strip()
    api_key = os.getenv("WORKBENCH_TRANSCRIPTION_API_KEY", "").strip()
    if not api_base or not model or not api_key:
        raise MediaTaskError(
            "transcription_unconfigured",
            "主站下载已就绪，但尚未配置支持 audio/transcriptions 的转写 API；当前文本模型中转站不能转写音频。",
        )
    return api_base, model, api_key


def multipart_body(audio: Path, model: str) -> tuple[bytes, str]:
    if audio.stat().st_size > transcription_max_audio_bytes():
        raise MediaTaskError(
            "audio_too_large",
            "视频音频超过本次转写大小上限，请使用更短的公开视频或补充字幕文本。",
        )
    boundary = f"----stillSettling{uuid4().hex}"
    chunks = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="model"\r\n\r\n{model}\r\n'.encode(),
        f'--{boundary}\r\nContent-Disposition: form-data; name="language"\r\n\r\nzh\r\n'.encode(),
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="source.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode(),
        audio.read_bytes(),
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    return b"".join(chunks), boundary


def transcribe_audio(audio: Path) -> ServerMediaTaskResult:
    api_base, model, api_key = transcription_config()
    body, boundary = multipart_body(audio, model)
    endpoint = f"{api_base}/audio/transcriptions"
    req = request.Request(
        endpoint,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=180) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        raise MediaTaskError(
            "transcription_failed", f"转写 API 返回 HTTP {exc.code}。"
        ) from exc
    except (error.URLError, TimeoutError, ValueError) as exc:
        raise MediaTaskError(
            "transcription_failed", "转写 API 未返回有效文稿。"
        ) from exc
    text = str(payload.get("text") or "").strip() if isinstance(payload, dict) else ""
    if len(text) < 10:
        raise MediaTaskError(
            "transcription_failed", "转写 API 未返回足够的可分析文稿。"
        )
    timestamps: list[str] = []
    if isinstance(payload, dict) and isinstance(payload.get("segments"), list):
        timestamps = [
            f"{segment.get('start', 0)}-{segment.get('end', 0)} {str(segment.get('text') or '').strip()}"
            for segment in payload["segments"]
            if isinstance(segment, dict) and str(segment.get("text") or "").strip()
        ]
    return ServerMediaTaskResult(
        source_url="",
        transcript=text,
        timestamps=timestamps,
        provider=f"外部转写 API（{model}）",
    )


def run_task(task_id: str) -> None:
    with MEDIA_WORKER_LOCK:
        task = TASKS[task_id]
        try:
            # Fail before downloading when the only supported transcription path is absent.
            transcription_config()
            update_task(
                task_id,
                status="processing",
                stage="服务器正在下载视频",
                stage_detail="媒体仅在主站临时目录中处理。",
                progress=15,
            )
            with tempfile.TemporaryDirectory(
                prefix="task-", dir=task_temp_dir()
            ) as temp_dir:
                directory = Path(temp_dir)
                media = download_media(task.source_url, directory)
                metadata = download_metadata(directory)
                update_task(task_id, stage="服务器正在提取音频", progress=50)
                audio = extract_audio(media, directory)
                update_task(task_id, stage="外部转写服务正在识别文稿", progress=72)
                result = transcribe_audio(audio).model_copy(
                    update={"source_url": task.source_url, **metadata}
                )
            update_task(
                task_id,
                status="completed",
                stage="真实文稿已准备完成",
                stage_detail="视频和音频已从服务器临时目录清理。",
                progress=100,
                result=result,
            )
        except MediaTaskError as exc:
            update_task(
                task_id,
                status="failed",
                stage="媒体任务未完成",
                progress=100,
                error_code=exc.code,
                error=str(exc),
            )
        except Exception:
            update_task(
                task_id,
                status="failed",
                stage="媒体任务未完成",
                progress=100,
                error_code="unexpected_error",
                error="媒体任务发生未预期错误，临时文件已清理。",
            )


def create_server_media_task(
    payload: ServerMediaTaskRequest, retry_of: str | None = None
) -> ServerMediaTask:
    load_tasks()
    source_url = normalize_douyin_url(payload.url)
    with TASKS_LOCK:
        active = next(
            (
                task
                for task in TASKS.values()
                if task.source_url == source_url
                and task.status in {"queued", "processing"}
            ),
            None,
        )
        if active:
            return active
        now = now_utc()
        task = ServerMediaTask(
            id=f"media_{uuid4().hex[:12]}",
            source_url=source_url,
            status="queued",
            stage="等待服务器媒体任务",
            stage_detail="任务会按单并发顺序处理，媒体不会写入历史记录。",
            created_at=now,
            updated_at=now,
            retry_of=retry_of,
        )
        TASKS[task.id] = task
        persist_tasks()
    threading.Thread(
        target=run_task, args=(task.id,), daemon=True, name=f"server-media-{task.id}"
    ).start()
    return task


def get_server_media_task(task_id: str) -> ServerMediaTask:
    load_tasks()
    if task_id not in TASKS:
        raise KeyError(task_id)
    return TASKS[task_id]


def list_server_media_tasks(limit: int = 20) -> list[ServerMediaTask]:
    load_tasks()
    return sorted(TASKS.values(), key=lambda task: task.updated_at, reverse=True)[
        : max(1, min(limit, 100))
    ]


def retry_server_media_task(task_id: str) -> ServerMediaTask:
    task = get_server_media_task(task_id)
    return create_server_media_task(
        ServerMediaTaskRequest(url=task.source_url), retry_of=task.id
    )
