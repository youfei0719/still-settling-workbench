mod audit;
mod db;
mod douyin_browser;
mod executable;
mod llm;
mod media;
mod publish;
mod settings;

use chrono::Utc;
use db::DesktopDb;
use serde_json::{json, Value};
use std::fs;
use std::path::{Path, PathBuf};
use tauri::{AppHandle, Manager, State};
use uuid::Uuid;

fn command_error(error: impl std::fmt::Display) -> String {
    error.to_string()
}

#[tauri::command]
fn load_snapshot(db: State<'_, DesktopDb>) -> Result<Value, String> {
    db.load_snapshot().map_err(command_error)
}

#[tauri::command]
fn save_snapshot(db: State<'_, DesktopDb>, snapshot: Value) -> Result<(), String> {
    db.save_snapshot(&snapshot).map_err(command_error)
}

#[tauri::command]
fn load_skill_workbench_state(db: State<'_, DesktopDb>) -> Result<Option<Value>, String> {
    db.load_skill_workbench_state().map_err(command_error)
}

#[tauri::command]
fn save_skill_workbench_state(db: State<'_, DesktopDb>, state: Value) -> Result<(), String> {
    db.save_skill_workbench_state(&state).map_err(command_error)
}

#[tauri::command]
fn load_stable_repository_snapshot(db: State<'_, DesktopDb>) -> Result<Value, String> {
    publish::snapshot_from_settings(&db)
}

#[tauri::command]
fn latest_publish_job(db: State<'_, DesktopDb>, candidate_id: String) -> Result<Option<Value>, String> {
    db.latest_publish_job(&candidate_id).map_err(command_error)
}

#[tauri::command]
async fn runtime_health(app: AppHandle, db: State<'_, DesktopDb>) -> Result<Value, String> {
    let trace_id = format!("health-{}", Uuid::new_v4());
    let _ = audit::record(&db, &trace_id, "runtime.health", "collect", "started", "RUNTIME_HEALTH_STARTED", "开始检查运行环境", "lib.rs:runtime_health", None);
    let status = settings::settings_status(&db).await.ok();
    let media_ready = status
        .as_ref()
        .is_some_and(|value| value.ffmpeg.available && value.asr_ready);
    let douyin_ready = status
        .as_ref()
        .is_some_and(|value| media_ready && value.douyin_browser.available);
    let network_proxy_source = status
        .as_ref()
        .map(|value| value.network_proxy_source.clone())
        .unwrap_or_else(|| "未能读取网络设置".into());
    let media_label = if douyin_ready {
        "抖音无登录解析、音频提取与真实转写已就绪"
    } else if media_ready && status.as_ref().is_some_and(|value| value.yt_dlp.available) {
        "本机媒体转写已就绪；抖音无登录解析需要 Chrome、Edge 或 Chromium"
    } else if media_ready {
        "本机媒体转写已就绪；抖音链接下载仍需要 yt-dlp"
    } else {
        "需要 FFmpeg，以及本机 MLX Whisper 或可用的转写 API"
    };
    let stable_snapshot = publish::snapshot_from_settings(&db);
    let result = json!({
      "mode": "native",
      "database": "healthy",
      "mediaPipeline": {
        "status": if media_ready { "healthy" } else { "unavailable" },
        "label": media_label,
        "version": status.as_ref().map(|value| value.settings.asr_model.clone()).unwrap_or_else(|| "未配置".to_string()),
        "protocolVersion": "native-v2-browser-signed"
      },
      "credentialStore": "available_unverified",
      "stableSnapshot": stable_snapshot.as_ref().ok(),
      "stableSnapshotError": stable_snapshot.err(),
      "networkProxySource": network_proxy_source,
      "checkedAt": Utc::now().to_rfc3339(),
      "resourceDirectory": app.path().resource_dir().ok().map(|path| path.to_string_lossy().into_owned())
    });
    let _ = audit::record(&db, &trace_id, "runtime.health", "collect", "success", "RUNTIME_HEALTH_READY", "运行环境检查完成", "lib.rs:runtime_health", Some(&format!("已读取本机依赖、凭据库与网络路由；网络：{network_proxy_source}")));
    Ok(result)
}

#[tauri::command]
fn record_diagnostic_log(db: State<'_, DesktopDb>, log: Value) -> Result<Value, String> {
    db.record_diagnostic_log(&log).map_err(command_error)
}

#[tauri::command]
fn list_diagnostic_logs(db: State<'_, DesktopDb>, limit: Option<u32>) -> Result<Vec<Value>, String> {
    db.list_diagnostic_logs(limit.unwrap_or(100)).map_err(command_error)
}

