from fastapi.testclient import TestClient


def test_workbench_rejects_cloud_video_uploads(client: TestClient) -> None:
    response = client.post(
        "/api/v1/script-workbench/upload-video?file_name=sample.txt",
        content=b"not a video",
        headers={"content-type": "text/plain"},
    )

    assert response.status_code == 410
    assert "本机连接器" in response.json()["detail"]


def test_workbench_rejects_cloud_link_tasks(client: TestClient) -> None:
    response = client.post(
        "/api/v1/script-workbench/link-task",
        json={"url": "https://v.douyin.com/demo/"},
    )

    assert response.status_code == 410
    assert "服务器只接收文稿" in response.json()["detail"]
