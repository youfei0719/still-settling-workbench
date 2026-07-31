from __future__ import annotations

import argparse
import json
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = ROOT / "evals" / "workbench" / "video-smoke-report.json"
SAMPLE_PATH = Path("/tmp/douyin-script-workbench-smoke.mp4")
SPOKEN_SAMPLE_TEXT = "今天我们只根据公开信息复盘这件事，先讲清时间线，再讨论大家真正关心的问题。"


def run(command: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)


def chinese_font_path() -> Path | None:
    candidates = [
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
        Path("/System/Library/Fonts/STHeiti Medium.ttc"),
        Path("/System/Library/Fonts/Supplemental/Songti.ttc"),
    ]
    return next((candidate for candidate in candidates if candidate.exists()), None)


def make_sample_video(path: Path) -> dict[str, Any]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return {
            "passed": False,
            "status": "missing",
            "detail": "PATH 中未找到 FFmpeg，无法生成样例视频。",
        }

    path.parent.mkdir(parents=True, exist_ok=True)
    result = run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=320x180:rate=2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=1000:sample_rate=16000",
            "-t",
            "1",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ]
    )
    if result.returncode != 0 or not path.exists() or path.stat().st_size == 0:
        return {
            "passed": False,
            "status": "failed",
            "detail": (result.stderr or result.stdout or "FFmpeg 未生成有效视频。").strip(),
        }
    return {
        "passed": True,
        "status": "completed",
        "detail": f"样例视频已生成：{path}，大小 {path.stat().st_size} bytes。",
    }


def make_spoken_sample_video(path: Path) -> dict[str, Any]:
    ffmpeg = shutil.which("ffmpeg")
    say = shutil.which("say")
    font_path = chinese_font_path()
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        Image = ImageDraw = ImageFont = None  # type: ignore[assignment]
    if not ffmpeg or not say or font_path is None or Image is None or ImageDraw is None or ImageFont is None:
        missing = [name for name, available in [("FFmpeg", ffmpeg), ("macOS say", say), ("中文字体", font_path), ("Pillow", Image)] if not available]
        return {
            "passed": False,
            "status": "missing",
            "detail": f"无法生成中文口播样例，缺少：{'、'.join(missing)}。",
        }

    path.parent.mkdir(parents=True, exist_ok=True)
    speech_path = path.with_suffix(".aiff")
    subtitle_frame_path = path.with_suffix(".png")
    speech = run([say, "-v", "Tingting", "-o", str(speech_path), SPOKEN_SAMPLE_TEXT])
    if speech.returncode != 0 or not speech_path.exists() or speech_path.stat().st_size == 0:
        return {
            "passed": False,
            "status": "failed",
            "detail": (speech.stderr or speech.stdout or "macOS say 未生成有效中文语音。").strip(),
        }

    frame = Image.new("RGB", (720, 1280), "white")
    draw = ImageDraw.Draw(frame)
    font = ImageFont.truetype(str(font_path), 42)
    draw.multiline_text((84, 550), SPOKEN_SAMPLE_TEXT, font=font, fill="black", spacing=18, align="left")
    frame.save(subtitle_frame_path)

    video = run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-loop",
            "1",
            "-framerate",
            "25",
            "-i",
            str(subtitle_frame_path),
            "-i",
            str(speech_path),
            "-t",
            "5",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ]
    )
    if video.returncode != 0 or not path.exists() or path.stat().st_size == 0:
        return {
            "passed": False,
            "status": "failed",
            "detail": (video.stderr or video.stdout or "FFmpeg 未生成有效中文口播视频。").strip(),
        }
    return {
        "passed": True,
        "status": "completed",
        "detail": "已生成自有中文口播和硬字幕样例，用于验证 FunASR、PaddleOCR 与统一文本入口。",
    }