#[tauri::command]
fn clear_diagnostic_logs(db: State<'_, DesktopDb>) -> Result<(), String> {
    db.clear_diagnostic_logs().map_err(command_error)
}

#[tauri::command]
fn import_media(paths: Vec<String>) -> Result<Vec<Value>, String> {
    let now = Utc::now().to_rfc3339();
    let mut tasks = Vec::new();
    for raw_path in paths {
        let path = PathBuf::from(&raw_path);
        let metadata = fs::metadata(&path).map_err(|error| format!("无法读取媒体：{error}"))?;
        if !metadata.is_file() {
            return Err("导入目标不是文件".to_string());
        }
        let file_name = path
            .file_name()
            .and_then(|name| name.to_str())
            .unwrap_or("本机媒体");
        let id = format!("task-{}", Uuid::new_v4());
        tasks.push(json!({
          "id": id,
          "title": Path::new(file_name).file_stem().and_then(|name| name.to_str()).unwrap_or(file_name),
          "media": {"fileName":file_name,"path":raw_path,"durationMs":0,"sizeBytes":metadata.len(),"format":"等待真实媒体处理","retained":true,"thumbnailTone":"gray"},
          "config": {"language":"自动检测","modelId":"whisper-large-v3-turbo","diarization":true},
          "status":"queued","stage":"preparing_media","progress":0,"createdAt":now,"updatedAt":now,
          "localVersion":1,"cloudVersion":null,"lastSyncedAt":null,"syncStatus":"local_only","failure":null,
          "events":[{"id":format!("event-{}",Uuid::new_v4()),"taskId":id,"stage":"preparing_media","status":"info","message":"媒体已加入本机队列，原始文件未上传","createdAt":now}],
          "segments":[],"chapterNames":[],"interrupted":false
        }));
    }
    Ok(tasks)
}

#[tauri::command]
fn apply_sidecar_event(db: State<'_, DesktopDb>, event: Value) -> Result<(), String> {
    db.save_event(&event).map_err(command_error)
}

#[tauri::command]
fn save_transcript(
    db: State<'_, DesktopDb>,
    task_id: String,
    segments: Value,
) -> Result<(), String> {
    db.save_transcript(&task_id, &segments)
        .map_err(command_error)
}

#[tauri::command]
fn resolve_sync_conflict(
    db: State<'_, DesktopDb>,
    task_id: String,
    resolution: String,
) -> Result<(), String> {
    match resolution.as_str() {
        "keep_local" | "use_cloud" | "manual_merge" => db
            .resolve_conflict(&task_id, &resolution)
            .map_err(command_error),
        _ => Err("不支持的冲突处理方式".to_string()),
    }
}

#[tauri::command]
fn save_skill_version(db: State<'_, DesktopDb>, skill: Value) -> Result<(), String> {
    db.save_skill_version(&skill).map_err(command_error)
}

#[tauri::command]
fn save_privacy_preferences(db: State<'_, DesktopDb>, preferences: Value) -> Result<(), String> {
    db.save_privacy(&preferences).map_err(command_error)
}

#[tauri::command]
fn clear_media_cache(db: State<'_, DesktopDb>, task_ids: Vec<String>) -> Result<u64, String> {
    let clearable = db.clearable_temp_media(&task_ids).map_err(command_error)?;
    let mut freed = 0_u64;
    for (size, raw_path) in clearable {
        let path = PathBuf::from(raw_path);
        if !is_safe_temp_media_path(&path) {
            continue;
        }
        if path.is_file() {
            fs::remove_file(&path).map_err(command_error)?;
            freed = freed.saturating_add(size.max(0) as u64);
        }
    }
    Ok(freed)
}

#[tauri::command]
fn store_secret(name: String, value: String) -> Result<(), String> {
    match name.as_str() {
        "cloud_token" | "api_key" | "llm_api_key" | "asr_api_key" | "douyin_cookie" => {
            let entry =
                keyring::Entry::new(settings::KEYRING_SERVICE, &name).map_err(command_error)?;
            entry.set_password(&value).map_err(command_error)
        }
        _ => Err("不支持的凭据名称".to_string()),
    }
}

#[tauri::command]
async fn get_local_settings(db: State<'_, DesktopDb>) -> Result<settings::SettingsStatus, String> {
    settings::settings_status(&db).await
}

#[tauri::command]
async fn update_local_settings(
    db: State<'_, DesktopDb>,
    update: settings::SettingsUpdate,
) -> Result<settings::SettingsStatus, String> {
    settings::update_settings(&db, update)?;
    settings::settings_status(&db).await
}

