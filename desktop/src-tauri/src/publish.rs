use crate::db::DesktopDb;
use crate::executable::require_executable;
use crate::settings::{api_client, load_settings, save_settings, WorkbenchSettings};
use chrono::Utc;
use serde::Deserialize;
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use tauri::{AppHandle, Emitter};
use tokio::process::Command;
use uuid::Uuid;

const ROOT_SKILL: &str = include_str!("../resources/skill-loader/SKILL.md");
const LOAD_LATEST: &str = include_str!("../resources/skill-loader/scripts/load_latest.py");
const RUNTIME_PACKAGE: &str = include_str!("../resources/skill-loader/scripts/runtime_package.py");
const INSTALL_SH: &str = include_str!("../resources/skill-loader/scripts/install.sh");
const INSTALL_PS1: &str = include_str!("../resources/skill-loader/scripts/install.ps1");
const LOADER_SCHEMA_VERSION: i64 = 2;

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PublishProgress<'a> {
    pub stage: &'a str,
    pub message: &'a str,
}

pub fn emit_progress(app: Option<&AppHandle>, stage: &str, message: &str) {
    if let Some(app) = app {
        let _ = app.emit("publish-progress", PublishProgress { stage, message });
    }
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RepositorySetupRequest {
    pub mode: String,
    pub repository_url: Option<String>,
    pub repository_name: Option<String>,
    pub visibility: Option<String>,
    pub local_parent_path: Option<String>,
}

async fn command_output(command: &str, args: &[String], current_dir: Option<&Path>) -> Result<String, String> {
    command_output_with_env(command, args, current_dir, &[]).await
}

async fn command_output_with_env(
    command: &str,
    args: &[String],
    current_dir: Option<&Path>,
    environment: &[(&str, String)],
) -> Result<String, String> {
    let executable = require_executable(command)?;
    let mut process = Command::new(executable);
    process.args(args);
    if let Some(directory) = current_dir { process.current_dir(directory); }
    for (key, value) in environment { process.env(key, value); }
    let output = process.output().await.map_err(|error| format!("无法启动 {command}：{error}"))?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
        let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
        return Err(if stderr.is_empty() { stdout } else { stderr });
    }
    Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
}

fn safe_repository_name(value: &str) -> Result<String, String> {
    let value = value.trim().trim_end_matches('/').trim_end_matches(".git");
    let name = value.rsplit('/').next().unwrap_or(value);
    if name.is_empty() || name.len() > 100 || !name.chars().all(|ch| ch.is_ascii_alphanumeric() || ".-_".contains(ch)) {
        return Err("项目名称只能包含字母、数字、点、下划线和连字符".into());
    }
    Ok(name.to_string())
}

fn setup_parent(value: Option<String>) -> Result<PathBuf, String> {
    let parent = value.filter(|value| !value.trim().is_empty()).map(PathBuf::from)
        .or_else(|| dirs::document_dir().map(|path| path.join("DouyinWritingSkills")))
        .ok_or_else(|| "无法确定本地项目目录".to_string())?;
    fs::create_dir_all(&parent).map_err(|error| format!("无法创建项目目录：{error}"))?;
    Ok(parent)
}

fn write_if_missing(path: &Path, content: &str) -> Result<(), String> {
    if path.exists() { return Ok(()); }
    if let Some(parent) = path.parent() { fs::create_dir_all(parent).map_err(|error| error.to_string())?; }
    fs::write(path, content).map_err(|error| error.to_string())
}

fn github_source(remote_url: &str, branch: &str) -> Option<Value> {
    let normalized = remote_url.trim().trim_end_matches('/').trim_end_matches(".git");
    let path = normalized.strip_prefix("https://github.com/")
        .or_else(|| normalized.strip_prefix("git@github.com:"))?;
    let mut parts = path.split('/');
    let owner = parts.next()?.trim();
    let repository = parts.next()?.trim();
    if owner.is_empty() || repository.is_empty() || parts.next().is_some() { return None; }
    Some(json!({
        "loader_schema_version": LOADER_SCHEMA_VERSION,
        "provider": "github",
        "owner": owner,
        "repository": repository,
        "branch": branch,
        "manifest_path": "published/stable/manifest.json"
    }))
}

fn write_loader_source(repository: &Path, sync_mode: &str, remote_url: &str, branch: &str) -> Result<(), String> {
    let source = if sync_mode == "github" {
        github_source(remote_url, branch).ok_or_else(|| "无法从 GitHub remote 推导固定加载器来源".to_string())?
    } else {
        json!({
            "loader_schema_version": LOADER_SCHEMA_VERSION,
            "provider": "local",
            "repository_path": repository.to_string_lossy(),
            "manifest_path": "published/stable/manifest.json"
        })
    };
    fs::write(repository.join("skill-source.json"), format!("{}\n", serde_json::to_string_pretty(&source).map_err(|error| error.to_string())?))
        .map_err(|error| error.to_string())
}

fn seed_loader(repository: &Path, sync_mode: &str, remote_url: &str, branch: &str) -> Result<(), String> {
    write_if_missing(&repository.join("SKILL.md"), ROOT_SKILL)?;
    write_if_missing(&repository.join("scripts/load_latest.py"), LOAD_LATEST)?;
    write_if_missing(&repository.join("scripts/runtime_package.py"), RUNTIME_PACKAGE)?;
    write_if_missing(&repository.join("scripts/install.sh"), INSTALL_SH)?;
    write_if_missing(&repository.join("scripts/install.ps1"), INSTALL_PS1)?;
    write_loader_source(repository, sync_mode, remote_url, branch)
}

async fn initialize_loader(repository: &Path, sync_mode: &str, remote_url: &str, branch: &str) -> Result<(), String> {
    seed_loader(repository, sync_mode, remote_url, branch)?;
    let mut add = vec!["add".into(), "--".into()];
    add.extend(["SKILL.md", "skill-source.json", "scripts/load_latest.py", "scripts/runtime_package.py", "scripts/install.sh", "scripts/install.ps1"].iter().map(|path| path.to_string()));
    command_output("git", &add, Some(repository)).await?;
    let staged = command_output("git", &["diff".into(), "--cached".into(), "--name-only".into()], Some(repository)).await?;
    if !staged.is_empty() {
        command_output("git", &["commit".into(), "-m".into(), "Initialize fixed Skill loader".into()], Some(repository)).await?;
    }
    Ok(())
}

fn loader_files_present(repository: &Path) -> Result<(), String> {
    for path in ["SKILL.md", "skill-source.json", "scripts/load_latest.py", "scripts/runtime_package.py", "scripts/install.sh", "scripts/install.ps1"] {
        if !repository.join(path).is_file() {
            return Err(format!("固定加载器缺少 {path}；请先初始化或修复加载器"));
        }
    }
    Ok(())
}

