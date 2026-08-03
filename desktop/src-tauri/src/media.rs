use crate::audit;
use crate::db::DesktopDb;
use crate::douyin_browser;
use crate::executable::{child_process_path, require_executable};
use crate::settings::{api_client, load_settings, proxy_route, read_secret, uses_local_mlx_asr, WorkbenchSettings};
use chrono::{TimeZone, Utc};
use regex::Regex;
use reqwest::header::{CONTENT_RANGE, CONTENT_TYPE, RANGE, REFERER};
use reqwest::{multipart, Client};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::fs;
use std::path::{Path, PathBuf};
use std::time::Duration;
use tauri::{AppHandle, Emitter, Manager};
use tokio::io::AsyncWriteExt;
use tokio::process::Command;
use tokio::time::timeout;
use uuid::Uuid;

const BROWSER_USER_AGENT: &str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36";
const MAX_DOWNLOADED_MEDIA_BYTES: u64 = 1024 * 1024 * 1024;

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct MediaRequest {
    pub mode: String,
    pub input: String,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct MediaProgress<'a> {
    task_id: &'a str,
    stage: &'a str,
    message: &'a str,
}

fn emit_progress(app: &AppHandle, task_id: &str, stage: &str, message: &str) {
    let _ = app.emit(
        "media-progress",
        MediaProgress {
            task_id,
            stage,
            message,
        },
    );
}

fn douyin_url(input: &str) -> Result<String, String> {
    let pattern = Regex::new(r#"https?://[^\s<>\"']+"#).map_err(|error| error.to_string())?;
    for matched in pattern.find_iter(input) {
        let candidate = matched
            .as_str()
            .trim_end_matches(|character: char| "，。！？、；：)]}".contains(character));
        if let Ok(url) = url::Url::parse(candidate) {
            if url
                .host_str()
                .is_some_and(|host| host == "douyin.com" || host.ends_with(".douyin.com"))
            {
                return Ok(candidate.to_string());
            }
        }
    }
    Err("没有识别到有效的 douyin.com 分享链接".into())
}

async fn run_command(
    command: &str,
    args: &[String],
    seconds: u64,
) -> Result<std::process::Output, String> {
    let executable = require_executable(command)?;
    let mut child = Command::new(&executable);
    child
        .args(args)
        .env("PATH", child_process_path())
        .kill_on_drop(true);
    let output = timeout(Duration::from_secs(seconds), child.output())
        .await
        .map_err(|_| format!("{command} 处理超时"))?
        .map_err(|error| format!("无法启动 {}：{error}", executable.display()))?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        let mut lines = stderr.lines().rev().take(8).collect::<Vec<_>>();
        lines.reverse();
        let detail = lines.join("\n");
        return Err(format!(
            "{command} 失败：{}",
            if detail.is_empty() {
                "未知错误"
            } else {
                &detail
            }
        ));
    }
    Ok(output)
}

async fn largest_download(directory: &Path) -> Result<PathBuf, String> {
    let mut entries = tokio::fs::read_dir(directory)
        .await
        .map_err(|error| error.to_string())?;
    let mut selected: Option<(u64, PathBuf)> = None;
    while let Some(entry) = entries
        .next_entry()
        .await
        .map_err(|error| error.to_string())?
    {
        let path = entry.path();
        let metadata = entry.metadata().await.map_err(|error| error.to_string())?;
        if metadata.is_file()
            && path.file_name().and_then(|value| value.to_str()) != Some("audio.mp3")
            && !matches!(
                path.file_name().and_then(|value| value.to_str()),
                Some("yt-dlp.conf" | "cookies.txt")
            )
        {
            if selected
                .as_ref()
                .is_none_or(|(size, _)| metadata.len() > *size)
            {
                selected = Some((metadata.len(), path));
            }
        }
    }
    selected
        .map(|(_, path)| path)
        .ok_or_else(|| "yt-dlp 没有生成可转写媒体".to_string())
}

