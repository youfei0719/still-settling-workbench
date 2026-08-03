use crate::executable::resolve_browser_executable;
use chromiumoxide::browser::{Browser, BrowserConfig};
use futures::StreamExt;
use serde_json::{json, Value};
use std::path::{Path, PathBuf};
use std::time::Duration;

pub fn browser_executable() -> Option<PathBuf> {
    resolve_browser_executable()
}

pub fn aweme_id(url: &str) -> Result<String, String> {
    let parsed = url::Url::parse(url).map_err(|_| "抖音链接格式无效".to_string())?;
    if !parsed
        .host_str()
        .is_some_and(|host| host == "douyin.com" || host.ends_with(".douyin.com"))
    {
        return Err("不是可支持的抖音链接".into());
    }
    let segments: Vec<_> = parsed
        .path_segments()
        .into_iter()
        .flatten()
        .filter(|segment| !segment.is_empty())
        .collect();
    if let Some(id) = segments
        .windows(2)
        .find(|parts| {
            parts[0] == "video" && parts[1].chars().all(|character| character.is_ascii_digit())
        })
        .map(|parts| parts[1])
    {
        return Ok(id.to_string());
    }
    if let Some(id) = parsed
        .query_pairs()
        .find(|(key, value)| {
            key == "modal_id" && value.chars().all(|character| character.is_ascii_digit())
        })
        .map(|(_, value)| value.into_owned())
    {
        return Ok(id);
    }
    Err("抖音链接中没有可识别的视频 ID".into())
}

fn append_media_urls(target: &mut Vec<String>, address: Option<&Value>) {
    let Some(urls) = address
        .and_then(|value| value.get("url_list"))
        .and_then(Value::as_array)
    else {
        return;
    };
    for value in urls.iter().filter_map(Value::as_str) {
        if url::Url::parse(value)
            .ok()
            .is_some_and(|url| url.scheme() == "https")
            && !target.iter().any(|existing| existing == value)
        {
            target.push(value.to_string());
        }
    }
}

fn parse_detail_response(raw: &str, expected_video_id: &str) -> Result<Value, String> {
    let payload: Value =
        serde_json::from_str(raw).map_err(|error| format!("详情 JSON 无效：{error}"))?;
    let aweme = payload
        .get("aweme_detail")
        .ok_or_else(|| "详情响应缺少 aweme_detail".to_string())?;
    let actual_video_id = aweme
        .get("aweme_id")
        .and_then(Value::as_str)
        .unwrap_or("缺失");
    if actual_video_id != expected_video_id {
        return Err(format!("详情响应属于其他视频：{actual_video_id}"));
    }
    let video = aweme
        .get("video")
        .ok_or_else(|| "详情响应缺少 video".to_string())?;
    let mut media_urls = Vec::new();
    append_media_urls(&mut media_urls, video.get("play_addr"));
    append_media_urls(&mut media_urls, video.get("download_addr"));
    if let Some(rates) = video.get("bit_rate").and_then(Value::as_array) {
        for rate in rates {
            append_media_urls(&mut media_urls, rate.get("play_addr"));
        }
    }
    if media_urls.is_empty() {
        return Err("详情响应不包含 HTTPS 媒体地址".into());
    }
    Ok(json!({
        "awemeId": expected_video_id,
        "title": aweme.get("desc").and_then(Value::as_str).unwrap_or("抖音授权视频"),
        "author": aweme.pointer("/author/nickname").and_then(Value::as_str),
        "timestamp": aweme.get("create_time").and_then(Value::as_i64),
        "durationMs": video.get("duration").and_then(Value::as_u64),
        "mediaUrls": media_urls
    }))
}

