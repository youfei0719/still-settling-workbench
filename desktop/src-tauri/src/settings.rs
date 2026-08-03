use crate::db::DesktopDb;
use crate::executable::{resolve_browser_executable, resolve_executable};
use reqwest::{Client, Proxy};
use serde::{Deserialize, Serialize};
use std::path::Path;
use std::process::Command as StdCommand;
use tokio::process::Command;

pub const SETTINGS_KEY: &str = "workbench_settings_v1";
pub const KEYRING_SERVICE: &str = "com.youfei.douyin-writing-skills";
pub const LOCAL_MLX_ASR_BASE: &str = "local://mlx-whisper";

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct WorkbenchSettings {
    pub llm_mode: String,
    pub llm_model: String,
    pub llm_api_base: String,
    pub asr_model: String,
    pub asr_api_base: String,
    pub skill_sync_mode: String,
    pub skill_repository_path: String,
    pub skill_remote: String,
    pub skill_remote_url: String,
    pub skill_branch: String,
    #[serde(default)]
    pub network_proxy: String,
}

impl Default for WorkbenchSettings {
    fn default() -> Self {
        Self {
            llm_mode: "offline".into(),
            llm_model: "gpt-4.1-mini".into(),
            llm_api_base: "https://api.openai.com/v1".into(),
            asr_model: "whisper-1".into(),
            asr_api_base: "https://api.openai.com/v1".into(),
            skill_sync_mode: "local".into(),
            skill_repository_path: String::new(),
            skill_remote: "origin".into(),
            skill_remote_url: String::new(),
            skill_branch: "main".into(),
            network_proxy: String::new(),
        }
    }
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SettingsUpdate {
    pub llm_mode: Option<String>,
    pub llm_model: Option<String>,
    pub llm_api_base: Option<String>,
    pub llm_api_key: Option<String>,
    pub asr_model: Option<String>,
    pub asr_api_base: Option<String>,
    pub asr_api_key: Option<String>,
    pub douyin_cookie_string: Option<String>,
    pub skill_sync_mode: Option<String>,
    pub skill_repository_path: Option<String>,
    pub skill_remote: Option<String>,
    pub skill_remote_url: Option<String>,
    pub skill_branch: Option<String>,
    pub clear_llm_key: Option<bool>,
    pub clear_asr_key: Option<bool>,
    pub clear_douyin_cookie: Option<bool>,
    pub network_proxy: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ToolStatus {
    pub available: bool,
    pub version: String,
    pub executable_path: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SettingsStatus {
    #[serde(flatten)]
    pub settings: WorkbenchSettings,
    pub llm_api_key_configured: bool,
    pub asr_api_key_configured: bool,
    pub asr_ready: bool,
    pub asr_backend: String,
    pub douyin_cookie_configured: bool,
    pub publish_configured: bool,
    pub secret_storage: String,
    pub network_proxy_source: String,
    pub yt_dlp: ToolStatus,
    pub douyin_browser: ToolStatus,
    pub ffmpeg: ToolStatus,
    pub mlx_whisper: ToolStatus,
    pub git: ToolStatus,
    pub gh: ToolStatus,
}

pub fn load_settings(db: &DesktopDb) -> Result<WorkbenchSettings, String> {
    match db
        .load_app_value(SETTINGS_KEY)
        .map_err(|error| error.to_string())?
    {
        Some(value) => serde_json::from_value(value).map_err(|error| error.to_string()),
        None => Ok(WorkbenchSettings::default()),
    }
}

pub fn save_settings(db: &DesktopDb, settings: &WorkbenchSettings) -> Result<(), String> {
    db.save_app_value(
        SETTINGS_KEY,
        &serde_json::to_value(settings).map_err(|error| error.to_string())?,
    )
    .map_err(|error| error.to_string())
}

fn validate_mode(value: &str, accepted: &[&str], label: &str) -> Result<(), String> {
    if accepted.contains(&value) {
        Ok(())
    } else {
        Err(format!("{label}无效"))
    }
}

fn clean_base(value: String) -> Result<String, String> {
    let value = value.trim().trim_end_matches('/').to_string();
    let parsed =
        url::Url::parse(&value).map_err(|_| "API Base 必须是完整的 HTTPS 地址".to_string())?;
    if parsed.scheme() != "https" && !matches!(parsed.host_str(), Some("127.0.0.1" | "localhost")) {
        return Err("API Base 仅允许 HTTPS，或本机 localhost 调试地址".into());
    }
    Ok(value)
}

fn clean_asr_base(value: String) -> Result<String, String> {
    let value = value.trim().trim_end_matches('/').to_string();
    if value == LOCAL_MLX_ASR_BASE {
        return Ok(value);
    }
    clean_base(value)
}

fn clean_network_proxy(value: String) -> Result<String, String> {
    let value = value.trim().trim_end_matches('/').to_string();
    if value.is_empty() {
        return Ok(value);
    }
    let parsed = url::Url::parse(&value).map_err(|_| "网络代理必须是完整的 HTTP 或 HTTPS 地址".to_string())?;
    if !matches!(parsed.scheme(), "http" | "https") || parsed.host_str().is_none() {
        return Err("网络代理必须是完整的 HTTP 或 HTTPS 地址".into());
    }
    if !parsed.username().is_empty() || parsed.password().is_some() {
        return Err("网络代理不能包含用户名或密码；请在系统代理工具中配置认证".into());
    }
    Ok(value)
}

#[derive(Clone, Debug)]
pub struct ProxyRoute {
    pub url: String,
    pub source: &'static str,
}

fn environment_proxy() -> Option<String> {
    ["HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"]
        .iter()
        .find_map(|key| std::env::var(key).ok().filter(|value| !value.trim().is_empty()))
}

#[cfg(target_os = "macos")]
fn macos_system_proxy() -> Option<String> {
    let output = StdCommand::new("scutil").arg("--proxy").output().ok()?;
    if !output.status.success() {
        return None;
    }
    let values = String::from_utf8_lossy(&output.stdout)
        .lines()
        .filter_map(|line| line.split_once(':').map(|(key, value)| (key.trim().to_string(), value.trim().to_string())))
        .collect::<std::collections::HashMap<_, _>>();
    for prefix in ["HTTPS", "HTTP"] {
        if values.get(&format!("{prefix}Enable")).is_some_and(|value| value == "1") {
            let host = values.get(&format!("{prefix}Proxy"))?;
            let port = values.get(&format!("{prefix}Port"))?;
            if host.is_empty() || port.parse::<u16>().ok().filter(|port| *port > 0).is_none() {
                continue;
            }
            return Some(format!("http://{host}:{port}"));
        }
    }
    None
}

#[cfg(not(target_os = "macos"))]
fn macos_system_proxy() -> Option<String> { None }

pub fn proxy_route(settings: &WorkbenchSettings) -> Result<Option<ProxyRoute>, String> {
    if !settings.network_proxy.trim().is_empty() {
        return Ok(Some(ProxyRoute { url: clean_network_proxy(settings.network_proxy.clone())?, source: "手动代理" }));
    }
    if let Some(url) = environment_proxy() {
        return Ok(Some(ProxyRoute { url: clean_network_proxy(url)?, source: "环境代理" }));
    }
    if let Some(url) = macos_system_proxy() {
        return Ok(Some(ProxyRoute { url: clean_network_proxy(url)?, source: "系统代理" }));
    }
    Ok(None)
}

pub fn api_client(settings: &WorkbenchSettings, timeout_seconds: u64) -> Result<(Client, Option<ProxyRoute>), String> {
    let route = proxy_route(settings)?;
    let mut builder = Client::builder().timeout(std::time::Duration::from_secs(timeout_seconds));
    if let Some(proxy) = &route {
        builder = builder.proxy(Proxy::all(&proxy.url).map_err(|error| format!("网络代理无效：{error}"))?);
    }
    Ok((builder.build().map_err(|error| error.to_string())?, route))
}

pub fn uses_local_mlx_asr(settings: &WorkbenchSettings) -> bool {
    settings.asr_api_base == LOCAL_MLX_ASR_BASE
}

fn set_secret(name: &str, value: Option<String>, clear: bool) -> Result<(), String> {
    let entry = keyring::Entry::new(KEYRING_SERVICE, name).map_err(|error| error.to_string())?;
    if clear {
        let _ = entry.delete_credential();
        return Ok(());
    }
    if let Some(value) = value.filter(|value| !value.trim().is_empty()) {
        entry
            .set_password(value.trim())
            .map_err(|error| error.to_string())?;
    }
    Ok(())
}

pub fn read_secret(name: &str) -> Result<Option<String>, String> {
    let entry = keyring::Entry::new(KEYRING_SERVICE, name).map_err(|error| error.to_string())?;
    match entry.get_password() {
        Ok(value) if !value.trim().is_empty() => Ok(Some(value)),
        Ok(_) | Err(keyring::Error::NoEntry) => Ok(None),
        Err(error) => Err(error.to_string()),
    }
}

pub fn update_settings(
    db: &DesktopDb,
    update: SettingsUpdate,
) -> Result<WorkbenchSettings, String> {
    let mut settings = load_settings(db)?;
    if let Some(value) = update.llm_mode {
        validate_mode(&value, &["offline", "optional", "required"], "模型模式")?;
        settings.llm_mode = value;
    }
    if let Some(value) = update.llm_model {
        settings.llm_model = value.trim().to_string();
    }
    if let Some(value) = update.llm_api_base {
        settings.llm_api_base = clean_base(value)?;
    }
    if let Some(value) = update.asr_model {
        settings.asr_model = value.trim().to_string();
    }
    if let Some(value) = update.asr_api_base {
        settings.asr_api_base = clean_asr_base(value)?;
    }
    if let Some(value) = update.network_proxy {
        settings.network_proxy = clean_network_proxy(value)?;
    }
    if let Some(value) = update.skill_sync_mode {
        validate_mode(&value, &["local", "github"], "同步方式")?;
        settings.skill_sync_mode = value;
    }
    if let Some(value) = update.skill_repository_path {
        settings.skill_repository_path = value.trim().to_string();
    }
    if let Some(value) = update.skill_remote {
        settings.skill_remote = value.trim().to_string();
    }
    if let Some(value) = update.skill_remote_url {
        settings.skill_remote_url = value.trim().to_string();
    }
    if let Some(value) = update.skill_branch {
        settings.skill_branch = value.trim().to_string();
    }
    set_secret(
        "llm_api_key",
        update.llm_api_key,
        update.clear_llm_key.unwrap_or(false),
    )?;
    set_secret(
        "asr_api_key",
        update.asr_api_key,
        update.clear_asr_key.unwrap_or(false),
    )?;
    set_secret(
        "douyin_cookie",
        update.douyin_cookie_string,
        update.clear_douyin_cookie.unwrap_or(false),
    )?;
    save_settings(db, &settings)?;
    Ok(settings)
}

fn version_argument(command: &str) -> &'static str {
    if command.eq_ignore_ascii_case("ffmpeg") {
        "-version"
    } else {
        "--version"
    }
}

async fn tool_status(command: &str) -> ToolStatus {
    let Some(executable) = resolve_executable(command) else {
        return ToolStatus {
            available: false,
            version: "未安装；已检查 PATH 和常见安装目录".into(),
            executable_path: None,
        };
    };
    if command.eq_ignore_ascii_case("mlx_whisper") {
        return ToolStatus {
            available: true,
            version: "本机 MLX Whisper CLI".into(),
            executable_path: Some(executable.to_string_lossy().into_owned()),
        };
    }
    let output = Command::new(&executable)
        .arg(version_argument(command))
        .output()
        .await;
    match output {
        Ok(output) if output.status.success() => {
            let value = String::from_utf8_lossy(&output.stdout).trim().to_string();
            let fallback = String::from_utf8_lossy(&output.stderr).trim().to_string();
            ToolStatus {
                available: true,
                version: value
                    .lines()
                    .next()
                    .unwrap_or(&fallback)
                    .chars()
                    .take(120)
                    .collect(),
                executable_path: Some(executable.to_string_lossy().into_owned()),
            }
        }
        _ => ToolStatus {
            available: false,
            version: "已找到，但执行 --version 失败".into(),
            executable_path: Some(executable.to_string_lossy().into_owned()),
        },
    }
}

async fn browser_status() -> ToolStatus {
    let Some(executable) = resolve_browser_executable() else {
        return ToolStatus {
            available: false,
            version: "未找到 Chrome、Edge 或 Chromium".into(),
            executable_path: None,
        };
    };
    match Command::new(&executable).arg("--version").output().await {
        Ok(output) if output.status.success() => {
            let stdout = String::from_utf8_lossy(&output.stdout);
            let stderr = String::from_utf8_lossy(&output.stderr);
            let version = stdout
                .lines()
                .chain(stderr.lines())
                .find(|line| !line.trim().is_empty())
                .unwrap_or("已找到 Chromium 内核浏览器")
                .chars()
                .take(120)
                .collect();
            ToolStatus {
                available: true,
                version,
                executable_path: Some(executable.to_string_lossy().into_owned()),
            }
        }
        _ => ToolStatus {
            available: false,
            version: "已找到浏览器，但无法启动无登录解析器".into(),
            executable_path: Some(executable.to_string_lossy().into_owned()),
        },
    }
}

pub async fn settings_status(db: &DesktopDb) -> Result<SettingsStatus, String> {
    let settings = load_settings(db)?;
    let (yt_dlp, douyin_browser, ffmpeg, mlx_whisper, git, gh) = tokio::join!(
        tool_status("yt-dlp"),
        browser_status(),
        tool_status("ffmpeg"),
        tool_status("mlx_whisper"),
        tool_status("git"),
        tool_status("gh")
    );
    let local_asr = uses_local_mlx_asr(&settings);
    let proxy_source = proxy_route(&settings)?.map(|route| route.source.to_string()).unwrap_or_else(|| "直连".into());
    let asr_api_key_configured =
        read_secret("asr_api_key")?.is_some() || read_secret("llm_api_key")?.is_some();
    let repository_ready = !settings.skill_repository_path.is_empty()
        && Path::new(&settings.skill_repository_path)
            .join(".git")
            .is_dir();
    Ok(SettingsStatus {
        llm_api_key_configured: read_secret("llm_api_key")?.is_some(),
        asr_api_key_configured,
        asr_ready: if local_asr {
            mlx_whisper.available
        } else {
            asr_api_key_configured
        },
        asr_backend: if local_asr {
            "local_mlx".into()
        } else {
            "openai_compatible_api".into()
        },
        douyin_cookie_configured: read_secret("douyin_cookie")?.is_some(),
        publish_configured: repository_ready,
        secret_storage: "system_keyring".into(),
        network_proxy_source: proxy_source,
        settings,
        yt_dlp,
        douyin_browser,
        ffmpeg,
        mlx_whisper,
        git,
        gh,
    })
}

#[cfg(test)]
mod tests {
    use super::{
        clean_asr_base, uses_local_mlx_asr, version_argument, WorkbenchSettings, LOCAL_MLX_ASR_BASE,
    };

    #[test]
    fn uses_ffmpegs_supported_version_flag() {
        assert_eq!(version_argument("ffmpeg"), "-version");
        assert_eq!(version_argument("git"), "--version");
    }

    #[test]
    fn accepts_local_mlx_asr_without_weakening_remote_url_validation() {
        assert_eq!(
            clean_asr_base(LOCAL_MLX_ASR_BASE.into()).unwrap(),
            LOCAL_MLX_ASR_BASE
        );
        assert!(clean_asr_base("http://example.com/v1".into()).is_err());

        let mut settings = WorkbenchSettings::default();
        settings.asr_api_base = LOCAL_MLX_ASR_BASE.into();
        assert!(uses_local_mlx_asr(&settings));
    }
}