fn netscape_cookie_jar(cookie: &str) -> Result<String, String> {
    let ignored = [
        "domain", "path", "expires", "max-age", "samesite", "secure", "httponly",
    ];
    let mut rows = Vec::new();
    for part in cookie.split(';') {
        let Some((name, value)) = part.trim().split_once('=') else {
            continue;
        };
        let name = name.trim();
        let value = value.trim();
        if name.is_empty()
            || ignored
                .iter()
                .any(|ignored| name.eq_ignore_ascii_case(ignored))
            || name.chars().any(char::is_whitespace)
            || name.chars().any(char::is_control)
            || value
                .chars()
                .any(|character| matches!(character, '\r' | '\n' | '\t'))
        {
            continue;
        }
        rows.push(format!(".douyin.com\tTRUE\t/\tTRUE\t0\t{name}\t{value}"));
    }
    if rows.is_empty() {
        return Err("抖音 Cookie 不包含可用的 name=value 项".into());
    }
    Ok(format!(
        "# Netscape HTTP Cookie File\n{}\n",
        rows.join("\n")
    ))
}

async fn canonical_douyin_url(url: &str) -> Result<String, String> {
    if douyin_browser::aweme_id(url).is_ok() {
        return Ok(url.to_string());
    }
    let mut errors = Vec::new();
    for bypass_system_proxy in [true, false] {
        let mut builder = Client::builder()
            .user_agent(BROWSER_USER_AGENT)
            .timeout(Duration::from_secs(30));
        if bypass_system_proxy {
            builder = builder.no_proxy();
        }
        let result = async {
            let response = builder
                .build()
                .map_err(|error| error.to_string())?
                .get(url)
                .send()
                .await
                .map_err(|error| error.to_string())?;
            let resolved = response.url().to_string();
            douyin_browser::aweme_id(&resolved)?;
            Ok::<_, String>(resolved)
        }
        .await;
        match result {
            Ok(resolved) => return Ok(resolved),
            Err(error) => errors.push(error),
        }
    }
    Err(format!("抖音短链接解析失败：{}", errors.join("；")))
}

async fn download_signed_media(
    client: &Client,
    media_url: &str,
    source_url: &str,
    destination: &Path,
) -> Result<(), String> {
    let mut file = tokio::fs::File::create(destination)
        .await
        .map_err(|error| error.to_string())?;
    let mut downloaded = 0_u64;
    loop {
        let mut response = client
            .get(media_url)
            .header(REFERER, source_url)
            .header(RANGE, format!("bytes={downloaded}-"))
            .send()
            .await
            .map_err(|error| format!("媒体请求失败：{error}"))?
            .error_for_status()
            .map_err(|error| format!("媒体服务器拒绝请求：{error}"))?;
        let partial = response.status() == reqwest::StatusCode::PARTIAL_CONTENT;
        let content_type = response
            .headers()
            .get(CONTENT_TYPE)
            .and_then(|value| value.to_str().ok())
            .unwrap_or("");
        if !content_type.is_empty()
            && !content_type.starts_with("video/")
            && content_type != "application/octet-stream"
        {
            return Err(format!("媒体地址返回了非视频内容：{content_type}"));
        }
        if let Some(length) = response.content_length() {
            if downloaded.saturating_add(length) > MAX_DOWNLOADED_MEDIA_BYTES {
                return Err("授权媒体超过 1GB 安全限制".into());
            }
        }
        let range = response
            .headers()
            .get(CONTENT_RANGE)
            .and_then(|value| value.to_str().ok())
            .and_then(|value| {
                let value = value.strip_prefix("bytes ")?;
                let (span, total) = value.split_once('/')?;
                let (start, end) = span.split_once('-')?;
                Some((
                    start.parse::<u64>().ok()?,
                    end.parse::<u64>().ok()?,
                    total.parse::<u64>().ok()?,
                ))
            });
        if let Some((start, end, total)) = range {
            if start != downloaded || end < start || total <= end {
                return Err("媒体服务器返回了不连续的字节范围".into());
            }
            if total > MAX_DOWNLOADED_MEDIA_BYTES {
                return Err("授权媒体超过 1GB 安全限制".into());
            }
        } else if partial {
            return Err("媒体服务器返回了无效的 Content-Range".into());
        }
        let before = downloaded;
        while let Some(chunk) = response
            .chunk()
            .await
            .map_err(|error| format!("媒体下载中断：{error}"))?
        {
            downloaded += chunk.len() as u64;
            if downloaded > MAX_DOWNLOADED_MEDIA_BYTES {
                return Err("授权媒体超过 1GB 安全限制".into());
            }
            file.write_all(&chunk)
                .await
                .map_err(|error| error.to_string())?;
        }
        if downloaded == before {
            return Err("媒体服务器返回了空文件".into());
        }
        if let Some((_, end, total)) = range {
            if downloaded != end + 1 {
                return Err("媒体服务器返的字节数与 Content-Range 不一致".into());
            }
            if downloaded >= total {
                break;
            }
        } else {
            break;
        }
    }
    file.flush().await.map_err(|error| error.to_string())?;
    if downloaded == 0 {
        return Err("媒体服务器返回了空文件".into());
    }
    Ok(())
}

