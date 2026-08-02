from types import SimpleNamespace

from app.script_workbench import (
    apply_context_term_corrections,
    build_primary_transcript,
    classify_douyin_download_error,
    correct_primary_transcript,
    external_link_gate,
    extract_share_context_terms,
    find_transcript_anomalies,
    normalize_douyin_url_input,
    parse_douyin_share_source_context,
)


def test_full_douyin_share_text_is_normalized_to_the_short_link() -> None:
    share_text = (
        "6.61 k@P.KW :6pm 09/11 CHI:/ 命运会反复出题 "
        "# 王虹 # 屠呦呦 # 谷爱凌 # 董明珠 # 女性  "
        "https://v.douyin.com/i6aptyoHPO8/ "
        "复制此链接，打开Dou音搜索，直接观看视频！"
    )

    assert normalize_douyin_url_input(share_text) == (
        "https://v.douyin.com/i6aptyoHPO8/"
    )


def test_douyin_share_text_extracts_title_without_guessing_author() -> None:
    share_text = (
        "6.61 k@P.KW :6pm 09/11 CHI:/ 命运会反复出题 "
        "直到看到你绝对信任自己的心 # 王虹 # 屠呦呦 # 女性 "
        "https://v.douyin.com/i6aptyoHPO8/ 复制此链接，打开Dou音搜索，直接观看视频！"
    )

    context = parse_douyin_share_source_context(share_text)

    assert context["title"] == "命运会反复出题 直到看到你绝对信任自己的心"
    assert "author" not in context


def test_link_task_preserves_original_video_source_metadata(monkeypatch) -> None:
    from datetime import datetime, timezone
    from pathlib import Path

    from app import script_workbench

    transcript_text = "真实提取出来的视频口播稿，足够后续沉淀为结构 Skill。"
    captured: dict[str, object] = {}

    def fake_download(url: str, source_id: str):
        return script_workbench.DouyinDownloadResult(
            status="completed",
            provider="yt-dlp",
            output_dir="/tmp/mock",
            downloaded_files=["/tmp/mock.mp4"],
            selected_video_path="/tmp/mock.mp4",
            message="已下载。",
            metadata_title="下载器识别标题",
            metadata_author="原视频作者",
            metadata_publish_time="20260730",
        )

    def fake_video_upload(
        file_name: str,
        material_path: Path,
        run_extractors: bool = False,
        context_text: str = "",
        source_title: str | None = None,
        source_url: str | None = None,
        source_author: str | None = None,
        source_publish_time: str | None = None,
        source_created_at=None,
    ):
        captured.update(
            {
                "source_title": source_title,
                "source_url": source_url,
                "source_author": source_author,
                "source_publish_time": source_publish_time,
            }
        )
        source = script_workbench.SourceVideo(
            id="source_video_real",
            input_type="video",
            title=source_title or file_name,
            url=source_url,
            author=source_author,
            publish_time=source_publish_time,
            status="completed",
            created_at=source_created_at or datetime.now(timezone.utc),
        )
        transcript = script_workbench.Transcript(
            id="transcript_real",
            source_video_id=source.id,
            content_text=transcript_text,
            source="funasr",
        )
        return script_workbench.VideoUploadResponse(
            source_video=source,
            extraction_status="completed",
            asr_status="completed",
            asr_text=transcript_text,
            ocr_status="skipped",
            ocr_text="",
            transcript=transcript,
            correction_status="completed",
            transcript_quality_score=91,
            transcript_quality_message="已通过。",
            message="已真实提取视频稿件。",
            asr_message="ASR 已完成。",
            ocr_message="OCR 已跳过。",
            next_step="拆解写作结构。",
            fallback_inputs=[],
        )

    monkeypatch.setattr(script_workbench, "run_douyin_downloader", fake_download)
    monkeypatch.setattr(
        script_workbench, "create_video_upload_result", fake_video_upload
    )

    response = script_workbench.create_link_task(
        script_workbench.LinkTaskRequest(
            url="分享文案里的标题 https://v.douyin.com/mock-real/"
        )
    )

    assert captured == {
        "source_title": "下载器识别标题",
        "source_url": "https://v.douyin.com/mock-real/",
        "source_author": "原视频作者",
        "source_publish_time": "20260730",
    }
    assert response.parser_status == "completed"
    assert response.video_upload is not None
    assert response.video_upload.source_video.author == "原视频作者"
    assert response.video_upload.source_video.url == "https://v.douyin.com/mock-real/"


