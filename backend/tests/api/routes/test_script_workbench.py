from fastapi.testclient import TestClient


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