async fn download_douyin_with_browser(
    url: &str,
    directory: &Path,
) -> Result<(PathBuf, Value), String> {
    let canonical_url = canonical_douyin_url(url).await?;
    let direct_profile = directory.join("douyin-browser-direct");
    tokio::fs::create_dir_all(&direct_profile)
        .await
        .map_err(|error| error.to_string())?;
    let (detail, bypass_system_proxy) =
        match douyin_browser::resolve_public_video(&canonical_url, &direct_profile, true).await {
            Ok(detail) => (detail, true),
            Err(direct_error) => {
                let proxy_profile = directory.join("douyin-browser-system-proxy");
                tokio::fs::create_dir_all(&proxy_profile)
                    .await
                    .map_err(|error| error.to_string())?;
                match douyin_browser::resolve_public_video(&canonical_url, &proxy_profile, false)
                    .await
                {
                    Ok(detail) => (detail, false),
                    Err(proxy_error) => {
                        return Err(format!(
                            "直连解析失败：{direct_error}；系统代理解析失败：{proxy_error}"
                        ));
                    }
                }
            }
        };
    let media_urls = detail
        .get("mediaUrls")
        .and_then(Value::as_array)
        .ok_or_else(|| "抖音详情中没有可下载的媒体地址".to_string())?;
    let destination = directory.join("source.mp4");
    let mut client_builder = Client::builder()
        .user_agent(BROWSER_USER_AGENT)
        .timeout(Duration::from_secs(300));
    if bypass_system_proxy {
        client_builder = client_builder.no_proxy();
    }
    let client = client_builder.build().map_err(|error| error.to_string())?;
    let mut last_error = None;
    for media_url in media_urls.iter().filter_map(Value::as_str) {
        match download_signed_media(&client, media_url, &canonical_url, &destination).await {
            Ok(()) => {
                let metadata = json!({
                    "id": detail.get("awemeId").and_then(Value::as_str),
                    "title": detail.get("title").and_then(Value::as_str).unwrap_or("抖音授权视频"),
                    "uploader": detail.get("author").and_then(Value::as_str),
                    "timestamp": detail.get("timestamp").and_then(Value::as_i64),
                    "duration": detail.get("durationMs").and_then(Value::as_u64).map(|value| value as f64 / 1000.0),
                    "webpage_url": canonical_url,
                    "extractor": "douyin-browser-signed"
                });
                return Ok((destination, metadata));
            }
            Err(error) => last_error = Some(error),
        }
    }
    Err(last_error.unwrap_or_else(|| "抖音详情中没有可用的媒体地址".into()))
}

async fn download_douyin_with_ytdlp(
    url: &str,
    directory: &Path,
) -> Result<(PathBuf, Value), String> {
    let output_template = directory
        .join("source.%(ext)s")
        .to_string_lossy()
        .into_owned();
    let mut args = vec![
        "--no-playlist".into(),
        "--print-json".into(),
        "--restrict-filenames".into(),
        "-f".into(),
        "ba/b".into(),
        "-o".into(),
        output_template,
    ];
    if let Some(cookie) = read_secret("douyin_cookie")? {
        let cookie_path = directory.join("cookies.txt");
        fs_write_private(&cookie_path, netscape_cookie_jar(&cookie)?.as_bytes())?;
        args.extend([
            "--cookies".into(),
            cookie_path.to_string_lossy().into_owned(),
        ]);
    }
    args.push(url.to_string());
    let output = run_command("yt-dlp", &args, 300).await?;
    let metadata = String::from_utf8_lossy(&output.stdout)
        .lines()
        .rev()
        .find_map(|line| serde_json::from_str::<Value>(line).ok())
        .unwrap_or_else(|| json!({}));
    Ok((largest_download(directory).await?, metadata))
}

