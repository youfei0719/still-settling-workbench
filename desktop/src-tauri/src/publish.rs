use crate::db::DesktopDb;
use crate::executable::require_executable;
use crate::settings::{load_settings, save_settings};
use chrono::Utc;
use serde::Deserialize;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use tauri::{AppHandle, Emitter};
use tokio::process::Command;
use uuid::Uuid;

const ROOT_SKILL: &str = include_str!("../resources/skill-loader/SKILL.md");
const LOAD_LATEST: &str = include_str!("../resources/skill-loader/scripts/load_latest.py");
const INSTALL_SH: &str = include_str!("../resources/skill-loader/scripts/install.sh");
const INSTALL_PS1: &str = include_str!("../resources/skill-loader/scripts/install.ps1");

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

async fn command_output(
    command: &str,
    args: &[String],
    current_dir: Option<&Path>,
) -> Result<String, String> {
    let executable = require_executable(command)?;
    let mut process = Command::new(&executable);
    process.args(args);
    if let Some(directory) = current_dir {
        process.current_dir(directory);
    }
    let output = process
        .output()
        .await
        .map_err(|error| format!("无法启动 {}：{error}", executable.display()))?;
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
    if name.is_empty()
        || name.len() > 100
        || !name
            .chars()
            .all(|character| character.is_ascii_alphanumeric() || ".-_".contains(character))
    {
        return Err("项目名称只能包含字母、数字、点、下划线和连字符".into());
    }
    Ok(name.to_string())
}

fn setup_parent(value: Option<String>) -> Result<PathBuf, String> {
    let parent = value
        .filter(|value| !value.trim().is_empty())
        .map(PathBuf::from)
        .or_else(|| dirs::document_dir().map(|path| path.join("DouyinWritingSkills")))
        .ok_or_else(|| "无法确定本地项目目录".to_string())?;
    fs::create_dir_all(&parent).map_err(|error| format!("无法创建项目目录：{error}"))?;
    Ok(parent)
}

fn write_if_missing(path: &Path, content: &str) -> Result<(), String> {
    if path.exists() {
        return Ok(());
    }
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    fs::write(path, content).map_err(|error| error.to_string())
}

fn seed_loader(repository: &Path) -> Result<(), String> {
    write_if_missing(&repository.join("SKILL.md"), ROOT_SKILL)?;
    write_if_missing(&repository.join("scripts/load_latest.py"), LOAD_LATEST)?;
    write_if_missing(&repository.join("scripts/install.sh"), INSTALL_SH)?;
    write_if_missing(&repository.join("scripts/install.ps1"), INSTALL_PS1)?;
    Ok(())
}

pub async fn setup_repository(
    db: &DesktopDb,
    request: RepositorySetupRequest,
) -> Result<Value, String> {
    let parent = setup_parent(request.local_parent_path)?;
    let (repository, remote_url, sync_mode) = match request.mode.as_str() {
        "connect" => {
            let url = request
                .repository_url
                .as_deref()
                .ok_or_else(|| "请填写 GitHub 仓库地址".to_string())?;
            if !url.starts_with("https://github.com/") && !url.starts_with("git@github.com:") {
                return Err("只支持连接 GitHub HTTPS 或 SSH 仓库地址".into());
            }
            let name = safe_repository_name(url)?;
            let destination = parent.join(name);
            if destination.join(".git").is_dir() {
                (destination, url.to_string(), "github".to_string())
            } else {
                let args = vec![
                    "repo".into(),
                    "clone".into(),
                    url.into(),
                    destination.to_string_lossy().into_owned(),
                ];
                command_output("gh", &args, Some(&parent)).await?;
                (destination, url.to_string(), "github".to_string())
            }
        }
        "create" => {
            let name = safe_repository_name(
                request
                    .repository_name
                    .as_deref()
                    .unwrap_or("douyin-writing-skills"),
            )?;
            let visibility = request.visibility.as_deref().unwrap_or("private");
            if !matches!(visibility, "private" | "public") {
                return Err("GitHub 可见性无效".into());
            }
            let destination = parent.join(&name);
            if destination.exists() {
                return Err("目标目录已存在，请改用连接现有仓库".into());
            }
            let args = vec![
                "repo".into(),
                "create".into(),
                name.clone(),
                format!("--{visibility}"),
                "--clone".into(),
            ];
            command_output("gh", &args, Some(&parent)).await?;
            let remote = command_output(
                "git",
                &["remote".into(), "get-url".into(), "origin".into()],
                Some(&destination),
            )
            .await?;
            (destination, remote, "github".to_string())
        }
        "local" => {
            let name = safe_repository_name(
                request
                    .repository_name
                    .as_deref()
                    .unwrap_or("douyin-writing-skills"),
            )?;
            let destination = parent.join(name);
            fs::create_dir_all(&destination).map_err(|error| error.to_string())?;
            if !destination.join(".git").is_dir() {
                command_output(
                    "git",
                    &["init".into(), "-b".into(), "main".into()],
                    Some(&destination),
                )
                .await?;
                command_output(
                    "git",
                    &[
                        "config".into(),
                        "user.name".into(),
                        "Douyin Writing Skills".into(),
                    ],
                    Some(&destination),
                )
                .await?;
                command_output(
                    "git",
                    &[
                        "config".into(),
                        "user.email".into(),
                        "douyin-writing-skills@local".into(),
                    ],
                    Some(&destination),
                )
                .await?;
            }
            (destination, String::new(), "local".to_string())
        }
        _ => return Err("不支持的项目配置方式".into()),
    };
    seed_loader(&repository)?;
    let mut settings = load_settings(db)?;
    settings.skill_sync_mode = sync_mode;
    settings.skill_repository_path = repository.to_string_lossy().into_owned();
    settings.skill_remote_url = remote_url.clone();
    settings.skill_remote = "origin".into();
    settings.skill_branch = "main".into();
    save_settings(db, &settings)?;
    Ok(json!({
        "message": if settings.skill_sync_mode == "github" { "GitHub Skill 项目已连接" } else { "本地 Skill 项目已创建" },
        "repositoryPath": settings.skill_repository_path,
        "remoteUrl": remote_url,
        "settings": settings
    }))
}