pub async fn setup_repository(db: &DesktopDb, request: RepositorySetupRequest) -> Result<Value, String> {
    let parent = setup_parent(request.local_parent_path)?;
    let (repository, remote_url, sync_mode) = match request.mode.as_str() {
        "connect" => {
            let url = request.repository_url.as_deref().ok_or_else(|| "请填写 GitHub 仓库地址".to_string())?;
            if github_source(url, "main").is_none() { return Err("只支持连接 GitHub HTTPS 或 SSH 仓库地址".into()); }
            let destination = parent.join(safe_repository_name(url)?);
            if !destination.join(".git").is_dir() {
                command_output("gh", &["repo".into(), "clone".into(), url.into(), destination.to_string_lossy().into_owned()], Some(&parent)).await?;
            }
            (destination, url.to_string(), "github".to_string())
        }
        "create" => {
            let name = safe_repository_name(request.repository_name.as_deref().unwrap_or("douyin-writing-skills"))?;
            let visibility = request.visibility.as_deref().unwrap_or("private");
            if !matches!(visibility, "private" | "public") { return Err("GitHub 可见性无效".into()); }
            let destination = parent.join(&name);
            if destination.exists() { return Err("目标目录已存在，请改用连接现有仓库".into()); }
            command_output("gh", &["repo".into(), "create".into(), name, format!("--{visibility}"), "--clone".into()], Some(&parent)).await?;
            let remote = command_output("git", &["remote".into(), "get-url".into(), "origin".into()], Some(&destination)).await?;
            (destination, remote, "github".to_string())
        }
        "local" => {
            let destination = parent.join(safe_repository_name(request.repository_name.as_deref().unwrap_or("douyin-writing-skills"))?);
            fs::create_dir_all(&destination).map_err(|error| error.to_string())?;
            if !destination.join(".git").is_dir() {
                command_output("git", &["init".into(), "-b".into(), "main".into()], Some(&destination)).await?;
                command_output("git", &["config".into(), "user.name".into(), "Douyin Writing Skills".into()], Some(&destination)).await?;
                command_output("git", &["config".into(), "user.email".into(), "douyin-writing-skills@local".into()], Some(&destination)).await?;
            }
            (destination, String::new(), "local".to_string())
        }
        _ => return Err("不支持的项目配置方式".into()),
    };
    let branch = command_output("git", &["branch".into(), "--show-current".into()], Some(&repository)).await?.trim().to_string();
    let branch = if branch.is_empty() { "main".to_string() } else { branch };
    initialize_loader(&repository, &sync_mode, &remote_url, &branch).await?;
    let mut settings = load_settings(db)?;
    settings.skill_sync_mode = sync_mode;
    settings.skill_repository_path = repository.to_string_lossy().into_owned();
    settings.skill_remote_url = remote_url.clone();
    settings.skill_remote = "origin".into();
    settings.skill_branch = branch;
    save_settings(db, &settings)?;
    Ok(json!({"message": "Skill 发布仓库已配置", "repositoryPath": settings.skill_repository_path, "remoteUrl": remote_url, "settings": settings}))
}

fn safe_version(value: &str) -> bool {
    !value.is_empty() && value.len() <= 128 && value.chars().enumerate().all(|(index, ch)| ch.is_ascii_alphanumeric() || (index > 0 && "._-".contains(ch)))
}

fn valid_runtime_path(path: &str) -> bool {
    !path.is_empty() && !path.starts_with('/') && !path.contains('\\') && !path.split('/').any(|part| part == "." || part == "..")
        && (path == "SKILL.md" || path == "references/skills.json" || path == "references/research-playbook.md" || (path.starts_with("references/skills/") && path.ends_with(".md")))
}

fn contains_secret_like_text(value: &str) -> bool {
    let lower = value.to_ascii_lowercase();
    ["sk-", "ghp_", "github_pat_", "authorization: bearer ", "bearer ", "-----begin private key-----", "akia"]
        .iter()
        .any(|marker| lower.contains(marker))
}

fn validate_candidate_public_fields(candidate: &Value) -> Result<(), String> {
    let macos_user_path = format!("/{}/", "Users");
    let windows_user_path = format!("\\{}\\", "Users");
    for field in ["name", "purpose", "hook", "progression", "ending", "riskBoundary"] {
        let value = candidate.get(field).and_then(Value::as_str).unwrap_or("");
        if contains_secret_like_text(value) { return Err(format!("候选 {field} 包含疑似凭据，不能发布")); }
        if ["http://", "https://", "file://", "/private/", "/var/"].iter().any(|marker| value.contains(marker)) || value.contains(&macos_user_path) || value.contains(&windows_user_path) {
            return Err(format!("候选 {field} 包含来源 URL 或本机路径，不能发布"));
        }
    }
    Ok(())
}

fn default_runtime() -> BTreeMap<String, String> {
    BTreeMap::from([
        ("SKILL.md".into(), "# Douyin Writing Skills Runtime\n\nRead `references/skills.json` before selecting a writing method.\n".into()),
        ("references/skills.json".into(), "{\n  \"name\": \"douyin-writing-skills\",\n  \"version\": \"unpublished\",\n  \"skills\": []\n}\n".into()),
        ("references/research-playbook.md".into(), "# Research Playbook\n\nVerify current facts before writing.\n".into()),
    ])
}

fn file_text(path: &Path) -> Result<String, String> {
    if path.is_symlink() { return Err("stable runtime 不允许符号链接".into()); }
    let bytes = fs::read(path).map_err(|error| error.to_string())?;
    String::from_utf8(bytes).map_err(|_| "stable runtime 文件不是 UTF-8".to_string())
}