def upload_video(api_base: str, path: Path, timeout: int, run_extractors: bool) -> dict[str, Any]:
    url = (
        f"{api_base.rstrip('/')}/api/v1/script-workbench/upload-video"
        f"?file_name={path.name}&run_extractors={'true' if run_extractors else 'false'}"
    )
    request = urllib.request.Request(
        url,
        data=path.read_bytes(),
        headers={"Content-Type": "application/octet-stream"},
        method="POST",
    )
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
        return {
            "passed": False,
            "status": "failed",
            "detail": f"无法访问轻量 API：{exc}",
        }

    extraction_ok = payload.get("extraction_status") == "completed"
    audio_path = payload.get("audio_path")
    audio_ok = bool(audio_path and Path(audio_path).exists())
    frame_paths = payload.get("frame_paths") or []
    frame_ok = bool(frame_paths)
    media_cleaned = payload.get("media_cleanup_status") == "completed"
    passed = extraction_ok and (media_cleaned or (audio_ok and frame_ok))
    return {
        "passed": passed,
        "status": "completed" if passed else "failed",
        "detail": "视频上传链路已完成抽音频和关键帧。" if passed else "视频上传链路未完整完成。",
        "response": {
            "run_extractors": run_extractors,
            "source_id": payload.get("source_video", {}).get("id"),
            "source_status": payload.get("source_video", {}).get("status"),
            "extraction_status": payload.get("extraction_status"),
            "audio_path": audio_path,
            "frame_count": len(frame_paths),
            "asr_status": payload.get("asr_status"),
            "asr_text": payload.get("asr_text"),
            "asr_message": payload.get("asr_message"),
            "ocr_status": payload.get("ocr_status"),
            "ocr_text": payload.get("ocr_text"),
            "ocr_message": payload.get("ocr_message"),
            "transcript": payload.get("transcript"),
            "next_step": payload.get("next_step"),
            "media_cleanup_status": payload.get("media_cleanup_status"),
            "media_cleanup_message": payload.get("media_cleanup_message"),
            "source_video": payload.get("source_video"),
        },
    }


def verify_content_extractors(upload: dict[str, Any]) -> dict[str, Any]:
    response = upload.get("response", {})
    asr_text = str(response.get("asr_text") or "").strip()
    ocr_text = str(response.get("ocr_text") or "").strip()
    transcript = response.get("transcript") or {}
    checks = {
        "asr_completed": response.get("asr_status") == "completed",
        "asr_has_text": len(asr_text) >= 10,
        "ocr_completed": response.get("ocr_status") == "completed",
        "ocr_has_text": len(ocr_text) >= 4,
        "unified_transcript_created": bool(transcript) and len(str(transcript.get("content_text") or "")) >= 10,
        "media_cleanup_completed": response.get("media_cleanup_status") == "completed",
        "media_paths_removed": not (response.get("source_video") or {}).get("material_path") and not response.get("audio_path") and not response.get("frame_paths"),
    }
    return {
        "passed": all(checks.values()),
        "status": "completed" if all(checks.values()) else "failed",
        "detail": "中文口播与硬字幕均已提取为统一可分析文本。" if all(checks.values()) else "中文内容提取未完整通过，请检查模型加载、ASR/OCR 输出或上传兜底。",
        "response": {
            "asr_status": response.get("asr_status"),
            "asr_text_length": len(asr_text),
            "ocr_status": response.get("ocr_status"),
            "ocr_text_length": len(ocr_text),
            "has_transcript": bool(transcript),
            "media_cleanup_status": response.get("media_cleanup_status"),
        },
        "checks": checks,
    }


