from fastapi.testclient import TestClient


def test_workbench_video_upload_keeps_local_connector_source_context(
    client: TestClient, monkeypatch
) -> None:
    from datetime import datetime, timezone

    from app.api.routes import script_workbench as workbench_route
    from app.script_workbench import SourceVideo, VideoUploadResponse

    captured: dict[str, object] = {}

    def fake_create_video_upload_result(
        file_name, material_path, *, run_extractors=False, context_text="", source_url=None
    ):
        captured.update(
            {
                "file_name": file_name,
                "material_path": material_path,
                "run_extractors": run_extractors,
                "context_text": context_text,
                "source_url": source_url,
            }
        )
        return VideoUploadResponse(
            source_video=SourceVideo(
                id="source_connector_test",
                input_type="video",
                title=file_name,
                url=source_url,
                status="needs_upload",
                created_at=datetime.now(timezone.utc),
            ),
            extraction_status="skipped",
            asr_status="skipped",
            ocr_status="skipped",
            message="视频已保存。",
            asr_message="ASR 未运行。",
            ocr_message="OCR 未运行。",
            next_step="继续处理。",
            fallback_inputs=[],
        )

    monkeypatch.setattr(
        workbench_route, "create_video_upload_result", fake_create_video_upload_result
    )

    response = client.post(
        "/api/v1/script-workbench/upload-video?file_name=connector.mp4"
        "&run_extractors=true&source_url=https%3A%2F%2Fv.douyin.com%2Fdemo%2F"
        "&context_text=share%20https%3A%2F%2Fv.douyin.com%2Fdemo%2F",
        content=b"video",
        headers={"content-type": "video/mp4"},
    )

    assert response.status_code == 200
    assert captured["run_extractors"] is True
    assert captured["source_url"] == "https://v.douyin.com/demo/"
    assert captured["context_text"] == "share https://v.douyin.com/demo/"


def test_workbench_rejects_oversized_video_before_reading_body(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setenv("WORKBENCH_MAX_VIDEO_UPLOAD_BYTES", "1")

    response = client.post(
        "/api/v1/script-workbench/upload-video?file_name=sample.mp4",
        content=b"12",
        headers={"content-type": "video/mp4"},
    )

    assert response.status_code == 413
    assert "不能超过" in response.json()["detail"]


def test_workbench_rejects_unsupported_video_type(client: TestClient) -> None:
    response = client.post(
        "/api/v1/script-workbench/upload-video?file_name=sample.txt",
        content=b"not a video",
        headers={"content-type": "text/plain"},
    )

    assert response.status_code == 415