pub fn load_stable_repository_snapshot(repository: &Path, configured: bool, remote_url: &str, branch: &str) -> Result<Value, String> {
    if !repository.join(".git").is_dir() { return Err("配置的 Skill 发布项目不是 Git 仓库".into()); }
    let manifest_path = repository.join("published/stable/manifest.json");
    if !manifest_path.exists() {
        return Ok(json!({"configured": configured, "verified": true, "hasStable": false, "version": null, "updatedAt": null, "packagePath": null, "manifestPath": null, "repositoryPath": repository, "remoteUrl": remote_url, "branch": branch, "skills": [], "runtimeFiles": default_runtime(), "error": null}));
    }
    let manifest: Value = serde_json::from_str(&file_text(&manifest_path)?).map_err(|_| "stable manifest 不是有效 JSON".to_string())?;
    if manifest.get("schema_version").and_then(Value::as_i64) != Some(1) || manifest.get("skill_name").and_then(Value::as_str) != Some("douyin-writing-skills") || manifest.get("channel").and_then(Value::as_str) != Some("stable") {
        return Err("stable manifest schema 或通道无效".into());
    }
    let version = manifest.get("version").and_then(Value::as_str).ok_or_else(|| "stable manifest 缺少版本号".to_string())?;
    if !safe_version(version) || manifest.get("package_path").and_then(Value::as_str) != Some(&format!("published/packages/{version}")) || manifest.get("entrypoint").and_then(Value::as_str) != Some("runtime/SKILL.md") { return Err("stable manifest 路径无效".into()); }
    let package = repository.join("published/packages").join(version);
    let files = manifest.get("files").and_then(Value::as_array).ok_or_else(|| "stable manifest 缺少文件列表".to_string())?;
    let mut runtime = BTreeMap::new();
    let mut seen = BTreeMap::new();
    for item in files {
        let path = item.get("path").and_then(Value::as_str).ok_or_else(|| "stable manifest 文件路径无效".to_string())?;
        let relative = path.strip_prefix("runtime/").ok_or_else(|| "stable manifest 文件必须位于 runtime".to_string())?;
        if !valid_runtime_path(relative) || seen.insert(path, true).is_some() { return Err("stable manifest 包含不安全或重复路径".into()); }
        let file = package.join(path);
        let bytes = fs::read(&file).map_err(|_| format!("stable runtime 缺少文件：{path}"))?;
        if file.is_symlink() || item.get("size").and_then(Value::as_u64) != Some(bytes.len() as u64) || item.get("sha256").and_then(Value::as_str) != Some(&format!("{:x}", Sha256::digest(&bytes))) { return Err(format!("stable runtime 校验失败：{path}")); }
        runtime.insert(relative.to_string(), String::from_utf8(bytes).map_err(|_| format!("stable runtime 不是 UTF-8：{path}"))?);
    }
    if !runtime.contains_key("SKILL.md") || !runtime.contains_key("references/skills.json") { return Err("stable runtime 缺少入口文件".into()); }
    let skills_json: Value = serde_json::from_str(runtime.get("references/skills.json").unwrap()).map_err(|_| "stable skills.json 无效".to_string())?;
    let skills = skills_json.get("skills").and_then(Value::as_array).ok_or_else(|| "stable skills.json 缺少 skills".to_string())?;
    Ok(json!({"configured": configured, "verified": true, "hasStable": true, "version": version, "updatedAt": manifest.get("updated_at"), "packagePath": manifest.get("package_path"), "manifestPath": manifest_path, "repositoryPath": repository, "remoteUrl": remote_url, "branch": branch, "skills": skills, "runtimeFiles": runtime, "error": null}))
}

pub fn snapshot_from_settings(db: &DesktopDb) -> Result<Value, String> {
    let settings = load_settings(db)?;
    if settings.skill_repository_path.trim().is_empty() { return Ok(json!({"configured": false, "verified": false, "hasStable": false, "skills": [], "runtimeFiles": {}, "error": "尚未配置 Skill 发布仓库"})); }
    load_stable_repository_snapshot(Path::new(&settings.skill_repository_path), true, &settings.skill_remote_url, &settings.skill_branch)
}

fn reference_markdown(candidate: &Value) -> String {
    format!("# {}\n\n## 解决什么问题\n\n{}\n\n## 开头\n\n{}\n\n## 推进\n\n{}\n\n## 收束\n\n{}\n\n## 风险边界\n\n{}\n\n发布包不包含来源标题、链接、真实稿件、媒体、指纹或用户身份。\n",
        candidate.get("name").and_then(Value::as_str).unwrap_or("未命名结构"), candidate.get("purpose").and_then(Value::as_str).unwrap_or(""), candidate.get("hook").and_then(Value::as_str).unwrap_or(""), candidate.get("progression").and_then(Value::as_str).unwrap_or(""), candidate.get("ending").and_then(Value::as_str).unwrap_or(""), candidate.get("riskBoundary").and_then(Value::as_str).unwrap_or(""))
}

fn build_runtime(snapshot: &Value, candidate: &Value, version: &str) -> Result<(Map<String, Value>, usize), String> {
    validate_candidate_public_fields(candidate)?;
    let mut files: Map<String, Value> = snapshot.get("runtimeFiles").and_then(Value::as_object).cloned().unwrap_or_default();
    if files.is_empty() { files = default_runtime().into_iter().map(|(key, value)| (key, Value::String(value))).collect(); }
    let raw = files.get("references/skills.json").and_then(Value::as_str).ok_or_else(|| "stable runtime 缺少 skills.json".to_string())?;
    let mut index: Value = serde_json::from_str(raw).map_err(|_| "stable skills.json 无法解析".to_string())?;
    let candidate_id = candidate.get("id").and_then(Value::as_str).ok_or_else(|| "候选 ID 缺失".to_string())?;
    let reference = format!("references/skills/{}.md", candidate_id.chars().map(|ch| if ch.is_ascii_alphanumeric() || "._-".contains(ch) { ch } else { '-' }).collect::<String>());
    let next = json!({"id": candidate_id, "name": candidate.get("name").and_then(Value::as_str).unwrap_or("未命名结构"), "account_type": "团队复用写作结构", "quality_score": candidate.pointer("/modelEvaluation/score").and_then(Value::as_i64).unwrap_or(0), "source_count": candidate.get("sourceCount").and_then(Value::as_i64).unwrap_or(0), "created_at": candidate.get("updatedAt").and_then(Value::as_str).unwrap_or(""), "hotspot_types": ["结构沉淀", "单源可复核", "人工最终确认"], "solves_problems": [candidate.get("purpose").and_then(Value::as_str).unwrap_or("")], "match_signals": [candidate.get("hook").and_then(Value::as_str).unwrap_or(""), candidate.get("progression").and_then(Value::as_str).unwrap_or("")], "applicable_scenes": [candidate.get("purpose").and_then(Value::as_str).unwrap_or("")], "research_needs": ["使用前核验当前事实、时间线、公开来源和平台语境。"], "choose_when": candidate.get("purpose").and_then(Value::as_str).unwrap_or(""), "writing_method": format!("开头：{}\n推进：{}\n收束：{}", candidate.get("hook").and_then(Value::as_str).unwrap_or(""), candidate.get("progression").and_then(Value::as_str).unwrap_or(""), candidate.get("ending").and_then(Value::as_str).unwrap_or("")), "risk_boundary": candidate.get("riskBoundary").and_then(Value::as_str).unwrap_or(""), "reference": reference, "reference_file": reference});
    let skill_count = {
        let skills = index.get_mut("skills").and_then(Value::as_array_mut).ok_or_else(|| "stable skills.json 缺少 skills".to_string())?;
        skills.retain(|skill| skill.get("id").and_then(Value::as_str) != Some(candidate_id));
        skills.push(next);
        skills.len()
    };
    index["version"] = Value::String(version.to_string());
    files.insert("references/skills.json".into(), Value::String(format!("{}\n", serde_json::to_string_pretty(&index).map_err(|error| error.to_string())?)));
    files.insert(reference, Value::String(reference_markdown(candidate)));
    Ok((files, skill_count))
}