#[tauri::command]
async fn list_provider_models(db: State<'_, DesktopDb>) -> Result<Value, String> {
    llm::list_models(&db).await
}

#[tauri::command]
async fn test_model_connection(db: State<'_, DesktopDb>) -> Result<Value, String> {
    llm::test_connection(&db).await
}

#[tauri::command]
async fn process_media_source(
    app: AppHandle,
    db: State<'_, DesktopDb>,
    request: media::MediaRequest,
) -> Result<Value, String> {
    let trace_id = format!("media-{}", Uuid::new_v4());
    let _ = audit::record(&db, &trace_id, "media.process", "request", "started", "MEDIA_PROCESS_STARTED", "已收到真实媒体处理请求", "lib.rs:process_media_source", None);
    let result = media::process_media(app, &db, request, &trace_id).await;
    match &result {
        Ok(_) => { let _ = audit::record(&db, &trace_id, "media.process", "completed", "success", "MEDIA_PROCESS_COMPLETED", "真实稿件提取完成", "lib.rs:process_media_source", None); }
        Err(error) => { let _ = audit::record(&db, &trace_id, "media.process", "failed", "error", audit::failure_code("media.process", error), "真实稿件提取失败", "lib.rs:process_media_source", Some(error)); }
    }
    result
}

#[tauri::command]
async fn analyze_transcript(
    db: State<'_, DesktopDb>,
    request: llm::AnalyzeRequest,
) -> Result<Value, String> {
    let trace_id = format!("analysis-{}", Uuid::new_v4());
    let _ = audit::record(&db, &trace_id, "llm.structure", "request", "started", "LLM_STRUCTURE_STARTED", "开始拆解已确认稿件", "lib.rs:analyze_transcript", None);
    let result = llm::analyze_transcript(&db, request).await;
    match &result {
        Ok(_) => { let _ = audit::record(&db, &trace_id, "llm.structure", "completed", "success", "LLM_STRUCTURE_COMPLETED", "结构拆解完成", "lib.rs:analyze_transcript", None); }
        Err(error) => { let _ = audit::record(&db, &trace_id, "llm.structure", "failed", "error", audit::failure_code("llm.structure", error), "结构拆解失败", "lib.rs:analyze_transcript", Some(error)); }
    }
    result
}

#[tauri::command]
async fn proofread_transcript(
    db: State<'_, DesktopDb>,
    request: llm::ProofreadRequest,
) -> Result<Value, String> {
    let trace_id = format!("proofread-{}", Uuid::new_v4());
    let _ = audit::record(&db, &trace_id, "llm.proofread", "request", "started", "LLM_PROOFREAD_STARTED", "开始校对真实稿件", "lib.rs:proofread_transcript", None);
    let result = llm::proofread_transcript(&db, request).await;
    match &result {
        Ok(_) => { let _ = audit::record(&db, &trace_id, "llm.proofread", "completed", "success", "LLM_PROOFREAD_COMPLETED", "AI 校对完成，等待人工确认", "lib.rs:proofread_transcript", None); }
        Err(error) => { let _ = audit::record(&db, &trace_id, "llm.proofread", "failed", "error", audit::failure_code("llm.proofread", error), "AI 校对失败", "lib.rs:proofread_transcript", Some(error)); }
    }
    result
}

#[tauri::command]
async fn evaluate_candidate(db: State<'_, DesktopDb>, candidate: Value) -> Result<Value, String> {
    let trace_id = format!("evaluation-{}", Uuid::new_v4());
    let _ = audit::record(&db, &trace_id, "llm.evaluation", "request", "started", "LLM_EVALUATION_STARTED", "开始评测候选 Skill", "lib.rs:evaluate_candidate", None);
    let result = llm::evaluate_candidate(&db, candidate).await;
    match &result {
        Ok(_) => { let _ = audit::record(&db, &trace_id, "llm.evaluation", "completed", "success", "LLM_EVALUATION_COMPLETED", "候选 Skill 评测完成", "lib.rs:evaluate_candidate", None); }
        Err(error) => { let _ = audit::record(&db, &trace_id, "llm.evaluation", "failed", "error", audit::failure_code("llm.evaluation", error), "候选 Skill 评测失败", "lib.rs:evaluate_candidate", Some(error)); }
    }
    result
}