async fn download_douyin(url: &str, directory: &Path) -> Result<(PathBuf, Value), String> {
    match download_douyin_with_browser(url, directory).await {
        Ok(result) => Ok(result),
        Err(browser_error) => match download_douyin_with_ytdlp(url, directory).await {
            Ok(result) => Ok(result),
            Err(ytdlp_error) => Err(format!(
                "抖音无登录解析失败：{browser_error}；yt-dlp 降级也失败：{ytdlp_error}"
            )),
        },
    }
}

fn fs_write_private(path: &Path, content: &[u8]) -> Result<(), String> {
    fs::write(path, content).map_err(|error| error.to_string())?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(path, fs::Permissions::from_mode(0o600))
            .map_err(|error| error.to_string())?;
    }
    Ok(())
}

async fn extract_audio(input: &Path, output: &Path) -> Result<(), String> {
    let args = vec![
        "-hide_banner".into(),
        "-loglevel".into(),
        "error".into(),
        "-y".into(),
        "-i".into(),
        input.to_string_lossy().into_owned(),
        "-vn".into(),
        "-ac".into(),
        "1".into(),
        "-ar".into(),
        "16000".into(),
        "-b:a".into(),
        "64k".into(),
        output.to_string_lossy().into_owned(),
    ];
    run_command("ffmpeg", &args, 240).await.map(|_| ())
}

fn validate_transcript(value: Value) -> Result<Value, String> {
    let text = value
        .get("text")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim();
    if text.chars().count() < 10 {
        return Err("转写服务没有返回可分析的真实稿件".into());
    }
    Ok(value)
}

fn summarize_process_output(stdout: &[u8], stderr: &[u8]) -> String {
    let stdout = String::from_utf8_lossy(stdout);
    let stderr = String::from_utf8_lossy(stderr);
    let mut lines = stdout
        .lines()
        .chain(stderr.lines())
        .map(str::trim)
        .filter(|line| !line.is_empty())
        .filter(|line| !line.starts_with("Fetching ") && !line.contains("frames/s"))
        .collect::<Vec<_>>();
    if lines
        .iter()
        .rev()
        .any(|line| line.contains("FileNotFoundError") && line.contains("ffmpeg"))
    {
        return "本机 MLX Whisper 找不到 ffmpeg 命令".to_string();
    }
    if lines.is_empty() {
        return String::new();
    }
    lines.drain(..lines.len().saturating_sub(8));
    lines.join(" | ").chars().take(900).collect()
}

fn read_local_transcript_output(directory: &Path, expected: &Path) -> Result<Value, String> {
    let mut candidates = vec![expected.to_path_buf()];
    let entries = fs::read_dir(directory)
        .map_err(|error| format!("无法读取本机转写输出目录：{error}"))?;
    for entry in entries.flatten() {
        let path = entry.path();
        if path != expected
            && path.extension().and_then(|extension| extension.to_str()) == Some("json")
        {
            candidates.push(path);
        }
    }
    candidates.sort();
    candidates.dedup();

    let mut observed = Vec::new();
    for path in candidates {
        let name = path.file_name().and_then(|name| name.to_str()).unwrap_or("未知 JSON");
        let raw = match fs::read_to_string(&path) {
            Ok(raw) => raw,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => continue,
            Err(error) => {
                observed.push(format!("{name} 无法读取：{error}"));
                continue;
            }
        };
        let value = match serde_json::from_str::<Value>(&raw) {
            Ok(value) => value,
            Err(error) => {
                observed.push(format!("{name} 不是 JSON：{error}"));
                continue;
            }
        };
        match validate_transcript(value) {
            Ok(value) => return Ok(value),
            Err(error) => observed.push(format!("{name}：{error}")),
        }
    }
    let observed = if observed.is_empty() {
        "CLI 未写入任何可用 JSON 文件".to_string()
    } else {
        observed.join("；")
    };
    Err(format!("未发现可用转写 JSON：{observed}"))
}