fn write_runtime_package(repository: &Path, version: &str, files: &Map<String, Value>) -> Result<(PathBuf, Vec<Value>), String> {
    if !safe_version(version) { return Err("发布版本号不安全".into()); }
    let packages = repository.join("published/packages");
    fs::create_dir_all(&packages).map_err(|error| error.to_string())?;
    let destination = packages.join(version);
    let temporary = packages.join(format!(".workbench-{version}-{}", Uuid::new_v4()));
    let mut accepted = BTreeMap::new();
    for (path, content) in files {
        if !valid_runtime_path(path) { return Err(format!("发布包含未授权运行时路径：{path}")); }
        let content = content.as_str().ok_or_else(|| format!("发布文件 {path} 不是文本"))?;
        if contains_secret_like_text(content) { return Err(format!("发布文件 {path} 包含疑似凭据")); }
        accepted.insert(path.clone(), content.to_string());
    }
    if !accepted.contains_key("SKILL.md") || !accepted.contains_key("references/skills.json") { return Err("发布包缺少 SKILL.md 或 references/skills.json".into()); }
    let mut manifest_files = Vec::new();
    for (path, content) in accepted {
        let target = temporary.join("runtime").join(&path);
        if let Some(parent) = target.parent() { fs::create_dir_all(parent).map_err(|error| error.to_string())?; }
        fs::write(&target, content.as_bytes()).map_err(|error| error.to_string())?;
        manifest_files.push(json!({"path": format!("runtime/{path}"), "sha256": format!("{:x}", Sha256::digest(content.as_bytes())), "size": content.as_bytes().len()}));
    }
    if destination.exists() {
        if directory_files(&destination)? != directory_files(&temporary)? { fs::remove_dir_all(&temporary).map_err(|error| error.to_string())?; return Err("同版本不可变包已存在且内容不同，请使用新的版本号".into()); }
        fs::remove_dir_all(&temporary).map_err(|error| error.to_string())?;
    } else { fs::rename(&temporary, &destination).map_err(|error| error.to_string())?; }
    Ok((destination, manifest_files))
}

fn directory_files(root: &Path) -> Result<BTreeMap<PathBuf, Vec<u8>>, String> {
    fn visit(root: &Path, current: &Path, output: &mut BTreeMap<PathBuf, Vec<u8>>) -> Result<(), String> {
        for entry in fs::read_dir(current).map_err(|error| error.to_string())? {
            let path = entry.map_err(|error| error.to_string())?.path();
            if path.is_symlink() { return Err("不可变包不允许符号链接".into()); }
            if path.is_dir() { visit(root, &path, output)?; } else if path.is_file() { output.insert(path.strip_prefix(root).map_err(|error| error.to_string())?.to_path_buf(), fs::read(path).map_err(|error| error.to_string())?); }
        }
        Ok(())
    }
    let mut output = BTreeMap::new(); visit(root, root, &mut output)?; Ok(output)
}

fn write_stable_manifest(repository: &Path, version: &str, files: Vec<Value>) -> Result<PathBuf, String> {
    let stable = repository.join("published/stable"); fs::create_dir_all(&stable).map_err(|error| error.to_string())?;
    let path = stable.join("manifest.json");
    let manifest = json!({"schema_version": 1, "skill_name": "douyin-writing-skills", "channel": "stable", "version": version, "updated_at": Utc::now().to_rfc3339(), "package_path": format!("published/packages/{version}"), "entrypoint": "runtime/SKILL.md", "files": files});
    let temporary = stable.join(format!(".manifest-{}.tmp", Uuid::new_v4()));
    fs::write(&temporary, format!("{}\n", serde_json::to_string_pretty(&manifest).map_err(|error| error.to_string())?)).map_err(|error| error.to_string())?;
    fs::rename(&temporary, &path).map_err(|error| error.to_string())?;
    Ok(path)
}

fn release_candidate_is_valid(candidate: &Value) -> Result<(), String> {
    if candidate.get("sourceCount").and_then(Value::as_i64).unwrap_or(0) < 1 { return Err("至少需要 1 条已授权真实稿件".into()); }
    if candidate.pointer("/modelEvaluation/status").and_then(Value::as_str) != Some("passed") || candidate.pointer("/modelEvaluation/score").and_then(Value::as_i64).unwrap_or(0) < 80 { return Err("模型评测未达到 80 分发布门槛".into()); }
    if candidate.pointer("/humanReview/status").and_then(Value::as_str) != Some("approved") { return Err("需要用户最终发布确认".into()); }
    Ok(())
}

fn job_stage(job: &mut Value, stage: &str, status: &str) { job["stage"] = Value::String(stage.into()); job["status"] = Value::String(status.into()); job["updatedAt"] = Value::String(Utc::now().to_rfc3339()); }

fn new_job(candidate_id: &str, repository: &Path, remote_url: &str, remote: &str, branch: &str) -> Value {
    let now = Utc::now().to_rfc3339();
    let suffix = Uuid::new_v4().simple().to_string()[..8].to_string();
    json!({"id": format!("publish-{}", Uuid::new_v4()), "candidateId": candidate_id, "version": format!("wb-{}-{}", Utc::now().format("%Y%m%dT%H%M%S"), suffix), "status": "pending", "stage": "pending", "repositoryPath": repository, "remoteUrl": remote_url, "remote": remote, "branch": branch, "packagePath": null, "manifestPath": null, "commitSha": null, "commitUrl": null, "startedAt": now, "updatedAt": now, "finishedAt": null, "errorCode": null, "errorMessage": null, "remoteVerifiedAt": null})
}