fn valid_runtime_path(path: &str) -> bool {
    !path.is_empty()
        && !path.starts_with('/')
        && !path.contains('\\')
        && !path.split('/').any(|part| part == "." || part == "..")
        && (path == "SKILL.md"
            || path == "references/skills.json"
            || path == "references/research-playbook.md"
            || (path.starts_with("references/skills/") && path.ends_with(".md")))
}

fn write_runtime_package(
    repository: &Path,
    version: &str,
    files: &serde_json::Map<String, Value>,
) -> Result<(PathBuf, Vec<Value>), String> {
    let packages = repository.join("published/packages");
    fs::create_dir_all(&packages).map_err(|error| error.to_string())?;
    let destination = packages.join(version);
    let temporary = packages.join(format!(".workbench-{version}-{}", Uuid::new_v4()));
    let runtime = temporary.join("runtime");
    fs::create_dir_all(&runtime).map_err(|error| error.to_string())?;
    let mut accepted = BTreeMap::new();
    for (path, content) in files {
        if !valid_runtime_path(path) {
            continue;
        }
        let content = content
            .as_str()
            .ok_or_else(|| format!("发布文件 {path} 不是文本"))?;
        accepted.insert(path.clone(), content.to_string());
    }
    if !accepted.contains_key("SKILL.md") || !accepted.contains_key("references/skills.json") {
        return Err("发布包缺少 SKILL.md 或 references/skills.json".into());
    }
    let mut manifest_files = Vec::new();
    for (path, content) in accepted {
        let relative = format!("runtime/{path}");
        let target = temporary.join(&relative);
        if let Some(parent) = target.parent() {
            fs::create_dir_all(parent).map_err(|error| error.to_string())?;
        }
        fs::write(&target, content.as_bytes()).map_err(|error| error.to_string())?;
        let digest = format!("{:x}", Sha256::digest(content.as_bytes()));
        manifest_files.push(json!({"path": relative, "sha256": digest, "size": content.len()}));
    }
    if destination.exists() {
        if directory_files(&destination)? != directory_files(&temporary)? {
            fs::remove_dir_all(&temporary).map_err(|error| error.to_string())?;
            return Err("同版本不可变包已存在且内容不同，请使用新的版本号".into());
        }
        fs::remove_dir_all(&temporary).map_err(|error| error.to_string())?;
        return Ok((destination, manifest_files));
    }
    fs::rename(&temporary, &destination).map_err(|error| error.to_string())?;
    Ok((destination, manifest_files))
}

fn directory_files(root: &Path) -> Result<BTreeMap<PathBuf, Vec<u8>>, String> {
    fn visit(
        root: &Path,
        current: &Path,
        output: &mut BTreeMap<PathBuf, Vec<u8>>,
    ) -> Result<(), String> {
        for entry in fs::read_dir(current).map_err(|error| error.to_string())? {
            let entry = entry.map_err(|error| error.to_string())?;
            let path = entry.path();
            if path.is_dir() {
                visit(root, &path, output)?;
            } else if path.is_file() {
                let relative = path
                    .strip_prefix(root)
                    .map_err(|error| error.to_string())?
                    .to_path_buf();
                output.insert(relative, fs::read(path).map_err(|error| error.to_string())?);
            }
        }
        Ok(())
    }
    let mut output = BTreeMap::new();
    visit(root, root, &mut output)?;
    Ok(output)
}

