use crate::db::DesktopDb;
use regex::Regex;
use serde_json::{Value, json};

pub fn record(
    db: &DesktopDb,
    trace_id: &str,
    action: &str,
    stage: &str,
    status: &str,
    code: &str,
    message: &str,
    location: &str,
    detail: Option<&str>,
) -> Result<Value, String> {
    let safe_detail = detail.map(sanitize_detail);
    db.record_diagnostic_log(&json!({
        "traceId": trace_id,
        "action": action,
        "stage": stage,
        "status": status,
        "code": code,
        "message": message,
        "location": location,
        "detail": safe_detail,
    }))
    .map_err(|error| error.to_string())
}

pub fn failure_code(action: &str, error: &str) -> &'static str {
    if action == "media.process" {
        if error.contains("本机 MLX Whisper") {
            return "MEDIA_LOCAL_TRANSCRIPTION_FAILED";
        }
        if error.contains("无法读取本机转写结果") || error.contains("No such file or directory")
        {
            return "MEDIA_TRANSCRIPT_RESULT_MISSING";
        }
        if error.contains("yt-dlp") || error.contains("抖音") {
            return "MEDIA_DOWNLOAD_FAILED";
        }
        if error.contains("FFmpeg") || error.contains("ffmpeg") {
            return "MEDIA_AUDIO_EXTRACTION_FAILED";
        }
        if error.contains("转写") || error.contains("audio/transcriptions") {
            return "MEDIA_TRANSCRIPTION_FAILED";
        }
        return "MEDIA_PROCESS_FAILED";
    }
    if action.starts_with("llm.") {
        if error.contains("尚未配置") || error.contains("凭据库") || error.contains("offline")
        {
            return "LLM_CONFIGURATION_REQUIRED";
        }
        if error.contains("模型请求失败")
            || error.contains("模型连接失败")
            || error.contains("模型服务返回错误")
            || error.contains("模型服务暂时不可用")
        {
            return "LLM_REQUEST_FAILED";
        }
        return "LLM_RESPONSE_INVALID";
    }
    if action.starts_with("publish.") {
        return "PUBLISH_OPERATION_FAILED";
    }
    "RUNTIME_OPERATION_FAILED"
}

pub fn sanitize_detail(value: &str) -> String {
    let mut output = value.replace('\n', " ").replace('\r', " ");
    for pattern in [
        r"sk-[A-Za-z0-9_-]+",
        r"Bearer\s+[^\s]+",
        r"https?://[^\s]+",
        r"/(Users|private|var)/[^\s]+",
    ] {
        if let Ok(regex) = Regex::new(pattern) {
            output = regex.replace_all(&output, "[已脱敏]").into_owned();
        }
    }
    output.chars().take(1200).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sanitizes_credentials_urls_and_paths() {
        let path = format!("/{}/a/video.mp4", "Users");
        let value = sanitize_detail(&format!(
            "Bearer abc https://example.test/a sk-secret {path}"
        ));
        assert!(!value.contains("abc"));
        assert!(!value.contains("example.test"));
        assert!(!value.contains(&path));
    }

    #[test]
    fn classifies_service_error_envelopes_as_request_failures() {
        assert_eq!(
            failure_code("llm.proofread", "模型服务返回错误：GROUP_DISABLED"),
            "LLM_REQUEST_FAILED"
        );
    }

    #[test]
    fn classifies_exhausted_transient_retries_as_request_failures() {
        assert_eq!(
            failure_code(
                "llm.proofread",
                "模型服务暂时不可用（503 Service Unavailable）"
            ),
            "LLM_REQUEST_FAILED"
        );
    }
}