async fn preflight(repository: &Path, sync_mode: &str, remote: &str, branch: &str) -> Result<(), String> {
    if !repository.join(".git").is_dir() { return Err("配置的 Skill 发布项目不是 Git 仓库".into()); }
    loader_files_present(repository)?;
    command_output("git", &["config".into(), "user.name".into()], Some(repository)).await?;
    command_output("git", &["config".into(), "user.email".into()], Some(repository)).await?;
    let dirty = command_output("git", &["status".into(), "--porcelain".into()], Some(repository)).await?;
    if !dirty.is_empty() { return Err("发布仓库存在未知未提交改动，已停止发布以保护工作区".into()); }
    if sync_mode == "github" {
        command_output("git", &["remote".into(), "get-url".into(), remote.into()], Some(repository)).await?;
        command_output("git", &["fetch".into(), "--prune".into(), remote.into()], Some(repository)).await?;
        let upstream = format!("{remote}/{branch}");
        if command_output("git", &["rev-parse".into(), "--verify".into(), upstream.clone()], Some(repository)).await.is_ok() {
            let counts = command_output("git", &["rev-list".into(), "--left-right".into(), "--count".into(), format!("HEAD...{upstream}")], Some(repository)).await?;
            let mut counts = counts.split_whitespace();
            let ahead = counts.next().and_then(|value| value.parse::<usize>().ok()).ok_or_else(|| "无法读取本机与远端分支关系".to_string())?;
            let behind = counts.next().and_then(|value| value.parse::<usize>().ok()).ok_or_else(|| "无法读取本机与远端分支关系".to_string())?;
            match (ahead, behind) {
                (0, 0) | (_, 0) => {}
                (0, _) => {
                    command_output("git", &["merge".into(), "--ff-only".into(), upstream], Some(repository)).await?;
                }
                _ => {
                    let local_subjects = command_output("git", &["log".into(), "--format=%s".into(), format!("{upstream}..HEAD")], Some(repository)).await?;
                    let generated_only = local_subjects.lines().all(|subject| subject.starts_with("publish writing skills ") || subject == "Initialize fixed Skill loader");
                    if !generated_only {
                        return Err("发布仓库与远端分叉，且包含未识别的本地提交。为保护你的提交，未自动改写历史；请先手动同步该仓库后重试。".into());
                    }
                    command_output("git", &["rebase".into(), upstream], Some(repository)).await.map_err(|error| format!("自动同步应用生成的发布提交失败：{error}\n已保留本地提交；请解决冲突后重试。"))?;
                }
            }
        }
    }
    Ok(())
}

async fn verify_public_github_runtime(source: &Value, commit: &str, version: &str, client: &reqwest::Client) -> Result<(), String> {
    let owner = source.get("owner").and_then(Value::as_str).ok_or_else(|| "GitHub 来源缺少 owner".to_string())?;
    let repository = source.get("repository").and_then(Value::as_str).ok_or_else(|| "GitHub 来源缺少 repository".to_string())?;
    let base = format!("https://raw.githubusercontent.com/{owner}/{repository}/{commit}");
    let response = client.get(format!("{base}/published/stable/manifest.json")).send().await.map_err(|error| format!("无法读取 GitHub Raw stable manifest：{error}"))?;
    if !response.status().is_success() { return Err(format!("GitHub Raw stable manifest 返回 HTTP {}", response.status())); }
    let manifest: Value = serde_json::from_slice(&response.bytes().await.map_err(|error| error.to_string())?).map_err(|_| "GitHub Raw stable manifest 不是有效 JSON".to_string())?;
    if manifest.get("version").and_then(Value::as_str) != Some(version) { return Err("GitHub Raw stable manifest 版本与发布任务不一致".into()); }
    if manifest.get("package_path").and_then(Value::as_str) != Some(&format!("published/packages/{version}")) { return Err("GitHub Raw stable manifest package_path 无效".into()); }
    let files = manifest.get("files").and_then(Value::as_array).ok_or_else(|| "GitHub Raw stable manifest 缺少文件列表".to_string())?;
    for file in files {
        let path = file.get("path").and_then(Value::as_str).ok_or_else(|| "GitHub Raw manifest 文件路径无效".to_string())?;
        let bytes = client.get(format!("{base}/published/packages/{version}/{path}")).send().await.map_err(|error| format!("无法读取 GitHub Raw runtime 文件：{error}"))?
            .error_for_status().map_err(|error| format!("GitHub Raw runtime 文件不可用：{error}"))?.bytes().await.map_err(|error| error.to_string())?;
        if file.get("size").and_then(Value::as_u64) != Some(bytes.len() as u64) || file.get("sha256").and_then(Value::as_str) != Some(&format!("{:x}", Sha256::digest(&bytes))) {
            return Err(format!("GitHub Raw runtime 校验失败：{path}"));
        }
    }
    Ok(())
}

async fn github_repository_is_public(source: &Value, client: &reqwest::Client) -> Result<bool, String> {
    let owner = source.get("owner").and_then(Value::as_str).ok_or_else(|| "GitHub 来源缺少 owner".to_string())?;
    let repository = source.get("repository").and_then(Value::as_str).ok_or_else(|| "GitHub 来源缺少 repository".to_string())?;
    let response = client
        .get(format!("https://api.github.com/repos/{owner}/{repository}"))
        .header("User-Agent", "douyin-writing-skills-desktop")
        .send().await.map_err(|error| format!("无法确认 GitHub 仓库可见性：{error}"))?;
    if !response.status().is_success() { return Ok(false); }
    let metadata: Value = response.json().await.map_err(|error| format!("GitHub 仓库元数据无效：{error}"))?;
    Ok(metadata.get("private").and_then(Value::as_bool) == Some(false))
}

async fn verify_clean_clone_and_loader(repository: &Path, remote_url: &str, branch: &str, commit: &str, version: &str) -> Result<(), String> {
    let scratch = std::env::temp_dir().join(format!("douyin-writing-skills-verify-{}", Uuid::new_v4()));
    let cache = scratch.join("cache");
    let source = if remote_url.trim().is_empty() { repository.to_string_lossy().into_owned() } else { remote_url.to_string() };
    let result: Result<(), String> = async {
        command_output("git", &["clone".into(), "--no-checkout".into(), source, scratch.to_string_lossy().into_owned()], None).await?;
        command_output("git", &["checkout".into(), "--detach".into(), commit.into()], Some(&scratch)).await?;
        loader_files_present(&scratch)?;
        let snapshot = load_stable_repository_snapshot(&scratch, true, remote_url, branch)?;
        if snapshot.get("version").and_then(Value::as_str) != Some(version) { return Err("干净 clone 的 stable version 与发布任务不一致".into()); }
        let python = if require_executable("python3").is_ok() { "python3" } else { "python" };
        let output = command_output_with_env(python, &["scripts/load_latest.py".into()], Some(&scratch), &[("DOUYIN_WRITING_CACHE_DIR", cache.to_string_lossy().into_owned())]).await?;
        let loader: Value = serde_json::from_str(&output).map_err(|_| "固定加载器没有返回 JSON".to_string())?;
        if loader.get("status").and_then(Value::as_str) != Some("ok") || loader.get("version").and_then(Value::as_str) != Some(version) {
            return Err("固定加载器未验证本次 stable 版本".into());
        }
        Ok(())
    }.await;
    let _ = fs::remove_dir_all(&scratch);
    result
}

async fn verify_remote_runtime(repository: &Path, job: &Value, commit: &str, settings: &WorkbenchSettings) -> Result<(), String> {
    let remote_url = job.get("remoteUrl").and_then(Value::as_str).unwrap_or("");
    let branch = job.get("branch").and_then(Value::as_str).unwrap_or("main");
    let version = job.get("version").and_then(Value::as_str).ok_or_else(|| "发布任务缺少版本号".to_string())?;
    let (client, _) = api_client(settings, 20)?;
    // Public GitHub receives an independent exact-SHA Raw check. Private repositories
    // use the authenticated clean-clone path below when Raw is unavailable.
    if let Some(source) = github_source(remote_url, branch) {
        if github_repository_is_public(&source, &client).await? {
            verify_public_github_runtime(&source, commit, version, &client).await?;
        }
    }
    verify_clean_clone_and_loader(repository, remote_url, branch, commit, version).await
}