async fn transcribe_local_mlx(settings: &WorkbenchSettings, audio: &Path) -> Result<Value, String> {
    let directory = audio
        .parent()
        .ok_or_else(|| "无法创建本机转写结果".to_string())?;
    let output_name = "local-transcript";
    let output_path = directory.join(format!("{output_name}.json"));
    let args = vec![
        audio.to_string_lossy().into_owned(),
        "--model".into(),
        settings.asr_model.clone(),
        "--output-name".into(),
        output_name.into(),
        "--output-dir".into(),
        directory.to_string_lossy().into_owned(),
        "--output-format".into(),
        "json".into(),
        "--verbose".into(),
        "False".into(),
    ];
    let output = run_command("mlx_whisper", &args, 900).await?;
    match read_local_transcript_output(directory, &output_path) {
        Ok(value) => Ok(value),
        Err(error) => {
            // mlx_whisper 0.4.x catches per-file exceptions and exits with code 0.
            // Its stdout/stderr is therefore the only reliable explanation when no JSON exists.
            let detail = summarize_process_output(&output.stdout, &output.stderr);
            if detail.is_empty() {
                Err(format!("本机 MLX Whisper 未生成转写结果：{error}"))
            } else {
                Err(format!("本机 MLX Whisper 未完成转写：{detail}；{error}"))
            }
        }
    }
}

async fn transcribe_api(settings: &WorkbenchSettings, audio: &Path) -> Result<Value, String> {
    let key = read_secret("asr_api_key")?
        .or(read_secret("llm_api_key")?)
        .ok_or_else(|| "尚未在系统凭据库保存转写 API Key".to_string())?;
    let bytes = tokio::fs::read(audio)
        .await
        .map_err(|error| error.to_string())?;
    if bytes.len() > 100 * 1024 * 1024 {
        return Err("提取后的音频超过 100MB，请压缩或裁剪后重试".into());
    }
    let part = multipart::Part::bytes(bytes)
        .file_name("audio.mp3")
        .mime_str("audio/mpeg")
        .map_err(|error| error.to_string())?;
    let form = multipart::Form::new()
        .text("model", settings.asr_model.clone())
        .text("response_format", "json")
        .part("file", part);
    let (http, _) = api_client(settings, 600)?;
    let response = http
        .post(format!(
            "{}/audio/transcriptions",
            settings.asr_api_base.trim_end_matches('/')
        ))
        .bearer_auth(key)
        .multipart(form)
        .send()
        .await
        .map_err(|error| format!("转写服务连接失败：{error}"))?;
    let status = response.status();
    let raw = response.text().await.map_err(|error| error.to_string())?;
    if !status.is_success() {
        let detail = serde_json::from_str::<Value>(&raw)
            .ok()
            .and_then(|value| {
                value
                    .pointer("/error/message")
                    .and_then(Value::as_str)
                    .map(ToOwned::to_owned)
            })
            .unwrap_or_else(|| raw.chars().take(300).collect());
        return Err(format!("转写请求失败（{status}）：{detail}"));
    }
    let value: Value =
        serde_json::from_str(&raw).map_err(|error| format!("转写响应不是 JSON：{error}"))?;
    validate_transcript(value)
}

async fn transcribe(db: &DesktopDb, audio: &Path) -> Result<Value, String> {
    let settings = load_settings(db)?;
    if uses_local_mlx_asr(&settings) {
        transcribe_local_mlx(&settings, audio).await
    } else {
        transcribe_api(&settings, audio).await
    }
}

fn publish_time(metadata: &Value) -> Option<String> {
    metadata
        .get("timestamp")
        .and_then(Value::as_i64)
        .and_then(|value| Utc.timestamp_opt(value, 0).single())
        .map(|value| value.to_rfc3339())
}