fn write_stable_manifest(
    repository: &Path,
    version: &str,
    files: Vec<Value>,
) -> Result<PathBuf, String> {
    let stable = repository.join("published/stable");
    fs::create_dir_all(&stable).map_err(|error| error.to_string())?;
    let path = stable.join("manifest.json");
    if let Ok(raw) = fs::read_to_string(&path) {
        if let Ok(existing) = serde_json::from_str::<Value>(&raw) {
            if existing.get("version").and_then(Value::as_str) == Some(version)
                && existing.get("files") == Some(&Value::Array(files.clone()))
            {
                return Ok(path);
            }
        }
    }
    let manifest = json!({
        "schema_version": 1,
        "skill_name": "douyin-writing-skills",
        "channel": "stable",
        "version": version,
        "updated_at": Utc::now().to_rfc3339(),
        "package_path": format!("published/packages/{version}"),
        "entrypoint": "runtime/SKILL.md",
        "files": files
    });
    let temporary = stable.join(format!(".manifest-{}.tmp", Uuid::new_v4()));
    fs::write(
        &temporary,
        format!(
            "{}\n",
            serde_json::to_string_pretty(&manifest).map_err(|error| error.to_string())?
        ),
    )
    .map_err(|error| error.to_string())?;
    fs::rename(&temporary, &path).map_err(|error| error.to_string())?;
    Ok(path)
}

async fn commit_and_push(
    app: Option<&AppHandle>,
    repository: &Path,
    version: &str,
    sync_mode: &str,
    remote: &str,
    branch: &str,
) -> Result<String, String> {
    let remote = if remote.trim().is_empty() {
        "origin"
    } else {
        remote
    };
    let branch = if branch.trim().is_empty() {
        "main"
    } else {
        branch
    };
    let paths = vec![
        format!("published/packages/{version}"),
        "published/stable/manifest.json".into(),
        "SKILL.md".into(),
        "scripts/load_latest.py".into(),
        "scripts/install.sh".into(),
        "scripts/install.ps1".into(),
    ];
    emit_progress(app, "commit", "正在提交本地发布包");
    let mut add_args = vec!["add".into(), "--".into()];
    add_args.extend(paths);
    command_output("git", &add_args, Some(repository)).await?;
    let staged = command_output(
        "git",
        &["diff".into(), "--cached".into(), "--name-only".into()],
        Some(repository),
    )
    .await?;
    if !staged.trim().is_empty() {
        command_output(
            "git",
            &[
                "commit".into(),
                "-m".into(),
                format!("publish writing skills {version}"),
            ],
            Some(repository),
        )
        .await?;
    }
    if sync_mode == "github" {
        let dirty = command_output("git", &["status".into(), "--porcelain".into()], Some(repository)).await?;
        if !dirty.trim().is_empty() {
            return Err("发布仓库存在未提交的其他改动，已停止远端同步以保护这些改动。请先提交、暂存或还原它们后重试。".into());
        }
        emit_progress(app, "fetch", "正在获取 GitHub 最新变更");
        command_output(
            "git",
            &["fetch".into(), "--prune".into(), remote.into(), branch.into()],
            Some(repository),
        )
        .await?;
        let upstream = format!("{remote}/{branch}");
        emit_progress(app, "rebase", "正在整合远端发布记录");
        if let Err(error) = command_output(
            "git",
            &["rebase".into(), upstream],
            Some(repository),
        )
        .await
        {
            let _ = command_output("git", &["rebase".into(), "--abort".into()], Some(repository)).await;
            return Err(format!("远端更新无法自动整合，已中止 rebase 且保留本地发布提交：{error}"));
        }
        emit_progress(app, "push", "正在推送 stable Skill 到 GitHub");
        command_output(
            "git",
            &[
                "push".into(),
                remote.into(),
                format!("HEAD:{branch}"),
            ],
            Some(repository),
        )
        .await?;
        Ok("published".into())
    } else {
        Ok("committed_local".into())
    }
}

#[cfg(test)]
pub async fn publish_release(
    db: &DesktopDb,
    candidate: &Value,
    pack: &Value,
) -> Result<Value, String> {
    publish_release_with_progress(None, db, candidate, pack).await
}