async fn commit_and_push(app: Option<&AppHandle>, repository: &Path, job: &mut Value, sync_mode: &str, settings: &WorkbenchSettings) -> Result<(), String> {
    let version = job["version"].as_str().unwrap_or_default().to_string();
    emit_progress(app, "committing", "正在提交不可变发布包"); job_stage(job, "committing", "running");
    let add = vec!["add".into(), "--".into(), format!("published/packages/{version}"), "published/stable/manifest.json".into()];
    command_output("git", &add, Some(repository)).await?;
    let staged = command_output("git", &["diff".into(), "--cached".into(), "--name-only".into()], Some(repository)).await?;
    if !staged.is_empty() { command_output("git", &["commit".into(), "-m".into(), format!("publish writing skills {version}")], Some(repository)).await?; }
    let commit = command_output("git", &["rev-parse".into(), "HEAD".into()], Some(repository)).await?;
    job["commitSha"] = Value::String(commit.clone());
    if sync_mode != "github" { return Ok(()); }
    let remote = job["remote"].as_str().unwrap_or("origin").to_string(); let branch = job["branch"].as_str().unwrap_or("main").to_string();
    emit_progress(app, "pushing", "正在推送 stable Skill 到 GitHub"); job_stage(job, "pushing", "running");
    command_output("git", &["push".into(), remote.clone(), format!("HEAD:{branch}")], Some(repository)).await?;
    emit_progress(app, "verifying", "正在验证远端 commit 与 stable manifest"); job_stage(job, "verifying", "running");
    let remote_sha = command_output("git", &["ls-remote".into(), remote, format!("refs/heads/{branch}")], Some(repository)).await?.split_whitespace().next().unwrap_or_default().to_string();
    if remote_sha != commit { return Err("Git push 后远端分支未指向本地发布 commit".into()); }
    verify_remote_runtime(repository, job, &commit, settings).await?;
    job["remoteVerifiedAt"] = Value::String(Utc::now().to_rfc3339());
    if let Some(source) = github_source(job["remoteUrl"].as_str().unwrap_or(""), &branch) {
        job["commitUrl"] = Value::String(format!("https://github.com/{}/{}/commit/{commit}", source["owner"].as_str().unwrap_or_default(), source["repository"].as_str().unwrap_or_default()));
    }
    Ok(())
}

