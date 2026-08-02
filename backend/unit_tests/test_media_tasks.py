import json
import time

from app import media_tasks


def reset_task_state(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WORKBENCH_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(media_tasks, "TASKS", {})
    monkeypatch.setattr(media_tasks, "TASKS_LOADED", True)


def wait_for_completion(task_id: str) -> media_tasks.ServerMediaTask:
    for _ in range(100):
        task = media_tasks.get_server_media_task(task_id)
        if task.status in {"completed", "failed"}:
            return task
        time.sleep(0.01)
    raise AssertionError("media task did not finish")


def test_server_media_task_returns_only_transcript(monkeypatch, tmp_path) -> None:
    reset_task_state(monkeypatch, tmp_path)

    def fake_download(_url, directory):
        media = directory / "source.mp4"
        media.write_bytes(b"video")
        return media

    def fake_extract(_media, directory):
        audio = directory / "source.wav"
        audio.write_bytes(b"audio")
        return audio

    def fake_transcribe(_audio):
        return media_tasks.ServerMediaTaskResult(
            source_url="",
            transcript="这是由外部转写 API 返回的真实视频口播文稿。",
            timestamps=["0-2 这是由外部转写 API 返回的真实视频口播文稿。"],
            provider="外部转写 API（whisper-1）",
        )

    monkeypatch.setattr(media_tasks, "download_media", fake_download)
    monkeypatch.setattr(media_tasks, "extract_audio", fake_extract)
    monkeypatch.setattr(media_tasks, "transcribe_audio", fake_transcribe)
    monkeypatch.setattr(
        media_tasks,
        "transcription_config",
        lambda: ("https://asr.example.test/v1", "whisper-1", "test-key"),
    )

    task = media_tasks.create_server_media_task(
        media_tasks.ServerMediaTaskRequest(
            url="分享文案 https://v.douyin.com/test-media/"
        )
    )
    completed = wait_for_completion(task.id)

    assert completed.status == "completed"
    assert completed.result is not None
    assert completed.result.source_url == "https://v.douyin.com/test-media/"
    assert "真实视频口播文稿" in completed.result.transcript
    assert not list(tmp_path.rglob("*.mp4"))
    assert not list(tmp_path.rglob("*.wav"))


def test_transcription_requires_an_audio_api(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("WORKBENCH_TRANSCRIPTION_API_BASE", raising=False)
    monkeypatch.delenv("WORKBENCH_TRANSCRIPTION_MODEL", raising=False)
    monkeypatch.delenv("WORKBENCH_TRANSCRIPTION_API_KEY", raising=False)
    audio = tmp_path / "source.wav"
    audio.write_bytes(b"audio")

    try:
        media_tasks.transcribe_audio(audio)
    except media_tasks.MediaTaskError as exc:
        assert exc.code == "transcription_unconfigured"
    else:
        raise AssertionError("expected an explicit audio API configuration error")


def test_download_metadata_is_read_from_ephemeral_ytdlp_sidecar(tmp_path) -> None:
    (tmp_path / "source.info.json").write_text(
        json.dumps(
            {
                "title": "真实标题",
                "uploader": "真实作者",
                "upload_date": "20260803",
            }
        ),
        encoding="utf-8",
    )

    assert media_tasks.download_metadata(tmp_path) == {
        "title": "真实标题",
        "author": "真实作者",
        "publish_time": "20260803",
    }