def verify_analysis_from_transcript(api_base: str, upload: dict[str, Any], timeout: int) -> dict[str, Any]:
    response = upload.get("response", {})
    transcript = response.get("transcript") or {}
    content = str(transcript.get("content_text") or "").strip()
    if len(content) < 10:
        return {
            "passed": False,
            "status": "skipped",
            "detail": "统一转写文本不足，无法验证结构分析入口。",
        }

    request = urllib.request.Request(
        f"{api_base.rstrip('/')}/api/v1/script-workbench/analyze-text",
        data=json.dumps({
            "title": "自有中文口播视频验证",
            "content": content,
            "input_type": "transcript",
        }).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        analysis = request_json(request, timeout=timeout)
    except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
        return {
            "passed": False,
            "status": "failed",
            "detail": f"统一转写无法进入结构分析：{exc}",
        }

    structure = analysis.get("analysis", {}).get("structure") or []
    preview = analysis.get("generated_preview") or {}
    checks = {
        "input_is_transcript": analysis.get("transcript", {}).get("source") == "transcript",
        "has_hook": bool(analysis.get("analysis", {}).get("hook")),
        "has_structure": len(structure) >= 5,
        "has_template": bool(analysis.get("preset_draft", {}).get("skeleton")),
        "has_shootable_script": len(str(preview.get("spoken_script") or "")) >= 120 and len(preview.get("shot_suggestions") or []) >= 3,
    }
    return {
        "passed": all(checks.values()),
        "status": "completed" if all(checks.values()) else "failed",
        "detail": "自有视频的统一转写已完成结构分析，并生成可拍摄脚本。" if all(checks.values()) else "统一转写进入结构分析后未得到完整结果。",
        "response": {
            "structure_count": len(structure),
            "script_length": len(str(preview.get("spoken_script") or "")),
            "shot_count": len(preview.get("shot_suggestions") or []),
        },
        "checks": checks,
    }
def request_json(request: urllib.request.Request, timeout: int) -> dict[str, Any]:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def verify_background_extraction(
    api_base: str,
    upload: dict[str, Any],
    timeout: int,
    run_asr: bool = False,
    run_ocr: bool = False,
) -> dict[str, Any]:
    source_id = upload.get("response", {}).get("source_id")
    if not source_id:
        return {
            "passed": False,
            "status": "skipped",
            "detail": "上传响应缺少 source_id，无法验证后台提取任务。",
        }

    base = api_base.rstrip()
    payload = json.dumps({"run_asr": run_asr, "run_ocr": run_ocr}).encode("utf-8")
    start_request = urllib.request.Request(
        f"{base}/api/v1/script-workbench/video-extraction-tasks/{source_id}",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        task = request_json(start_request, timeout=timeout)
        deadline = time.monotonic() + timeout
        while task.get("status") in {"queued", "processing"} and time.monotonic() < deadline:
            time.sleep(0.3)
            task = request_json(
                urllib.request.Request(f"{base}/api/v1/script-workbench/video-extraction-tasks/{task.get('id')}"),
                timeout=timeout,
            )
    except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
        return {
            "passed": False,
            "status": "failed",
            "detail": f"后台提取任务接口不可用：{exc}",
        }

    passed = task.get("status") == "completed" and task.get("progress") == 100 and bool(task.get("video_upload"))
    return {
        "passed": passed,
        "status": task.get("status", "failed"),
        "detail": "后台提取任务可创建、轮询并完成。" if passed else "后台提取任务未完成。",
        "response": {
            "task_id": task.get("id"),
            "source_id": source_id,
            "stage": task.get("stage"),
            "progress": task.get("progress"),
            "asr_status": task.get("asr_status"),
            "ocr_status": task.get("ocr_status"),
            "has_video_upload": bool(task.get("video_upload")),
            "video_upload": task.get("video_upload"),
        },
    }


def verify_task_management(api_base: str, background: dict[str, Any], timeout: int) -> dict[str, Any]:
    task_id = background.get("response", {}).get("task_id")
    if not task_id:
        return {
            "passed": False,
            "status": "skipped",
            "detail": "缺少后台任务 id，无法验证任务管理接口。",
        }

    base = api_base.rstrip()
    try:
        tasks = request_json(
            urllib.request.Request(f"{base}/api/v1/script-workbench/video-extraction-tasks?limit=10"),
            timeout=timeout,
        )
        listed = any(task.get("id") == task_id for task in tasks)
        cancel_response = request_json(
            urllib.request.Request(
                f"{base}/api/v1/script-workbench/video-extraction-tasks/{task_id}/cancel",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST",
            ),
            timeout=timeout,
        )
        media_cleaned = (background.get("response", {}).get("video_upload") or {}).get("media_cleanup_status") == "completed"
        retry_request = urllib.request.Request(
            f"{base}/api/v1/script-workbench/video-extraction-tasks/{task_id}/retry",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        if media_cleaned:
            try:
                request_json(retry_request, timeout=timeout)
                retry_response = {"blocked_after_cleanup": False}
            except urllib.error.HTTPError as exc:
                retry_response = {"blocked_after_cleanup": exc.code == 409}
            retried = retry_response
        else:
            retry_response = request_json(retry_request, timeout=timeout)
            retried = retry_response
            deadline = time.monotonic() + timeout
            while retried.get("status") in {"queued", "processing"} and time.monotonic() < deadline:
                time.sleep(0.3)
                retried = request_json(
                    urllib.request.Request(f"{base}/api/v1/script-workbench/video-extraction-tasks/{retry_response.get('id')}"),
                    timeout=timeout,
                )
    except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
        return {
            "passed": False,
            "status": "failed",
            "detail": f"任务管理接口不可用：{exc}",
        }

    passed = (
        listed
        and cancel_response.get("id") == task_id
        and (
            retry_response.get("blocked_after_cleanup")
            if media_cleaned
            else retry_response.get("retry_of") == task_id and retried.get("status") in {"completed", "failed", "cancelled"}
        )
    )
    return {
        "passed": passed,
        "status": "completed" if passed else "failed",
        "detail": "任务列表、取消和重试接口可用；完成转写后会阻止对已清理素材重试。" if passed else "任务管理接口验证未通过。",
        "response": {
            "listed": listed,
            "cancel_status": cancel_response.get("status"),
            "retry_task_id": retry_response.get("id"),
            "retry_of": retry_response.get("retry_of"),
            "retry_final_status": retried.get("status"),
            "retry_blocked_after_cleanup": retry_response.get("blocked_after_cleanup"),
        },
    }


def verify_model_runtime(api_base: str, timeout: int) -> dict[str, Any]:
    base = api_base.rstrip()
    try:
        status = request_json(
            urllib.request.Request(f"{base}/api/v1/script-workbench/model-status"),
            timeout=timeout,
        )
        warmup = request_json(
            urllib.request.Request(
                f"{base}/api/v1/script-workbench/model-warmup",
                data=json.dumps({"run_asr": True, "run_ocr": False, "execute": False}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            ),
            timeout=timeout,
        )
    except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
        return {
            "passed": False,
            "status": "failed",
            "detail": f"模型状态接口不可用：{exc}",
        }

    keys = {item.get("key") for item in status.get("items", [])}
    passed = keys == {"asr", "ocr"} and warmup.get("executed") is False
    return {
        "passed": passed,
        "status": "completed" if passed else "failed",
        "detail": "模型状态和非执行预热检查接口可用。" if passed else "模型状态接口响应不完整。",
        "response": {
            "keys": sorted(keys),
            "ready_count": status.get("ready_count"),
            "warmup_executed": warmup.get("executed"),
            "message": warmup.get("message"),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a local video upload smoke test for the workbench API.")
    parser.add_argument("--api-base", default="http://127.0.0.1:8000")
    parser.add_argument("--sample", type=Path, default=SAMPLE_PATH)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--run-extractors", action="store_true")
    parser.add_argument("--with-spoken-content", action="store_true", help="生成自有中文口播和硬字幕样例，并要求 ASR/OCR 返回可分析文本。")
    args = parser.parse_args()

    sample = make_spoken_sample_video(args.sample) if args.with_spoken_content else make_sample_video(args.sample)
    # Website uploads always stay light; ASR/OCR run in the background task after the file is saved.
    run_extractors = False
    upload = upload_video(args.api_base, args.sample, args.timeout, run_extractors) if sample["passed"] else {
        "passed": False,
        "status": "skipped",
        "detail": "样例视频生成失败，跳过上传。",
    }
    background = verify_background_extraction(
        args.api_base,
        upload,
        args.timeout,
        run_asr=args.run_extractors or args.with_spoken_content,
        run_ocr=args.run_extractors or args.with_spoken_content,
    ) if upload.get("passed") else {
        "passed": False,
        "status": "skipped",
        "detail": "上传未通过，跳过后台提取任务验证。",
    }
    task_management = verify_task_management(args.api_base, background, args.timeout) if background.get("passed") else {
        "passed": False,
        "status": "skipped",
        "detail": "后台任务未通过，跳过任务管理接口验证。",
    }
    model_runtime = verify_model_runtime(args.api_base, args.timeout)
    extracted_upload = {"response": background.get("response", {}).get("video_upload") or {}}
    content_extraction = verify_content_extractors(extracted_upload) if args.with_spoken_content and background.get("passed") else {
        "passed": not args.with_spoken_content,
        "status": "skipped",
        "detail": "未请求中文口播内容提取验证。",
    }
    content_analysis = verify_analysis_from_transcript(args.api_base, extracted_upload, args.timeout) if args.with_spoken_content and content_extraction["passed"] else {
        "passed": not args.with_spoken_content,
        "status": "skipped",
        "detail": "未请求中文口播内容提取验证，跳过结构分析验证。" if not args.with_spoken_content else "中文内容提取未通过，跳过结构分析验证。",
    }
    report = {
        "passed": sample["passed"] and upload["passed"] and background["passed"] and task_management["passed"] and model_runtime["passed"] and content_extraction["passed"] and content_analysis["passed"],
        "sample": sample,
        "upload": upload,
        "background_extraction": background,
        "task_management": task_management,
        "model_runtime": model_runtime,
        "content_extraction": content_extraction,
        "content_analysis": content_analysis,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    response = upload.get("response", {})
    print(
        "workbench_video_smoke "
        f"passed={report['passed']} "
        f"sample={sample['status']} "
        f"upload={upload['status']} "
        f"extraction={response.get('extraction_status')} "
        f"asr={response.get('asr_status')} "
        f"ocr={response.get('ocr_status')} "
        f"content={content_extraction['status']} "
        f"analysis={content_analysis['status']} "
        f"background={background['status']} "
        f"task_management={task_management['status']} "
        f"model_runtime={model_runtime['status']} "
        f"report={args.report}"
    )
    if not report["passed"]:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