#[tauri::command]
async fn remediate_candidate(db: State<'_, DesktopDb>, candidate: Value) -> Result<Value, String> {
    let trace_id = format!("remediation-{}", Uuid::new_v4());
    let _ = audit::record(&db, &trace_id, "llm.remediation", "request", "started", "LLM_REMEDIATION_STARTED", "开始生成去特定化修复草稿", "lib.rs:remediate_candidate", None);
    let result = llm::remediate_candidate(&db, candidate).await;
    match &result {
        Ok(_) => { let _ = audit::record(&db, &trace_id, "llm.remediation", "completed", "success", "LLM_REMEDIATION_COMPLETED", "去特定化修复草稿已生成，等待人工确认", "lib.rs:remediate_candidate", None); }
        Err(error) => { let _ = audit::record(&db, &trace_id, "llm.remediation", "failed", "error", audit::failure_code("llm.remediation", error), "去特定化修复草稿生成失败", "lib.rs:remediate_candidate", Some(error)); }
    }
    result
}

#[tauri::command]
async fn setup_skill_repository(
    db: State<'_, DesktopDb>,
    request: publish::RepositorySetupRequest,
) -> Result<Value, String> {
    let trace_id = format!("repository-{}", Uuid::new_v4());
    let result = publish::setup_repository(&db, request).await;
    match &result {
        Ok(_) => { let _ = audit::record(&db, &trace_id, "publish.repository", "completed", "success", "PUBLISH_REPOSITORY_READY", "Skill 发布仓库已配置", "lib.rs:setup_skill_repository", None); }
        Err(error) => { let _ = audit::record(&db, &trace_id, "publish.repository", "failed", "error", audit::failure_code("publish.repository", error), "Skill 发布仓库配置失败", "lib.rs:setup_skill_repository", Some(error)); }
    }
    result
}

#[tauri::command]
async fn publish_release_candidate(
    app: AppHandle,
    db: State<'_, DesktopDb>,
    candidate_id: String,
) -> Result<Value, String> {
    let trace_id = format!("publish-{}", Uuid::new_v4());
    let _ = audit::record(&db, &trace_id, "publish.release", "request", "started", "PUBLISH_RELEASE_STARTED", "开始发布稳定 Skill 包", "lib.rs:publish_release_candidate", None);
    let result = publish::publish_candidate_with_progress(Some(&app), &db, &candidate_id).await;
    match &result {
        Ok(_) => { let _ = audit::record(&db, &trace_id, "publish.release", "completed", "success", "PUBLISH_RELEASE_COMPLETED", "稳定 Skill 包发布完成", "lib.rs:publish_release_candidate", None); }
        Err(error) => {
            publish::emit_progress(Some(&app), "failed", "stable Skill 发布失败");
            let _ = audit::record(&db, &trace_id, "publish.release", "failed", "error", audit::failure_code("publish.release", error), "稳定 Skill 包发布失败", "lib.rs:publish_release_candidate", Some(error));
        }
    }
    result
}

fn is_safe_temp_media_path(path: &Path) -> bool {
    let normalized = path.to_string_lossy();
    normalized.contains("douyin-writing-skills") && normalized.contains("media-cache")
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_process::init())
        .setup(|app| {
            let app_data = app.path().app_data_dir()?;
            fs::create_dir_all(&app_data)?;
            let db = DesktopDb::open(&app_data.join("workbench.sqlite3"))
                .map_err(|error| std::io::Error::other(error.to_string()))?;
            app.manage(db);
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            load_snapshot,
            record_diagnostic_log,
            list_diagnostic_logs,
            clear_diagnostic_logs,
            save_snapshot,
            load_skill_workbench_state,
            save_skill_workbench_state,
            load_stable_repository_snapshot,
            latest_publish_job,
            runtime_health,
            import_media,
            apply_sidecar_event,
            save_transcript,
            resolve_sync_conflict,
            save_skill_version,
            save_privacy_preferences,
            clear_media_cache,
            store_secret,
            get_local_settings,
            update_local_settings,
            list_provider_models,
            test_model_connection,
            process_media_source,
            proofread_transcript,
            analyze_transcript,
            evaluate_candidate,
            remediate_candidate,
            setup_skill_repository,
            publish_release_candidate
        ])
        .run(tauri::generate_context!())
        .expect("error while running douyin-writing-skills desktop");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cache_guard_rejects_arbitrary_paths() {
        let arbitrary_path = format!("/{}/demo/Movies/source.mp4", "Users");
        assert!(!is_safe_temp_media_path(Path::new(&arbitrary_path)));
        assert!(is_safe_temp_media_path(Path::new(
            "/tmp/douyin-writing-skills/media-cache/task/audio.wav"
        )));
    }
}