pub async fn resolve_public_video(
    url: &str,
    profile_dir: &Path,
    bypass_system_proxy: bool,
) -> Result<Value, String> {
    let video_id = aweme_id(url)?;
    let executable = browser_executable()
        .ok_or_else(|| "未找到 Google Chrome、Microsoft Edge 或 Chromium".to_string())?;
    let mut config = BrowserConfig::builder()
        .chrome_executable(executable)
        .user_data_dir(profile_dir)
        .request_timeout(Duration::from_secs(30))
        .arg(("disable-blink-features", "AutomationControlled"));
    if bypass_system_proxy {
        config = config.arg("no-proxy-server");
    }
    let config = config
        .build()
        .map_err(|error| format!("无法创建临时浏览器配置：{error}"))?;
    let (mut browser, mut handler) = Browser::launch(config)
        .await
        .map_err(|error| format!("无法启动临时浏览器：{error}"))?;
    let handler_task = tokio::spawn(async move {
        while let Some(event) = handler.next().await {
            if event.is_err() {
                break;
            }
        }
    });
    let page = browser
        .new_page("about:blank")
        .await
        .map_err(|error| format!("无法创建临时浏览器页面：{error}"))?;
    page.evaluate_on_new_document(
        "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });",
    )
    .await
    .map_err(|error| format!("无法初始化浏览器兼容模式：{error}"))?;
    page.goto(url)
        .await
        .map_err(|error| format!("抖音页面加载失败：{error}"))?;
    tokio::time::sleep(Duration::from_secs(7)).await;
    let endpoint = format!("https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id={video_id}");
    let endpoint = serde_json::to_string(&endpoint).map_err(|error| error.to_string())?;
    let script = format!(
        r#"async () => {{
          const controller = new AbortController();
          const timer = setTimeout(() => controller.abort(), 10000);
          try {{
            const response = await fetch({endpoint}, {{ credentials: 'include', cache: 'no-store', signal: controller.signal }});
            if (!response.ok) throw new Error(`HTTP ${{response.status}}`);
            return await response.text();
          }} finally {{
            clearTimeout(timer);
          }}
        }}"#
    );
    let mut last_error = "抖音详情请求没有返回结果".to_string();
    for attempt in 0..4 {
        if attempt > 0 {
            tokio::time::sleep(Duration::from_secs(2)).await;
        }
        let raw = match tokio::time::timeout(
            Duration::from_secs(15),
            page.evaluate_function(script.clone()),
        )
        .await
        {
            Ok(Ok(value)) => match value.into_value::<String>() {
                Ok(value) => value,
                Err(error) => {
                    last_error = format!("抖音详情响应无法读取：{error}");
                    continue;
                }
            },
            Ok(Err(error)) => {
                last_error = error.to_string();
                continue;
            }
            Err(_) => {
                last_error = "抖音详情请求超时".into();
                continue;
            }
        };
        if raw.is_empty() {
            last_error = "抖音详情请求返回空响应".into();
            continue;
        }
        match parse_detail_response(&raw, &video_id) {
            Ok(value) => {
                let _ = browser.close().await;
                let _ = tokio::time::timeout(Duration::from_secs(3), handler_task).await;
                return Ok(value);
            }
            Err(error) => {
                last_error = error;
            }
        }
    }
    let _ = browser.close().await;
    let _ = tokio::time::timeout(Duration::from_secs(3), handler_task).await;
    Err(format!("抖音无登录解析重试后仍失败：{last_error}"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn extracts_video_and_modal_ids() {
        assert_eq!(
            aweme_id("https://www.douyin.com/video/7667525275554549018").unwrap(),
            "7667525275554549018"
        );
        assert_eq!(
            aweme_id("https://www.douyin.com/user/example?modal_id=7667525275554549018").unwrap(),
            "7667525275554549018"
        );
        assert!(aweme_id("https://example.com/video/7667525275554549018").is_err());
    }

    #[test]
    fn parses_progressive_media_before_rate_variants() {
        let payload = json!({
            "aweme_detail": {
                "aweme_id": "123",
                "desc": "测试视频",
                "author": { "nickname": "作者" },
                "create_time": 1234,
                "video": {
                    "duration": 5678,
                    "play_addr": { "url_list": ["https://media.example/progressive.mp4"] },
                    "download_addr": { "url_list": ["https://media.example/download.mp4"] },
                    "bit_rate": [{
                        "play_addr": { "url_list": ["https://media.example/rate.mp4"] }
                    }]
                }
            }
        });
        let detail = parse_detail_response(&payload.to_string(), "123").unwrap();
        assert_eq!(
            detail.pointer("/mediaUrls/0").and_then(Value::as_str),
            Some("https://media.example/progressive.mp4")
        );
        assert!(parse_detail_response(&payload.to_string(), "456").is_err());
    }

    #[tokio::test]
    #[ignore = "requires network and an installed Chromium browser"]
    async fn resolves_public_video_without_existing_browser_profile() {
        let profile = tempfile::tempdir().unwrap();
        let value = resolve_public_video(
            "https://www.douyin.com/video/7667525275554549018",
            profile.path(),
            true,
        )
        .await
        .unwrap();
        assert_eq!(
            value.get("awemeId").and_then(Value::as_str),
            Some("7667525275554549018")
        );
        assert!(!value
            .get("mediaUrls")
            .and_then(Value::as_array)
            .unwrap()
            .is_empty());
    }
}