def test_primary_download_timeout_is_not_overwritten_by_fallback_cookie_error() -> None:
    code, title, _detail, _actions = classify_douyin_download_error(
        "Cookies may be invalid or incomplete", timeout=True
    )

    assert code == "timeout"
    assert title == "链接提取超时"


def test_link_task_preserves_skipped_status_and_offers_manual_inputs(
    monkeypatch,
) -> None:
    from app import script_workbench

    def fake_download(_url: str, _source_id: str):
        return script_workbench.DouyinDownloadResult(
            status="skipped",
            provider="yt-dlp",
            error_code="downloader_disabled",
            error_title="抖音链接解析已关闭",
            error_detail="当前配置关闭了下载器。",
            action_items=["打开免登录链接提取能力后重试"],
            message="下载器已关闭。",
        )

    monkeypatch.setattr(script_workbench, "run_douyin_downloader", fake_download)

    response = script_workbench.create_link_task(
        script_workbench.LinkTaskRequest(url="https://v.douyin.com/fallback/")
    )

    assert response.parser_status == "skipped"
    assert response.parser_error_code == "downloader_disabled"
    assert response.fallback_inputs == [
        "上传视频文件",
        "上传字幕文件",
        "粘贴转写文本",
    ]


def test_server_media_task_does_not_require_a_browser_session() -> None:

    code, title, _detail, actions = classify_douyin_download_error(
        "Cookies may be invalid or incomplete; Empty 200 response (anti-bot)"
    )
    assert code == "cookie_required"
    assert title == "需要有效 Cookie 或登录态"
    assert any("Chrome" in item for item in actions)

    gate = external_link_gate(
        "https://v.douyin.com/public/", run_link=False
    )
    assert gate["status"] == "ready"
    assert gate["cookie_configured"] is False
    assert gate["downloader_mode"] == "server_media_task"
    assert any("无需安装" in item for item in gate["action_items"])


def test_ytdlp_reads_browser_cookies_by_default(monkeypatch, tmp_path) -> None:
    from app import script_workbench

    monkeypatch.setenv("WORKBENCH_YTDLP_COOKIES_FROM_BROWSER", "chrome")
    monkeypatch.setattr(script_workbench.shutil, "which", lambda _name: "yt-dlp")

    command, message = script_workbench.ytdlp_command(
        "https://v.douyin.com/public/", tmp_path
    )

    assert command is not None
    assert "--cookies-from-browser" in command
    assert command[command.index("--cookies-from-browser") + 1] == "chrome"
    assert "浏览器会话" in message