pub async fn process_media(
    app: AppHandle,
    db: &DesktopDb,
    request: MediaRequest,
    trace_id: &str,
) -> Result<Value, String> {
    let task_id = format!("media-{}", Uuid::new_v4());
    let cache = app
        .path()
        .app_cache_dir()
        .map_err(|error| error.to_string())?
        .join("media-cache")
        .join(&task_id);
    tokio::fs::create_dir_all(&cache)
        .await
        .map_err(|error| error.to_string())?;
    emit_progress(&app, &task_id, "source", "正在校验来源");
    let _ = audit::record(db, trace_id, "media.process", "source", "started", "MEDIA_SOURCE_VALIDATION_STARTED", "开始校验媒体来源", "media.rs:process_media/source", None);
    let result = async {
        let (input_path, source_url, metadata) = match request.mode.as_str() {
            "douyin_link" => {
                let url = douyin_url(&request.input)?;
                let _ = audit::record(db, trace_id, "media.process", "source", "success", "MEDIA_SOURCE_VALIDATED", "抖音来源已通过域名校验", "media.rs:process_media/source", None);
                emit_progress(&app, &task_id, "download", "正在临时下载抖音媒体");
                let _ = audit::record(db, trace_id, "media.process", "download", "started", "MEDIA_DOWNLOAD_STARTED", "开始临时下载媒体", "media.rs:process_media/download", None);
                let (path, metadata) = download_douyin(&url, &cache).await?;
                let _ = audit::record(db, trace_id, "media.process", "download", "success", "MEDIA_DOWNLOAD_COMPLETED", "媒体临时下载完成", "media.rs:process_media/download", None);
                (path, Some(url), metadata)
            }
            "local_media" => {
                let path = PathBuf::from(request.input.trim());
                if !path.is_file() {
                    return Err("选择的本机媒体不存在或不可读取".into());
                }
                let _ = audit::record(db, trace_id, "media.process", "source", "success", "MEDIA_LOCAL_FILE_VALIDATED", "本机媒体文件已通过可读性校验", "media.rs:process_media/source", None);
                (path, None, json!({}))
            }
            _ => return Err("不支持的媒体来源类型".into()),
        };
        emit_progress(&app, &task_id, "audio", "正在提取临时音频");
        let _ = audit::record(db, trace_id, "media.process", "audio", "started", "MEDIA_AUDIO_EXTRACTION_STARTED", "开始提取临时音频", "media.rs:process_media/audio", None);
        let audio = cache.join("audio.mp3");
        extract_audio(&input_path, &audio).await?;
        let _ = audit::record(db, trace_id, "media.process", "audio", "success", "MEDIA_AUDIO_EXTRACTION_COMPLETED", "临时音频提取完成", "media.rs:process_media/audio", None);
        let settings = load_settings(db)?;
        let progress = if uses_local_mlx_asr(&settings) {
            "正在使用本机 MLX Whisper 转写"
        } else {
            "正在调用真实转写 API"
        };
        emit_progress(&app, &task_id, "transcription", progress);
        let route = proxy_route(&settings)?.map(|route| route.source.to_string()).unwrap_or_else(|| "直连".into());
        let _ = audit::record(db, trace_id, "media.process", "transcription", "info", "MEDIA_TRANSCRIPTION_NETWORK_ROUTE", "转写网络路由已确定", "media.rs:process_media/transcription", Some(&route));
        let _ = audit::record(db, trace_id, "media.process", "transcription", "started", "MEDIA_TRANSCRIPTION_STARTED", progress, "media.rs:process_media/transcription", None);
        let transcript = transcribe(db, &audio).await?;
        let text_length = transcript.get("text").and_then(Value::as_str).map(str::chars).map(Iterator::count).unwrap_or(0);
        let _ = audit::record(db, trace_id, "media.process", "transcription", "success", "MEDIA_TRANSCRIPTION_COMPLETED", "真实转写结果已通过格式校验", "media.rs:process_media/transcription", Some(&format!("转写文本长度：{text_length} 字")));
        let title = metadata
            .get("title")
            .and_then(Value::as_str)
            .map(ToOwned::to_owned)
            .or_else(|| {
                input_path
                    .file_stem()
                    .and_then(|value| value.to_str())
                    .map(ToOwned::to_owned)
            })
            .unwrap_or_else(|| "已授权媒体".into());
        Ok(json!({
            "taskId": task_id,
            "title": title,
            "url": source_url,
            "author": metadata.get("uploader").and_then(Value::as_str),
            "publishTime": publish_time(&metadata),
            "transcript": transcript.get("text").and_then(Value::as_str).unwrap_or(""),
            "timestamps": transcript.get("segments").cloned().unwrap_or_else(|| json!([])),
            "provider": if uses_local_mlx_asr(&settings) { format!("本机 MLX · {}", settings.asr_model) } else { settings.asr_model },
            "mediaCleanupStatus": "completed"
        }))
    }
    .await;
    let succeeded = result.is_ok();
    let cleanup = tokio::fs::remove_dir_all(&cache).await;
    if cleanup.is_err() {
        emit_progress(
            &app,
            &task_id,
            "cleanup",
            "临时媒体清理失败，请在系统诊断重试清理",
        );
        let _ = audit::record(db, trace_id, "media.process", "cleanup", "error", "MEDIA_CACHE_CLEANUP_FAILED", "临时媒体清理失败", "media.rs:process_media/cleanup", Some("请在系统诊断中重新检查缓存目录权限"));
    } else if succeeded {
        emit_progress(
            &app,
            &task_id,
            "completed",
            "真实稿件已取得，临时媒体已清理",
        );
        let _ = audit::record(db, trace_id, "media.process", "cleanup", "success", "MEDIA_CACHE_CLEANED", "临时媒体已清理", "media.rs:process_media/cleanup", None);
    } else {
        emit_progress(
            &app,
            &task_id,
            "cleanup",
            "处理已停止，临时浏览器和媒体数据已清理",
        );
        let _ = audit::record(db, trace_id, "media.process", "cleanup", "success", "MEDIA_CACHE_CLEANED_AFTER_FAILURE", "失败后的临时媒体已清理", "media.rs:process_media/cleanup", None);
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn extracts_only_douyin_urls() {
        assert_eq!(
            douyin_url("复制 https://v.douyin.com/abc123/ 打开").unwrap(),
            "https://v.douyin.com/abc123/"
        );
        assert!(douyin_url("https://example.com/video").is_err());
    }

    #[test]
    fn converts_cookie_header_to_a_real_cookie_jar() {
        let value =
            netscape_cookie_jar("s_v_web_id=verify_123; ttwid=abc==; Path=/; Secure").unwrap();
        assert!(value.starts_with("# Netscape HTTP Cookie File\n"));
        assert!(value.contains("\ts_v_web_id\tverify_123\n"));
        assert!(value.contains("\tttwid\tabc==\n"));
        assert!(!value.contains("\tPath\t"));
    }

    #[test]
    fn rejects_cookie_text_without_name_value_pairs() {
        assert!(netscape_cookie_jar("Secure; HttpOnly").is_err());
    }

    #[test]
    fn local_transcript_reader_uses_a_valid_json_output() {
        let directory = tempfile::tempdir().unwrap();
        let metadata = directory.path().join("source.info.json");
        std::fs::write(metadata, r#"{"title":"not a transcript"}"#).unwrap();
        let transcript = directory.path().join("local-transcript.json");
        std::fs::write(&transcript, r#"{"text":"这是一段超过十个字的真实转写结果。","segments":[]}"#).unwrap();

        let result = read_local_transcript_output(directory.path(), &transcript).unwrap();
        assert_eq!(result["text"], "这是一段超过十个字的真实转写结果。");
    }

    #[test]
    fn local_transcript_reader_reports_missing_cli_output() {
        let directory = tempfile::tempdir().unwrap();
        let error = read_local_transcript_output(directory.path(), &directory.path().join("local-transcript.json"))
            .unwrap_err();
        assert!(error.contains("CLI 未写入任何可用 JSON 文件"));
    }

    #[test]
    fn summarizes_mlx_cli_errors_even_when_the_process_succeeds() {
        let detail = summarize_process_output(
            b"Skipping audio.mp3 due to FileNotFoundError: weights.safetensors not found\n",
            b"Traceback (most recent call last):\nFileNotFoundError: weights.safetensors not found\n",
        );
        assert!(detail.contains("Skipping audio.mp3"));
        assert!(detail.contains("FileNotFoundError"));
    }

    #[tokio::test]
    #[ignore = "requires network, Chromium, and FFmpeg"]
    async fn downloads_and_extracts_audio_from_public_douyin_without_login() {
        let directory = tempfile::tempdir().unwrap();
        let (video, metadata) =
            download_douyin_with_browser("https://v.douyin.com/I2tJ2Lywu-E/", directory.path())
                .await
                .unwrap();
        assert!(tokio::fs::metadata(&video).await.unwrap().len() > 1024);
        assert_eq!(
            metadata.get("extractor").and_then(Value::as_str),
            Some("douyin-browser-signed")
        );
        let audio = directory.path().join("audio.mp3");
        extract_audio(&video, &audio).await.unwrap();
        assert!(tokio::fs::metadata(audio).await.unwrap().len() > 1024);
    }
}