pub async fn publish_release_with_progress(
    app: Option<&AppHandle>,
    db: &DesktopDb,
    candidate: &Value,
    pack: &Value,
) -> Result<Value, String> {
    super::validate_release_candidate(candidate, pack)?;
    let settings = load_settings(db)?;
    if settings.skill_repository_path.trim().is_empty() {
        return Err("请先在系统诊断连接或创建 Skill 发布项目".into());
    }
    let repository = PathBuf::from(&settings.skill_repository_path);
    if !repository.join(".git").is_dir() {
        return Err("配置的 Skill 发布项目不是 Git 仓库".into());
    }
    let version = pack
        .get("version")
        .and_then(Value::as_str)
        .ok_or_else(|| "发布包缺少版本号".to_string())?;
    let files = pack
        .get("files")
        .and_then(Value::as_object)
        .ok_or_else(|| "发布包缺少文件".to_string())?;
    let loader_dirty = command_output(
        "git",
        &[
            "status".into(),
            "--porcelain".into(),
            "--".into(),
            "SKILL.md".into(),
            "scripts/load_latest.py".into(),
            "scripts/install.sh".into(),
            "scripts/install.ps1".into(),
        ],
        Some(&repository),
    )
    .await?;
    if loader_dirty.lines().any(|line| !line.starts_with("?? ")) {
        return Err("固定加载器文件有尚未提交的修改；为避免混入发布提交，本次已停止".into());
    }
    seed_loader(&repository)?;
    let dirty = command_output(
        "git",
        &[
            "status".into(),
            "--porcelain".into(),
            "--".into(),
            "published/stable/manifest.json".into(),
        ],
        Some(&repository),
    )
    .await?;
    if !dirty.trim().is_empty() {
        let same_version = fs::read_to_string(repository.join("published/stable/manifest.json"))
            .ok()
            .and_then(|raw| serde_json::from_str::<Value>(&raw).ok())
            .and_then(|value| {
                value
                    .get("version")
                    .and_then(Value::as_str)
                    .map(|value| value == version)
            })
            .unwrap_or(false);
        if !same_version {
            return Err("stable 清单有其他版本的尚未提交修改；请先处理仓库冲突".into());
        }
    }
    emit_progress(app, "package", "正在生成不可变 Skill 包");
    let (package_path, manifest_files) = write_runtime_package(&repository, version, files)?;
    let manifest_path = write_stable_manifest(&repository, version, manifest_files)?;
    let status = commit_and_push(
        app,
        &repository,
        version,
        &settings.skill_sync_mode,
        &settings.skill_remote,
        &settings.skill_branch,
    )
    .await?;
    emit_progress(app, "completed", "stable Skill 已同步完成");
    Ok(json!({
        "status": status,
        "version": version,
        "repository": if settings.skill_remote_url.is_empty() { settings.skill_repository_path } else { settings.skill_remote_url },
        "packagePath": package_path,
        "manifestPath": manifest_path,
        "publishedAt": Utc::now().to_rfc3339()
    }))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::db::DesktopDb;
    use serde_json::json;

    #[test]
    fn runtime_path_rejects_traversal() {
        assert!(valid_runtime_path("SKILL.md"));
        assert!(valid_runtime_path("references/skills/example.md"));
        assert!(!valid_runtime_path("../SKILL.md"));
        assert!(!valid_runtime_path("scripts/publish.py"));
    }

    #[tokio::test]
    async fn publishes_an_immutable_local_stable_package() {
        let temp = tempfile::tempdir().unwrap();
        let db = DesktopDb::memory().unwrap();
        setup_repository(
            &db,
            RepositorySetupRequest {
                mode: "local".into(),
                repository_url: None,
                repository_name: Some("test-skills".into()),
                visibility: None,
                local_parent_path: Some(temp.path().to_string_lossy().into_owned()),
            },
        )
        .await
        .unwrap();
        let candidate = json!({
            "sourceCount": 1,
            "modelEvaluation": {"status": "passed", "score": 90},
            "humanReview": {"status": "approved"}
        });
        let pack = json!({
            "version": "wb-test-1",
            "files": {
                "SKILL.md": "# Runtime\n",
                "references/skills.json": "{\"version\":\"wb-test-1\",\"skills\":[]}\n"
            }
        });
        let result = publish_release(&db, &candidate, &pack).await.unwrap();
        assert_eq!(result["status"], "committed_local");
        let repository = temp.path().join("test-skills");
        assert!(repository.join("published/stable/manifest.json").is_file());
        assert!(repository
            .join("published/packages/wb-test-1/runtime/SKILL.md")
            .is_file());
        let changed = json!({
            "version": "wb-test-1",
            "files": {
                "SKILL.md": "# Different runtime\n",
                "references/skills.json": "{\"version\":\"wb-test-1\",\"skills\":[]}\n"
            }
        });
        assert!(publish_release(&db, &candidate, &changed)
            .await
            .unwrap_err()
            .contains("内容不同"));
    }
}