def test_cookie_block_falls_back_to_secondary_downloader(
    monkeypatch, tmp_path
) -> None:
    from app import script_workbench

    attempts = 0

    def fake_run(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        output_dir = tmp_path / "douyin" / "source_public_retry"
        output_dir.mkdir(parents=True, exist_ok=True)
        if attempts == 1:
            return SimpleNamespace(
                returncode=1,
                stderr="Failed to resolve short URL: temporary anti-bot response",
                stdout="",
            )
        (output_dir / "yt-dlp-video.mp4").write_bytes(b"video")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setenv("WORKBENCH_DOUYIN_PUBLIC_ATTEMPTS", "2")
    monkeypatch.setenv("WORKBENCH_DOUYIN_RETRY_DELAY_SECONDS", "0")
    monkeypatch.delenv("WORKBENCH_YTDLP_DOWNLOAD_ATTEMPTS", raising=False)
    monkeypatch.setattr(script_workbench, "media_root", lambda: tmp_path)
    monkeypatch.setattr(
        script_workbench,
        "ytdlp_command",
        lambda _url, _output_dir: (["yt-dlp", "test-url"], "浏览器会话测试下载器"),
    )
    monkeypatch.setattr(
        script_workbench, "recover_playable_partial_media", lambda _output_dir: []
    )
    monkeypatch.setattr(script_workbench.subprocess, "run", fake_run)

    result = script_workbench.run_douyin_downloader(
        "https://v.douyin.com/public-retry/", "source_public_retry"
    )

    assert attempts == 2
    assert result.status == "completed"
    assert result.provider == "jiji262/douyin-downloader"


def test_ytdlp_timeout_retries_and_resumes_before_fallback(
    monkeypatch, tmp_path
) -> None:
    from app import script_workbench

    attempts = 0

    def fake_run(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        output_dir = tmp_path / "douyin" / "source_retry"
        output_dir.mkdir(parents=True, exist_ok=True)
        if attempts == 1:
            (output_dir / "yt-dlp-video.mp4.part").write_bytes(b"partial")
            raise script_workbench.subprocess.TimeoutExpired("yt-dlp", 1)
        (output_dir / "yt-dlp-video.mp4").write_bytes(b"video")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setenv("WORKBENCH_DOUYIN_DOWNLOADER_TIMEOUT", "1")
    monkeypatch.setenv("WORKBENCH_YTDLP_DOWNLOAD_ATTEMPTS", "2")
    monkeypatch.setattr(script_workbench, "media_root", lambda: tmp_path)
    monkeypatch.setattr(
        script_workbench,
        "ytdlp_command",
        lambda _url, _output_dir: (["yt-dlp", "test-url"], "测试下载器"),
    )
    monkeypatch.setattr(
        script_workbench, "recover_playable_partial_media", lambda _output_dir: []
    )
    monkeypatch.setattr(script_workbench.subprocess, "run", fake_run)

    result = script_workbench.run_douyin_downloader(
        "https://v.douyin.com/i6aptyoHPO8/", "source_retry"
    )

    assert attempts == 2
    assert result.status == "completed"
    assert result.provider == "yt-dlp"
    assert result.selected_video_path is not None


def test_asr_is_primary_and_ocr_document_text_is_not_appended() -> None:
    asr = (
        "命运会反复出题，直到看到一颗绝对信任自己的心。"
        "她经历过怀疑和失败，但最后仍然选择继续。"
    )
    ocr = (
        "Thm Orpo EsB101 through Definition clustering hypothesis "
        "论文页面上的英文公式和长段正文"
    )

    content, source = build_primary_transcript(asr, ocr)

    assert content == asr
    assert source == "funasr"
    assert "clustering hypothesis" not in content


def test_long_english_asr_hallucination_is_removed_in_chinese_transcript() -> None:
    asr = (
        "他一直没有放弃，我needs to be honest about后来他真的走向了数学世界的前沿。"
        "这不是天赋故事，而是长期选择的结果。"
    )

    content, source = build_primary_transcript(asr, "")

    assert source == "funasr"
    assert "needs to be honest about" not in content
    assert "后来他真的走向了数学世界的前沿" in content


def test_ocr_only_fallback_keeps_chinese_subtitles_and_drops_english_page() -> None:
    ocr = (
        "命运会反复出题，直到你相信自己。\n"
        "Section 1.2 Unions of convex sets and non clustering hypothesis\n"
        "经历失败之后，她仍然选择继续。"
    )

    content, source = build_primary_transcript("", ocr)

    assert source == "paddleocr"
    assert "命运会反复出题" in content
    assert "仍然选择继续" in content
    assert "clustering hypothesis" not in content


def test_share_hashtags_correct_person_names_without_overlapping_replacements() -> None:
    share_text = "# 王虹 # 屠呦呦 # 谷爱凌 # 董明珠 # 女性"
    transcript = (
        "王红证明了猜想。独呦悠接过任务，刘悠悠怀疑过自己。"
        "胡爱凌从雪山上摔下来，农民哥从业务员做起。"
    )

    terms, entities = extract_share_context_terms(share_text)
    corrected, corrections = apply_context_term_corrections(transcript, entities)

    assert terms == ["王虹", "屠呦呦", "谷爱凌", "董明珠", "女性"]
    assert entities == ["王虹", "屠呦呦", "谷爱凌", "董明珠"]
    assert "王虹" in corrected
    assert corrected.count("屠呦呦") == 2
    assert "谷爱凌" in corrected
    assert "刘屠呦呦" not in corrected
    assert "农民哥" in corrected
    assert {item.original for item in corrections} == {
        "王红",
        "独呦悠",
        "刘悠悠",
        "胡爱凌",
    }


def test_normal_repeated_phrase_is_not_flagged_but_asr_stutter_is() -> None:
    anomalies = find_transcript_anomalies(
        "谷爱凌摔倒后拍拍雪站起来，但旁白说成要开开始。", ["谷爱凌"]
    )

    assert not any("拍拍雪" in item for item in anomalies)
    assert any("开开始" in item for item in anomalies)


def test_quality_gate_applies_declared_ai_corrections_before_analysis(
    monkeypatch,
) -> None:
    from app import workbench_llm

    transcript = (
        "王红证明了猜想。独呦悠接过任务，刘悠悠怀疑过自己。"
        "胡爱凌从雪山上摔下来，而且要开开始。农民哥从业务员做起。"
    )
    share_text = "# 王虹 # 屠呦呦 # 谷爱凌 # 董明珠 # 女性"

    def fake_correction(*_args):
        return SimpleNamespace(
            corrections=[
                SimpleNamespace(
                    original="而且要开开始",
                    corrected="而且要拍拍雪站起来",
                    reason="结合画面语义修正语音残片",
                    confidence=94,
                ),
                SimpleNamespace(
                    original="农民哥",
                    corrected="董明珠",
                    reason="与分享标签和人物上下文一致",
                    confidence=96,
                ),
            ],
            unresolved_fragments=[],
        )

    monkeypatch.setattr(workbench_llm, "correct_transcript_structured", fake_correction)
    corrected, corrections, unresolved, score, _message, _terms = (
        correct_primary_transcript(transcript, share_text, "")
    )

    assert "王虹" in corrected
    assert corrected.count("屠呦呦") == 2
    assert "谷爱凌" in corrected
    assert "拍拍雪站起来" in corrected
    assert "董明珠" in corrected
    assert not unresolved
    assert score >= 80
    assert any(item.original == "农民哥" for item in corrections)


def test_quality_gate_blocks_unconfirmed_low_confidence_name(monkeypatch) -> None:
    from app import workbench_llm

    monkeypatch.setattr(
        workbench_llm, "correct_transcript_structured", lambda *_args: None
    )
    corrected, _corrections, unresolved, _score, message, _terms = (
        correct_primary_transcript(
            "谷爱凌拍拍雪站起来，农民哥从业务员做起。",
            "# 谷爱凌 # 董明珠",
            "",
        )
    )

    assert "农民哥" in corrected
    assert any("董明珠" in item for item in unresolved)
    assert "已停止后续拆解" in message


def test_ai_correction_must_uniquely_identify_its_source_fragment(monkeypatch) -> None:
    from app import workbench_llm

    def ambiguous_correction(*_args):
        return SimpleNamespace(
            corrections=[
                SimpleNamespace(
                    original="学科",
                    corrected="草药",
                    reason="药物研发上下文",
                    confidence=92,
                )
            ],
            unresolved_fragments=[],
        )

    monkeypatch.setattr(
        workbench_llm, "correct_transcript_structured", ambiguous_correction
    )
    original = "他继续投入数学这门学科。课题组筛选了两千多种学科。"
    corrected, corrections, unresolved, _score, _message, _terms = (
        correct_primary_transcript(original, "", "")
    )

    assert corrected == original
    assert not corrections
    assert any("定位不唯一" in item for item in unresolved)