pub async fn publish_candidate_with_progress(app: Option<&AppHandle>, db: &DesktopDb, candidate_id: &str) -> Result<Value, String> {
    let candidate = db.load_candidate(candidate_id).map_err(|error| error.to_string())?.ok_or_else(|| "候选不存在或尚未保存到 SQLite".to_string())?;
    release_candidate_is_valid(&candidate)?;
    let settings = load_settings(db)?;
    if settings.skill_repository_path.trim().is_empty() { return Err("请先在系统诊断连接或创建 Skill 发布项目".into()); }
    let repository = PathBuf::from(&settings.skill_repository_path);
    let mut job = match db.latest_publish_job(candidate_id).map_err(|error| error.to_string())? {
        Some(existing) if existing.get("status").and_then(Value::as_str) == Some("failed") => existing,
        Some(existing) if matches!(existing.get("status").and_then(Value::as_str), Some("pending" | "running")) => {
            let stale = existing.get("updatedAt").and_then(Value::as_str)
                .and_then(|value| chrono::DateTime::parse_from_rfc3339(value).ok())
                .is_none_or(|updated| Utc::now().signed_duration_since(updated.with_timezone(&Utc)) > chrono::Duration::minutes(10));
            if !stale { return Err("该 Skill 已有正在运行的发布任务，请等待完成或稍后重试".into()); }
            existing
        }
        Some(existing) if existing.get("status").and_then(Value::as_str) == Some("succeeded") && candidate.pointer("/release/version").and_then(Value::as_str) == existing.get("version").and_then(Value::as_str) => return Ok(existing),
        _ => new_job(candidate_id, &repository, &settings.skill_remote_url, &settings.skill_remote, &settings.skill_branch),
    };
    db.save_publish_job(&job).map_err(|error| error.to_string())?;
    let result: Result<Value, String> = async {
        emit_progress(app, "fetching", "正在安全同步目标 Skill 仓库"); job_stage(&mut job, "fetching", "running"); db.save_publish_job(&job).map_err(|error| error.to_string())?;
        preflight(&repository, &settings.skill_sync_mode, &settings.skill_remote, &settings.skill_branch).await?;
        emit_progress(app, "loading_base", "正在读取并校验当前 stable runtime"); job_stage(&mut job, "loading_base", "running"); db.save_publish_job(&job).map_err(|error| error.to_string())?;
        let snapshot = load_stable_repository_snapshot(&repository, true, &settings.skill_remote_url, &settings.skill_branch)?;
        let version = job["version"].as_str().ok_or_else(|| "发布任务缺少版本号".to_string())?.to_string();
        emit_progress(app, "building", "正在合并已有 stable Skill 并生成不可变版本"); job_stage(&mut job, "building", "running"); db.save_publish_job(&job).map_err(|error| error.to_string())?;
        let (files, active_count) = build_runtime(&snapshot, &candidate, &version)?;
        let (package, manifest_files) = write_runtime_package(&repository, &version, &files)?;
        let manifest = write_stable_manifest(&repository, &version, manifest_files)?;
        job["packagePath"] = Value::String(package.to_string_lossy().into_owned()); job["manifestPath"] = Value::String(manifest.to_string_lossy().into_owned());
        emit_progress(app, "validating", "正在校验完整 stable runtime"); job_stage(&mut job, "validating", "running"); db.save_publish_job(&job).map_err(|error| error.to_string())?;
        let checked = load_stable_repository_snapshot(&repository, true, &settings.skill_remote_url, &settings.skill_branch)?;
        if checked.get("skills").and_then(Value::as_array).map(|skills| skills.len()) != Some(active_count) { return Err("发布后 Skill 数量校验失败".into()); }
        commit_and_push(app, &repository, &mut job, &settings.skill_sync_mode, &settings).await?;
        let manifest_path = job.get("manifestPath").and_then(Value::as_str).ok_or_else(|| "发布任务缺少 stable manifest 路径".to_string())?;
        db.mark_candidate_released(candidate_id, &version, manifest_path).map_err(|error| error.to_string())?;
        job_stage(&mut job, "succeeded", "succeeded"); job["finishedAt"] = Value::String(Utc::now().to_rfc3339()); db.save_publish_job(&job).map_err(|error| error.to_string())?;
        emit_progress(app, "succeeded", "stable Skill 已完成远端验证"); Ok(job.clone())
    }.await;
    if let Err(error) = result {
        let failed_stage = job.get("stage").and_then(Value::as_str).unwrap_or("failed").to_string();
        job_stage(&mut job, &failed_stage, "failed"); job["errorCode"] = Value::String("PUBLISH_FAILED".into()); job["errorMessage"] = Value::String(error.clone()); job["finishedAt"] = Value::String(Utc::now().to_rfc3339()); let _ = db.save_publish_job(&job); emit_progress(app, "failed", "stable Skill 发布失败"); return Err(error);
    }
    Ok(job)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::db::DesktopDb;
    use serde_json::json;

    fn candidate(id: &str) -> Value { json!({"id":id,"name":"结构","purpose":"说明问题","hook":"反差开头","progression":"递进说明","ending":"认知收束","riskBoundary":"核验事实","sourceCount":1,"status":"release_ready","sources":[],"modelEvaluation":{"status":"passed","score":90,"evaluator":"test","summary":"ok","evaluatedAt":"2026-08-01T00:00:00Z"},"humanReview":{"status":"approved","reviewer":"user","notes":"ok","reviewedAt":"2026-08-01T00:01:00Z"},"release":null,"sourceLabel":"private","updatedAt":"2026-08-01T00:01:00Z"}) }

    #[test]
    fn runtime_path_rejects_traversal() { assert!(valid_runtime_path("SKILL.md")); assert!(!valid_runtime_path("../SKILL.md")); assert!(!valid_runtime_path("scripts/publish.py")); }

    #[test]
    fn candidate_runtime_rejects_source_urls_paths_and_credentials() {
        let snapshot = json!({});
        let local_path = format!("/{}/example/private-note", "Users");
        for (field, value) in [("hook", "https://example.test/source".to_string()), ("progression", local_path), ("ending", "Bearer private-token-value".to_string())] {
            let mut value_candidate = candidate("privacy-test");
            value_candidate[field] = Value::String(value);
            assert!(build_runtime(&snapshot, &value_candidate, "test-v1").is_err(), "{field} should be rejected");
        }
    }

    #[test]
    fn runtime_package_rejects_secret_like_content() {
        let temp = tempfile::tempdir().unwrap();
        let mut files = default_runtime();
        files.insert("references/research-playbook.md".into(), "Bearer private-token-value".into());
        let files = files.into_iter().map(|(path, content)| (path, Value::String(content))).collect();
        assert!(write_runtime_package(temp.path(), "test-v1", &files).is_err());
    }

    #[test]
    fn github_loader_source_uses_configured_https_or_ssh_remote() {
        assert_eq!(github_source("https://github.com/acme/custom-skills.git", "release").unwrap()["repository"], "custom-skills");
        assert_eq!(github_source("git@github.com:acme/custom-skills.git", "release").unwrap()["branch"], "release");
        assert!(github_source("https://example.com/acme/custom-skills.git", "main").is_none());
    }

    #[tokio::test]
    async fn incremental_runtime_keeps_existing_skills_and_updates_ids() {
        let temp = tempfile::tempdir().unwrap(); let repo = temp.path().join("skills"); fs::create_dir_all(&repo).unwrap();
        command_output("git", &["init".into(), "-b".into(), "main".into()], Some(&repo)).await.unwrap(); command_output("git", &["config".into(), "user.name".into(), "test".into()], Some(&repo)).await.unwrap(); command_output("git", &["config".into(), "user.email".into(), "test@example.com".into()], Some(&repo)).await.unwrap(); initialize_loader(&repo, "local", "", "main").await.unwrap();
        let db = DesktopDb::memory().unwrap();
        let state = json!({"session":{"stage":"awaiting_source","source":null,"transcript":"","transcriptQuality":"unavailable","draft":null,"events":[]},"candidates":[candidate("A"), candidate("B")]}); db.save_skill_workbench_state(&state).unwrap();
        let mut settings = crate::settings::load_settings(&db).unwrap(); settings.skill_sync_mode="local".into(); settings.skill_repository_path=repo.to_string_lossy().into_owned(); crate::settings::save_settings(&db,&settings).unwrap();
        let first = publish_candidate_with_progress(None, &db, "A").await.unwrap(); let version_a=first["version"].as_str().unwrap().to_string();
        let _second = publish_candidate_with_progress(None, &db, "B").await.unwrap(); let snapshot=load_stable_repository_snapshot(&repo,true,"","main").unwrap(); assert_eq!(snapshot["skills"].as_array().unwrap().len(),2); assert!(repo.join(format!("published/packages/{version_a}/runtime/references/skills/A.md")).is_file());
        let updated = candidate("A"); let state = json!({"session":{"stage":"awaiting_source","source":null,"transcript":"","transcriptQuality":"unavailable","draft":null,"events":[]},"candidates":[updated,candidate("B")]}); db.save_skill_workbench_state(&state).unwrap();
        let third = publish_candidate_with_progress(None, &db, "A").await.unwrap(); assert_ne!(third["version"], first["version"]); assert_eq!(load_stable_repository_snapshot(&repo,true,"","main").unwrap()["skills"].as_array().unwrap().len(),2);
    }

    #[tokio::test]
    async fn preflight_rebases_generated_publish_commit_after_remote_advances() {
        let temp = tempfile::tempdir().unwrap();
        let repo = temp.path().join("skills");
        let remote = temp.path().join("remote.git");
        command_output("git", &["init".into(), "-b".into(), "main".into(), repo.to_string_lossy().into_owned()], None).await.unwrap();
        command_output("git", &["config".into(), "user.name".into(), "test".into()], Some(&repo)).await.unwrap();
        command_output("git", &["config".into(), "user.email".into(), "test@example.com".into()], Some(&repo)).await.unwrap();
        fs::write(repo.join("base.txt"), "base\n").unwrap();
        command_output("git", &["add".into(), "base.txt".into()], Some(&repo)).await.unwrap();
        command_output("git", &["commit".into(), "-m".into(), "base".into()], Some(&repo)).await.unwrap();
        command_output("git", &["init".into(), "--bare".into(), remote.to_string_lossy().into_owned()], None).await.unwrap();
        command_output("git", &["remote".into(), "add".into(), "origin".into(), remote.to_string_lossy().into_owned()], Some(&repo)).await.unwrap();
        command_output("git", &["push".into(), "-u".into(), "origin".into(), "main".into()], Some(&repo)).await.unwrap();
        seed_loader(&repo, "local", "", "main").unwrap();
        command_output("git", &["add".into(), "SKILL.md".into(), "skill-source.json".into(), "scripts".into()], Some(&repo)).await.unwrap();
        command_output("git", &["commit".into(), "-m".into(), "Initialize fixed Skill loader".into()], Some(&repo)).await.unwrap();

        let writer = temp.path().join("writer");
        command_output("git", &["clone".into(), remote.to_string_lossy().into_owned(), writer.to_string_lossy().into_owned()], None).await.unwrap();
        command_output("git", &["config".into(), "user.name".into(), "writer".into()], Some(&writer)).await.unwrap();
        command_output("git", &["config".into(), "user.email".into(), "writer@example.com".into()], Some(&writer)).await.unwrap();
        fs::write(writer.join("remote.txt"), "remote\n").unwrap();
        command_output("git", &["add".into(), "remote.txt".into()], Some(&writer)).await.unwrap();
        command_output("git", &["commit".into(), "-m".into(), "remote update".into()], Some(&writer)).await.unwrap();
        command_output("git", &["push".into(), "origin".into(), "main".into()], Some(&writer)).await.unwrap();

        fs::write(repo.join("published.txt"), "publish\n").unwrap();
        command_output("git", &["add".into(), "published.txt".into()], Some(&repo)).await.unwrap();
        command_output("git", &["commit".into(), "-m".into(), "publish writing skills wb-test".into()], Some(&repo)).await.unwrap();
        preflight(&repo, "github", "origin", "main").await.unwrap();

        assert!(repo.join("remote.txt").is_file());
        assert!(repo.join("published.txt").is_file());
        assert_eq!(command_output("git", &["log".into(), "-1".into(), "--format=%s".into()], Some(&repo)).await.unwrap(), "publish writing skills wb-test");
    }

    #[tokio::test]
    async fn loader_is_complete_and_verifies_a_local_stable_runtime() {
        let temp = tempfile::tempdir().unwrap(); let repo = temp.path().join("skills"); fs::create_dir_all(&repo).unwrap();
        command_output("git", &["init".into(), "-b".into(), "main".into()], Some(&repo)).await.unwrap(); command_output("git", &["config".into(), "user.name".into(), "test".into()], Some(&repo)).await.unwrap(); command_output("git", &["config".into(), "user.email".into(), "test@example.com".into()], Some(&repo)).await.unwrap(); initialize_loader(&repo, "local", "", "main").await.unwrap();
        assert!(repo.join("scripts/runtime_package.py").is_file());
        let db = DesktopDb::memory().unwrap();
        let state = json!({"session":{"stage":"awaiting_source","source":null,"transcript":"","transcriptQuality":"unavailable","draft":null,"events":[]},"candidates":[candidate("A")]}); db.save_skill_workbench_state(&state).unwrap();
        let mut settings = crate::settings::load_settings(&db).unwrap(); settings.skill_sync_mode="local".into(); settings.skill_repository_path=repo.to_string_lossy().into_owned(); crate::settings::save_settings(&db,&settings).unwrap();
        let published = publish_candidate_with_progress(None, &db, "A").await.unwrap();
        let cache = temp.path().join("isolated-cache");
        let python = if require_executable("python3").is_ok() { "python3" } else { "python" };
        let output = command_output_with_env(python, &["scripts/load_latest.py".into()], Some(&repo), &[("DOUYIN_WRITING_CACHE_DIR", cache.to_string_lossy().into_owned())]).await.unwrap();
        let loader: Value = serde_json::from_str(&output).unwrap();
        assert_eq!(loader["status"], "ok"); assert_eq!(loader["version"], published["version"]);
    }

    #[tokio::test]
    async fn github_mode_verifies_push_against_a_clean_bare_remote_clone() {
        let temp = tempfile::tempdir().unwrap();
        let bare = temp.path().join("remote.git"); let repo = temp.path().join("skills"); fs::create_dir_all(&repo).unwrap();
        command_output("git", &["init".into(), "-b".into(), "main".into()], Some(&repo)).await.unwrap(); command_output("git", &["config".into(), "user.name".into(), "test".into()], Some(&repo)).await.unwrap(); command_output("git", &["config".into(), "user.email".into(), "test@example.com".into()], Some(&repo)).await.unwrap(); initialize_loader(&repo, "local", "", "main").await.unwrap();
        command_output("git", &["init".into(), "--bare".into(), bare.to_string_lossy().into_owned()], None).await.unwrap();
        command_output("git", &["remote".into(), "add".into(), "origin".into(), bare.to_string_lossy().into_owned()], Some(&repo)).await.unwrap(); command_output("git", &["push".into(), "-u".into(), "origin".into(), "main".into()], Some(&repo)).await.unwrap();
        let db = DesktopDb::memory().unwrap();
        let state = json!({"session":{"stage":"awaiting_source","source":null,"transcript":"","transcriptQuality":"unavailable","draft":null,"events":[]},"candidates":[candidate("A")]}); db.save_skill_workbench_state(&state).unwrap();
        let mut settings = crate::settings::load_settings(&db).unwrap(); settings.skill_sync_mode="github".into(); settings.skill_repository_path=repo.to_string_lossy().into_owned(); settings.skill_remote="origin".into(); settings.skill_remote_url=bare.to_string_lossy().into_owned(); settings.skill_branch="main".into(); crate::settings::save_settings(&db,&settings).unwrap();
        let job = publish_candidate_with_progress(None, &db, "A").await.unwrap();
        let remote = command_output("git", &["--git-dir".into(), bare.to_string_lossy().into_owned(), "rev-parse".into(), "main".into()], None).await.unwrap();
        assert_eq!(job["commitSha"].as_str(), Some(remote.as_str())); assert!(job["remoteVerifiedAt"].is_string());
    }

    #[tokio::test]
    async fn invalid_stable_hash_is_rejected_before_publish() {
        let temp = tempfile::tempdir().unwrap(); let repo = temp.path().join("skills"); fs::create_dir_all(&repo).unwrap();
        command_output("git", &["init".into(), "-b".into(), "main".into()], Some(&repo)).await.unwrap(); command_output("git", &["config".into(), "user.name".into(), "test".into()], Some(&repo)).await.unwrap(); command_output("git", &["config".into(), "user.email".into(), "test@example.com".into()], Some(&repo)).await.unwrap(); initialize_loader(&repo, "local", "", "main").await.unwrap();
        let files = default_runtime().into_iter().map(|(path, content)| (path, Value::String(content))).collect();
        let (_, manifest_files) = write_runtime_package(&repo, "test-v1", &files).unwrap();
        let manifest = write_stable_manifest(&repo, "test-v1", manifest_files).unwrap();
        let mut broken: Value = serde_json::from_str(&fs::read_to_string(&manifest).unwrap()).unwrap(); broken["files"][0]["sha256"] = Value::String("0".repeat(64)); fs::write(&manifest, serde_json::to_string(&broken).unwrap()).unwrap();
        assert!(load_stable_repository_snapshot(&repo, true, "", "main").is_err());
    }
}
