use rusqlite::{params, Connection, OptionalExtension};
use serde_json::Value;
use std::path::Path;
use std::sync::Mutex;
use thiserror::Error;

#[derive(Debug, Error)]
pub enum DbError {
    #[error("SQLite error: {0}")]
    Sqlite(#[from] rusqlite::Error),
    #[error("JSON error: {0}")]
    Json(#[from] serde_json::Error),
    #[error("Database lock is unavailable")]
    Lock,
    #[error("Desktop snapshot has not been initialized")]
    MissingSnapshot,
}

pub struct DesktopDb {
    connection: Mutex<Connection>,
}

const SCHEMA: &str = r#"
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS app_state (
  key TEXT PRIMARY KEY,
  value_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  status TEXT NOT NULL,
  stage TEXT NOT NULL,
  progress INTEGER NOT NULL,
  media_json TEXT NOT NULL,
  config_json TEXT NOT NULL,
  local_version INTEGER NOT NULL,
  cloud_version INTEGER,
  sync_status TEXT NOT NULL,
  interrupted INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS transcript_segments (
  id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  speaker TEXT NOT NULL,
  start_ms INTEGER NOT NULL,
  end_ms INTEGER NOT NULL,
  text TEXT NOT NULL,
  review_status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS task_events (
  id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  stage TEXT NOT NULL,
  status TEXT NOT NULL,
  message TEXT NOT NULL,
  technical_detail TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS model_states (
  id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  version TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS local_versions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  version INTEGER NOT NULL,
  transcript_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(task_id, version)
);
CREATE TABLE IF NOT EXISTS sync_queue (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  object_type TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  status TEXT NOT NULL,
  retry_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sync_conflicts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  local_version INTEGER NOT NULL,
  cloud_version INTEGER NOT NULL,
  resolution TEXT,
  resolved_at TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS skills (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  version TEXT NOT NULL,
  status TEXT NOT NULL,
  source_task_id TEXT,
  metadata_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS skill_versions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  skill_id TEXT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
  version TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(skill_id, version)
);
CREATE TABLE IF NOT EXISTS privacy_preferences (
  id INTEGER PRIMARY KEY CHECK(id = 1),
  payload_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS temp_media (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  path TEXT NOT NULL,
  size_bytes INTEGER NOT NULL DEFAULT 0,
  protected INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS authorized_sources (
  id TEXT PRIMARY KEY,
  source_mode TEXT NOT NULL,
  label TEXT NOT NULL,
  source_value TEXT NOT NULL,
  authorized INTEGER NOT NULL,
  media_local_only INTEGER NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS deposit_sessions (
  id TEXT PRIMARY KEY,
  source_id TEXT REFERENCES authorized_sources(id),
  stage TEXT NOT NULL,
  transcript TEXT NOT NULL,
  transcript_quality TEXT NOT NULL,
  draft_json TEXT,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS deposit_events (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES deposit_sessions(id) ON DELETE CASCADE,
  label TEXT NOT NULL,
  detail TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS candidate_skills (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  status TEXT NOT NULL,
  source_label TEXT NOT NULL,
  source_count INTEGER NOT NULL,
  payload_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS candidate_sources (
  id TEXT PRIMARY KEY,
  candidate_id TEXT NOT NULL REFERENCES candidate_skills(id) ON DELETE CASCADE,
  source_id TEXT NOT NULL REFERENCES authorized_sources(id),
  transcript TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  added_at TEXT NOT NULL,
  UNIQUE(candidate_id, fingerprint)
);
CREATE TABLE IF NOT EXISTS candidate_evaluations (
  candidate_id TEXT PRIMARY KEY REFERENCES candidate_skills(id) ON DELETE CASCADE,
  status TEXT NOT NULL,
  score INTEGER NOT NULL,
  evaluator TEXT NOT NULL,
  summary TEXT NOT NULL,
  evaluated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS candidate_reviews (
  candidate_id TEXT PRIMARY KEY REFERENCES candidate_skills(id) ON DELETE CASCADE,
  status TEXT NOT NULL,
  reviewer TEXT NOT NULL,
  notes TEXT NOT NULL,
  reviewed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS release_exports (
  id TEXT PRIMARY KEY,
  candidate_id TEXT NOT NULL REFERENCES candidate_skills(id) ON DELETE CASCADE,
  version TEXT NOT NULL,
  path TEXT NOT NULL,
  exported_at TEXT NOT NULL,
  UNIQUE(candidate_id, version)
);
CREATE TABLE IF NOT EXISTS publish_jobs (
  id TEXT PRIMARY KEY,
  candidate_id TEXT NOT NULL REFERENCES candidate_skills(id) ON DELETE CASCADE,
  version TEXT NOT NULL,
  status TEXT NOT NULL,
  stage TEXT NOT NULL,
  repository_path TEXT NOT NULL,
  remote_url TEXT NOT NULL,
  remote TEXT NOT NULL,
  branch TEXT NOT NULL,
  package_path TEXT,
  manifest_path TEXT,
  commit_sha TEXT,
  commit_url TEXT,
  started_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  finished_at TEXT,
  error_code TEXT,
  error_message TEXT,
  remote_verified_at TEXT,
  UNIQUE(candidate_id, version)
);
CREATE TABLE IF NOT EXISTS diagnostic_logs (
  id TEXT PRIMARY KEY,
  trace_id TEXT NOT NULL,
  action TEXT NOT NULL,
  stage TEXT NOT NULL,
  status TEXT NOT NULL,
  code TEXT NOT NULL,
  message TEXT NOT NULL,
  location TEXT NOT NULL,
  detail TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_status_updated ON tasks(status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_segments_task_start ON transcript_segments(task_id, start_ms);
CREATE INDEX IF NOT EXISTS idx_events_task_created ON task_events(task_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sync_queue_status ON sync_queue(status, updated_at);
CREATE INDEX IF NOT EXISTS idx_deposit_events_created ON deposit_events(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_candidate_skills_updated ON candidate_skills(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_candidate_sources_candidate ON candidate_sources(candidate_id, added_at);
CREATE INDEX IF NOT EXISTS idx_release_exports_candidate ON release_exports(candidate_id, exported_at DESC);
CREATE INDEX IF NOT EXISTS idx_publish_jobs_candidate ON publish_jobs(candidate_id, updated_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_publish_jobs_active_candidate ON publish_jobs(candidate_id) WHERE status IN ('pending', 'running');
CREATE INDEX IF NOT EXISTS idx_diagnostic_logs_created ON diagnostic_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_diagnostic_logs_trace ON diagnostic_logs(trace_id, created_at);
"#;

impl DesktopDb {
    pub fn open(path: &Path) -> Result<Self, DbError> {
        let connection = Connection::open(path)?;
        connection.execute_batch(SCHEMA)?;
        Ok(Self {
            connection: Mutex::new(connection),
        })
    }

    #[cfg(test)]
    pub fn memory() -> Result<Self, DbError> {
        let connection = Connection::open_in_memory()?;
        connection.execute_batch(SCHEMA)?;
        Ok(Self {
            connection: Mutex::new(connection),
        })
    }

    pub fn load_snapshot(&self) -> Result<Value, DbError> {
        let connection = self.connection.lock().map_err(|_| DbError::Lock)?;
        let raw: Option<String> = connection
            .query_row(
                "SELECT value_json FROM app_state WHERE key = 'desktop_snapshot'",
                [],
                |row| row.get(0),
            )
            .optional()?;
        raw.map(|value| serde_json::from_str(&value))
            .transpose()?
            .ok_or(DbError::MissingSnapshot)
    }

    pub fn save_snapshot(&self, snapshot: &Value) -> Result<(), DbError> {
        let mut connection = self.connection.lock().map_err(|_| DbError::Lock)?;
        let transaction = connection.transaction()?;
        let now = chrono::Utc::now().to_rfc3339();
        transaction.execute(
            "INSERT INTO app_state(key, value_json, updated_at) VALUES('desktop_snapshot', ?1, ?2) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at",
            params![serde_json::to_string(snapshot)?, now],
        )?;

        if let Some(tasks) = snapshot.get("tasks").and_then(Value::as_array) {
            for task in tasks {
                transaction.execute(
                    "INSERT INTO tasks(id,title,status,stage,progress,media_json,config_json,local_version,cloud_version,sync_status,interrupted,created_at,updated_at) VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,?12,?13) ON CONFLICT(id) DO UPDATE SET title=excluded.title,status=excluded.status,stage=excluded.stage,progress=excluded.progress,media_json=excluded.media_json,config_json=excluded.config_json,local_version=excluded.local_version,cloud_version=excluded.cloud_version,sync_status=excluded.sync_status,interrupted=excluded.interrupted,updated_at=excluded.updated_at",
                    params![
                        required_str(task, "id")?, required_str(task, "title")?, required_str(task, "status")?, required_str(task, "stage")?,
                        task.get("progress").and_then(Value::as_i64).unwrap_or(0), serde_json::to_string(task.get("media").unwrap_or(&Value::Null))?,
                        serde_json::to_string(task.get("config").unwrap_or(&Value::Null))?, task.get("localVersion").and_then(Value::as_i64).unwrap_or(1),
                        task.get("cloudVersion").and_then(Value::as_i64), required_str(task, "syncStatus")?, task.get("interrupted").and_then(Value::as_bool).unwrap_or(false),
                        required_str(task, "createdAt")?, required_str(task, "updatedAt")?,
                    ],
                )?;
                upsert_segments(&transaction, task)?;
                upsert_events(&transaction, task)?;
            }
        }
        if let Some(models) = snapshot.get("models").and_then(Value::as_array) {
            for model in models {
                transaction.execute(
                    "INSERT INTO model_states(id,status,version,metadata_json,updated_at) VALUES(?1,?2,?3,?4,?5) ON CONFLICT(id) DO UPDATE SET status=excluded.status,version=excluded.version,metadata_json=excluded.metadata_json,updated_at=excluded.updated_at",
                    params![required_str(model, "id")?, required_str(model, "status")?, required_str(model, "version")?, serde_json::to_string(model)?, now],
                )?;
            }
        }
        if let Some(skills) = snapshot.get("skills").and_then(Value::as_array) {
            for skill in skills {
                upsert_skill(&transaction, skill, &now)?;
            }
        }
        if let Some(privacy) = snapshot.get("privacy") {
            transaction.execute("INSERT INTO privacy_preferences(id,payload_json,updated_at) VALUES(1,?1,?2) ON CONFLICT(id) DO UPDATE SET payload_json=excluded.payload_json,updated_at=excluded.updated_at", params![serde_json::to_string(privacy)?, now])?;
        }
        transaction.commit()?;
        Ok(())
    }

    pub fn load_skill_workbench_state(&self) -> Result<Option<Value>, DbError> {
        let connection = self.connection.lock().map_err(|_| DbError::Lock)?;
        let raw: Option<String> = connection
            .query_row(
                "SELECT value_json FROM app_state WHERE key = 'skill_workbench_v2'",
                [],
                |row| row.get(0),
            )
            .optional()?;
        raw.map(|value| serde_json::from_str(&value))
            .transpose()
            .map_err(Into::into)
    }

    pub fn save_skill_workbench_state(&self, state: &Value) -> Result<(), DbError> {
        let mut connection = self.connection.lock().map_err(|_| DbError::Lock)?;
        let transaction = connection.transaction()?;
        let now = chrono::Utc::now().to_rfc3339();
        transaction.execute(
            "INSERT INTO app_state(key,value_json,updated_at) VALUES('skill_workbench_v2',?1,?2) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at",
            params![serde_json::to_string(state)?, now],
        )?;

        if let Some(session) = state.get("session") {
            let source_id =
                if let Some(source) = session.get("source").filter(|value| !value.is_null()) {
                    let source_id = source
                        .get("id")
                        .and_then(Value::as_str)
                        .map(ToOwned::to_owned)
                        .unwrap_or_else(|| {
                            format!(
                                "source-{}",
                                source
                                    .get("createdAt")
                                    .and_then(Value::as_str)
                                    .unwrap_or(&now)
                            )
                        });
                    upsert_authorized_source(&transaction, source, &source_id)?;
                    Some(source_id)
                } else {
                    None
                };
            transaction.execute(
                "INSERT INTO deposit_sessions(id,source_id,stage,transcript,transcript_quality,draft_json,updated_at) VALUES('current',?1,?2,?3,?4,?5,?6) ON CONFLICT(id) DO UPDATE SET source_id=excluded.source_id,stage=excluded.stage,transcript=excluded.transcript,transcript_quality=excluded.transcript_quality,draft_json=excluded.draft_json,updated_at=excluded.updated_at",
                params![source_id, required_str(session,"stage")?, session.get("transcript").and_then(Value::as_str).unwrap_or(""), required_str(session,"transcriptQuality")?, session.get("draft").filter(|value| !value.is_null()).map(serde_json::to_string).transpose()?, now],
            )?;
            if let Some(events) = session.get("events").and_then(Value::as_array) {
                for event in events {
                    transaction.execute(
                        "INSERT OR IGNORE INTO deposit_events(id,session_id,label,detail,created_at) VALUES(?1,'current',?2,?3,?4)",
                        params![required_str(event,"id")?, required_str(event,"label")?, required_str(event,"detail")?, required_str(event,"at")?],
                    )?;
                }
            }
        }
        if let Some(candidates) = state.get("candidates").and_then(Value::as_array) {
            for candidate in candidates {
                transaction.execute(
                    "INSERT INTO candidate_skills(id,name,status,source_label,source_count,payload_json,updated_at) VALUES(?1,?2,?3,?4,?5,?6,?7) ON CONFLICT(id) DO UPDATE SET name=excluded.name,status=excluded.status,source_label=excluded.source_label,source_count=excluded.source_count,payload_json=excluded.payload_json,updated_at=excluded.updated_at",
                    params![required_str(candidate,"id")?, required_str(candidate,"name")?, required_str(candidate,"status")?, required_str(candidate,"sourceLabel")?, candidate.get("sourceCount").and_then(Value::as_i64).unwrap_or(1), serde_json::to_string(candidate)?, required_str(candidate,"updatedAt")?],
                )?;
                let candidate_id = required_str(candidate, "id")?;
                transaction.execute(
                    "DELETE FROM candidate_sources WHERE candidate_id=?1",
                    params![candidate_id],
                )?;
                if let Some(sources) = candidate.get("sources").and_then(Value::as_array) {
                    for evidence in sources {
                        let source = evidence.get("source").ok_or_else(|| {
                            DbError::Json(serde_json::Error::io(std::io::Error::other(
                                "candidate evidence source missing",
                            )))
                        })?;
                        let source_id = source
                            .get("id")
                            .and_then(Value::as_str)
                            .map(ToOwned::to_owned)
                            .unwrap_or_else(|| {
                                format!(
                                    "source-{}",
                                    evidence
                                        .get("id")
                                        .and_then(Value::as_str)
                                        .unwrap_or("legacy")
                                )
                            });
                        upsert_authorized_source(&transaction, source, &source_id)?;
                        transaction.execute(
                            "INSERT INTO candidate_sources(id,candidate_id,source_id,transcript,fingerprint,added_at) VALUES(?1,?2,?3,?4,?5,?6)",
                            params![required_str(evidence,"id")?, candidate_id, source_id, evidence.get("transcript").and_then(Value::as_str).unwrap_or(""), required_str(evidence,"fingerprint")?, required_str(evidence,"addedAt")?],
                        )?;
                    }
                }
                transaction.execute(
                    "DELETE FROM candidate_evaluations WHERE candidate_id=?1",
                    params![candidate_id],
                )?;
                if let Some(evaluation) = candidate
                    .get("modelEvaluation")
                    .filter(|value| !value.is_null())
                {
                    transaction.execute(
                        "INSERT INTO candidate_evaluations(candidate_id,status,score,evaluator,summary,evaluated_at) VALUES(?1,?2,?3,?4,?5,?6)",
                        params![candidate_id, required_str(evaluation,"status")?, evaluation.get("score").and_then(Value::as_i64).unwrap_or(0), required_str(evaluation,"evaluator")?, required_str(evaluation,"summary")?, required_str(evaluation,"evaluatedAt")?],
                    )?;
                }
                transaction.execute(
                    "DELETE FROM candidate_reviews WHERE candidate_id=?1",
                    params![candidate_id],
                )?;
                if let Some(review) = candidate
                    .get("humanReview")
                    .filter(|value| !value.is_null())
                {
                    transaction.execute(
                        "INSERT INTO candidate_reviews(candidate_id,status,reviewer,notes,reviewed_at) VALUES(?1,?2,?3,?4,?5)",
                        params![candidate_id, required_str(review,"status")?, required_str(review,"reviewer")?, required_str(review,"notes")?, required_str(review,"reviewedAt")?],
                    )?;
                }
                transaction.execute(
                    "DELETE FROM release_exports WHERE candidate_id=?1",
                    params![candidate_id],
                )?;
                if let Some(release) = candidate.get("release").filter(|value| !value.is_null()) {
                    let version = required_str(release, "version")?;
                    transaction.execute(
                        "INSERT INTO release_exports(id,candidate_id,version,path,exported_at) VALUES(?1,?2,?3,?4,?5)",
                        params![format!("{candidate_id}-{version}"), candidate_id, version, required_str(release,"path")?, required_str(release,"exportedAt")?],
                    )?;
                }
            }
        }
        transaction.commit()?;
        Ok(())
    }

    pub fn load_app_value(&self, key: &str) -> Result<Option<Value>, DbError> {
        let connection = self.connection.lock().map_err(|_| DbError::Lock)?;
        let raw: Option<String> = connection
            .query_row(
                "SELECT value_json FROM app_state WHERE key=?1",
                params![key],
                |row| row.get(0),
            )
            .optional()?;
        raw.map(|value| serde_json::from_str(&value))
            .transpose()
            .map_err(Into::into)
    }

    pub fn load_candidate(&self, candidate_id: &str) -> Result<Option<Value>, DbError> {
        let connection = self.connection.lock().map_err(|_| DbError::Lock)?;
        let raw: Option<String> = connection
            .query_row(
                "SELECT payload_json FROM candidate_skills WHERE id=?1",
                params![candidate_id],
                |row| row.get(0),
            )
            .optional()?;
        raw.map(|value| serde_json::from_str(&value)).transpose().map_err(Into::into)
    }

    pub fn latest_publish_job(&self, candidate_id: &str) -> Result<Option<Value>, DbError> {
        let connection = self.connection.lock().map_err(|_| DbError::Lock)?;
        let raw: Option<String> = connection
            .query_row(
                "SELECT json_object('id',id,'candidateId',candidate_id,'version',version,'status',status,'stage',stage,'repositoryPath',repository_path,'remoteUrl',remote_url,'remote',remote,'branch',branch,'packagePath',package_path,'manifestPath',manifest_path,'commitSha',commit_sha,'commitUrl',commit_url,'startedAt',started_at,'updatedAt',updated_at,'finishedAt',finished_at,'errorCode',error_code,'errorMessage',error_message,'remoteVerifiedAt',remote_verified_at) FROM publish_jobs WHERE candidate_id=?1 ORDER BY updated_at DESC LIMIT 1",
                params![candidate_id],
                |row| row.get(0),
            )
            .optional()?;
        raw.map(|value| serde_json::from_str(&value)).transpose().map_err(Into::into)
    }

    pub fn save_publish_job(&self, job: &Value) -> Result<Value, DbError> {
        let id = required_str(job, "id")?;
        let candidate_id = required_str(job, "candidateId")?;
        let version = required_str(job, "version")?;
        let status = required_str(job, "status")?;
        let stage = required_str(job, "stage")?;
        let repository_path = required_str(job, "repositoryPath")?;
        let remote_url = job.get("remoteUrl").and_then(Value::as_str).unwrap_or("");
        let remote = required_str(job, "remote")?;
        let branch = required_str(job, "branch")?;
        let started_at = required_str(job, "startedAt")?;
        let updated_at = required_str(job, "updatedAt")?;
        let connection = self.connection.lock().map_err(|_| DbError::Lock)?;
        connection.execute(
            "INSERT INTO publish_jobs(id,candidate_id,version,status,stage,repository_path,remote_url,remote,branch,package_path,manifest_path,commit_sha,commit_url,started_at,updated_at,finished_at,error_code,error_message,remote_verified_at) VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,?12,?13,?14,?15,?16,?17,?18,?19) ON CONFLICT(id) DO UPDATE SET status=excluded.status,stage=excluded.stage,package_path=excluded.package_path,manifest_path=excluded.manifest_path,commit_sha=excluded.commit_sha,commit_url=excluded.commit_url,updated_at=excluded.updated_at,finished_at=excluded.finished_at,error_code=excluded.error_code,error_message=excluded.error_message,remote_verified_at=excluded.remote_verified_at",
            params![id, candidate_id, version, status, stage, repository_path, remote_url, remote, branch, job.get("packagePath").and_then(Value::as_str), job.get("manifestPath").and_then(Value::as_str), job.get("commitSha").and_then(Value::as_str), job.get("commitUrl").and_then(Value::as_str), started_at, updated_at, job.get("finishedAt").and_then(Value::as_str), job.get("errorCode").and_then(Value::as_str), job.get("errorMessage").and_then(Value::as_str), job.get("remoteVerifiedAt").and_then(Value::as_str)],
        )?;
        Ok(job.clone())
    }

    pub fn mark_candidate_released(&self, candidate_id: &str, version: &str, path: &str) -> Result<(), DbError> {
        let mut connection = self.connection.lock().map_err(|_| DbError::Lock)?;
        let transaction = connection.transaction()?;
        let now = chrono::Utc::now().to_rfc3339();
        let raw: String = transaction.query_row(
            "SELECT value_json FROM app_state WHERE key = 'skill_workbench_v2'",
            [],
            |row| row.get(0),
        )?;
        let mut state: Value = serde_json::from_str(&raw)?;
        let candidate_payload = {
            let candidates = state.get_mut("candidates").and_then(Value::as_array_mut).ok_or(DbError::MissingSnapshot)?;
            let candidate = candidates.iter_mut().find(|candidate| candidate.get("id").and_then(Value::as_str) == Some(candidate_id)).ok_or(DbError::MissingSnapshot)?;
            candidate["release"] = serde_json::json!({"version": version, "path": path, "exportedAt": now});
            candidate["status"] = Value::String("exported".into());
            candidate["updatedAt"] = Value::String(now.clone());
            serde_json::to_string(candidate)?
        };
        transaction.execute(
            "UPDATE app_state SET value_json=?1,updated_at=?2 WHERE key='skill_workbench_v2'",
            params![serde_json::to_string(&state)?, now],
        )?;
        transaction.execute(
            "UPDATE candidate_skills SET status='exported',payload_json=?1,updated_at=?2 WHERE id=?3",
            params![candidate_payload, now, candidate_id],
        )?;
        transaction.execute("DELETE FROM release_exports WHERE candidate_id=?1", params![candidate_id])?;
        transaction.execute(
            "INSERT INTO release_exports(id,candidate_id,version,path,exported_at) VALUES(?1,?2,?3,?4,?5)",
            params![format!("{candidate_id}-{version}"), candidate_id, version, path, now],
        )?;
        transaction.commit()?;
        Ok(())
    }

    pub fn save_app_value(&self, key: &str, value: &Value) -> Result<(), DbError> {
        let connection = self.connection.lock().map_err(|_| DbError::Lock)?;
        connection.execute(
            "INSERT INTO app_state(key,value_json,updated_at) VALUES(?1,?2,?3) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at",
            params![key, serde_json::to_string(value)?, chrono::Utc::now().to_rfc3339()],
        )?;
        Ok(())
    }

    pub fn save_transcript(&self, task_id: &str, segments: &Value) -> Result<(), DbError> {
        let mut connection = self.connection.lock().map_err(|_| DbError::Lock)?;
        let transaction = connection.transaction()?;
        transaction.execute(
            "DELETE FROM transcript_segments WHERE task_id = ?1",
            params![task_id],
        )?;
        if let Some(items) = segments.as_array() {
            for segment in items {
                insert_segment(&transaction, task_id, segment)?;
            }
        }
        let next_version: i64 = transaction.query_row(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM local_versions WHERE task_id=?1",
            params![task_id],
            |row| row.get(0),
        )?;
        transaction.execute("INSERT INTO local_versions(task_id,version,transcript_json,created_at) VALUES(?1,?2,?3,?4)", params![task_id, next_version, serde_json::to_string(segments)?, chrono::Utc::now().to_rfc3339()])?;
        transaction.commit()?;
        Ok(())
    }

    pub fn save_event(&self, event: &Value) -> Result<(), DbError> {
        let connection = self.connection.lock().map_err(|_| DbError::Lock)?;
        let id = event
            .get("id")
            .and_then(Value::as_str)
            .map(ToOwned::to_owned)
            .unwrap_or_else(|| uuid::Uuid::new_v4().to_string());
        connection.execute("INSERT OR IGNORE INTO task_events(id,task_id,stage,status,message,technical_detail,created_at) VALUES(?1,?2,?3,?4,?5,?6,?7)", params![id, required_str(event,"taskId")?, event.get("stage").and_then(Value::as_str).unwrap_or("needs_attention"), event.get("status").and_then(Value::as_str).unwrap_or("info"), event.get("message").and_then(Value::as_str).unwrap_or("sidecar event"), event.get("technicalDetail").and_then(Value::as_str), chrono::Utc::now().to_rfc3339()])?;
        Ok(())
    }

    pub fn record_diagnostic_log(&self, log: &Value) -> Result<Value, DbError> {
        let id = log
            .get("id")
            .and_then(Value::as_str)
            .filter(|value| !value.is_empty())
            .map(ToOwned::to_owned)
            .unwrap_or_else(|| format!("diagnostic-{}", uuid::Uuid::new_v4()));
        let created_at = log
            .get("createdAt")
            .and_then(Value::as_str)
            .filter(|value| !value.is_empty())
            .map(ToOwned::to_owned)
            .unwrap_or_else(|| chrono::Utc::now().to_rfc3339());
        let value = serde_json::json!({
            "id": id,
            "traceId": log.get("traceId").and_then(Value::as_str).unwrap_or("standalone"),
            "action": log.get("action").and_then(Value::as_str).unwrap_or("unknown.action"),
            "stage": log.get("stage").and_then(Value::as_str).unwrap_or("unknown"),
            "status": log.get("status").and_then(Value::as_str).unwrap_or("info"),
            "code": log.get("code").and_then(Value::as_str).unwrap_or("DIAGNOSTIC_INFO"),
            "message": log.get("message").and_then(Value::as_str).unwrap_or("运行事件"),
            "location": log.get("location").and_then(Value::as_str).unwrap_or("runtime"),
            "detail": log.get("detail").and_then(Value::as_str),
            "createdAt": created_at,
        });
        let connection = self.connection.lock().map_err(|_| DbError::Lock)?;
        connection.execute(
            "INSERT INTO diagnostic_logs(id,trace_id,action,stage,status,code,message,location,detail,created_at) VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9,?10)",
            params![
                value["id"].as_str(), value["traceId"].as_str(), value["action"].as_str(),
                value["stage"].as_str(), value["status"].as_str(), value["code"].as_str(),
                value["message"].as_str(), value["location"].as_str(), value["detail"].as_str(),
                value["createdAt"].as_str(),
            ],
        )?;
        Ok(value)
    }

    pub fn list_diagnostic_logs(&self, limit: u32) -> Result<Vec<Value>, DbError> {
        let connection = self.connection.lock().map_err(|_| DbError::Lock)?;
        let mut statement = connection.prepare(
            "SELECT id,trace_id,action,stage,status,code,message,location,detail,created_at FROM diagnostic_logs ORDER BY created_at DESC LIMIT ?1",
        )?;
        let rows = statement.query_map(params![i64::from(limit.clamp(1, 500))], |row| {
            Ok(serde_json::json!({
                "id": row.get::<_, String>(0)?, "traceId": row.get::<_, String>(1)?,
                "action": row.get::<_, String>(2)?, "stage": row.get::<_, String>(3)?,
                "status": row.get::<_, String>(4)?, "code": row.get::<_, String>(5)?,
                "message": row.get::<_, String>(6)?, "location": row.get::<_, String>(7)?,
                "detail": row.get::<_, Option<String>>(8)?, "createdAt": row.get::<_, String>(9)?,
            }))
        })?;
        rows.collect::<Result<Vec<_>, _>>().map_err(Into::into)
    }

    pub fn clear_diagnostic_logs(&self) -> Result<(), DbError> {
        let connection = self.connection.lock().map_err(|_| DbError::Lock)?;
        connection.execute("DELETE FROM diagnostic_logs", [])?;
        Ok(())
    }

    pub fn resolve_conflict(&self, task_id: &str, resolution: &str) -> Result<(), DbError> {
        let connection = self.connection.lock().map_err(|_| DbError::Lock)?;
        connection.execute("UPDATE sync_conflicts SET resolution=?1,resolved_at=?2 WHERE task_id=?3 AND resolved_at IS NULL", params![resolution, chrono::Utc::now().to_rfc3339(), task_id])?;
        Ok(())
    }

    pub fn save_skill_version(&self, skill: &Value) -> Result<(), DbError> {
        let connection = self.connection.lock().map_err(|_| DbError::Lock)?;
        let now = chrono::Utc::now().to_rfc3339();
        upsert_skill(&connection, skill, &now)?;
        connection.execute("INSERT OR IGNORE INTO skill_versions(skill_id,version,payload_json,created_at) VALUES(?1,?2,?3,?4)", params![required_str(skill,"id")?,required_str(skill,"version")?,serde_json::to_string(skill)?,now])?;
        Ok(())
    }

    pub fn save_privacy(&self, privacy: &Value) -> Result<(), DbError> {
        let connection = self.connection.lock().map_err(|_| DbError::Lock)?;
        connection.execute("INSERT INTO privacy_preferences(id,payload_json,updated_at) VALUES(1,?1,?2) ON CONFLICT(id) DO UPDATE SET payload_json=excluded.payload_json,updated_at=excluded.updated_at", params![serde_json::to_string(privacy)?, chrono::Utc::now().to_rfc3339()])?;
        Ok(())
    }

    pub fn clearable_temp_media(&self, task_ids: &[String]) -> Result<Vec<(i64, String)>, DbError> {
        let connection = self.connection.lock().map_err(|_| DbError::Lock)?;
        let mut output = Vec::new();
        let mut statement = connection
            .prepare("SELECT size_bytes,path FROM temp_media WHERE task_id=?1 AND protected=0")?;
        for task_id in task_ids {
            let rows =
                statement.query_map(params![task_id], |row| Ok((row.get(0)?, row.get(1)?)))?;
            for row in rows {
                output.push(row?);
            }
        }
        Ok(output)
    }
}

fn required_str<'a>(value: &'a Value, key: &str) -> Result<&'a str, DbError> {
    value.get(key).and_then(Value::as_str).ok_or_else(|| {
        serde_json::Error::io(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            format!("missing {key}"),
        ))
        .into()
    })
}

fn upsert_authorized_source(
    connection: &Connection,
    source: &Value,
    source_id: &str,
) -> Result<(), DbError> {
    connection.execute(
        "INSERT INTO authorized_sources(id,source_mode,label,source_value,authorized,media_local_only,created_at) VALUES(?1,?2,?3,?4,?5,?6,?7) ON CONFLICT(id) DO UPDATE SET source_mode=excluded.source_mode,label=excluded.label,source_value=excluded.source_value,authorized=excluded.authorized,media_local_only=excluded.media_local_only",
        params![source_id, required_str(source,"mode")?, required_str(source,"label")?, required_str(source,"value")?, source.get("authorized").and_then(Value::as_bool).unwrap_or(false), source.get("mediaLocalOnly").and_then(Value::as_bool).unwrap_or(false), required_str(source,"createdAt")?],
    )?;
    Ok(())
}

fn upsert_segments(connection: &Connection, task: &Value) -> Result<(), DbError> {
    let task_id = required_str(task, "id")?;
    if let Some(segments) = task.get("segments").and_then(Value::as_array) {
        for segment in segments {
            insert_segment(connection, task_id, segment)?;
        }
    }
    Ok(())
}

fn insert_segment(connection: &Connection, task_id: &str, segment: &Value) -> Result<(), DbError> {
    connection.execute("INSERT INTO transcript_segments(id,task_id,speaker,start_ms,end_ms,text,review_status) VALUES(?1,?2,?3,?4,?5,?6,?7) ON CONFLICT(id) DO UPDATE SET speaker=excluded.speaker,start_ms=excluded.start_ms,end_ms=excluded.end_ms,text=excluded.text,review_status=excluded.review_status", params![required_str(segment,"id")?,task_id,required_str(segment,"speaker")?,segment.get("startMs").and_then(Value::as_i64).unwrap_or(0),segment.get("endMs").and_then(Value::as_i64).unwrap_or(0),required_str(segment,"text")?,required_str(segment,"reviewStatus")?])?;
    Ok(())
}

fn upsert_events(connection: &Connection, task: &Value) -> Result<(), DbError> {
    if let Some(events) = task.get("events").and_then(Value::as_array) {
        for event in events {
            connection.execute("INSERT OR IGNORE INTO task_events(id,task_id,stage,status,message,technical_detail,created_at) VALUES(?1,?2,?3,?4,?5,?6,?7)", params![required_str(event,"id")?,required_str(task,"id")?,required_str(event,"stage")?,required_str(event,"status")?,required_str(event,"message")?,event.get("technicalDetail").and_then(Value::as_str),required_str(event,"createdAt")?])?;
        }
    }
    Ok(())
}

fn upsert_skill(connection: &Connection, skill: &Value, now: &str) -> Result<(), DbError> {
    connection.execute("INSERT INTO skills(id,name,version,status,source_task_id,metadata_json,updated_at) VALUES(?1,?2,?3,?4,?5,?6,?7) ON CONFLICT(id) DO UPDATE SET name=excluded.name,version=excluded.version,status=excluded.status,source_task_id=excluded.source_task_id,metadata_json=excluded.metadata_json,updated_at=excluded.updated_at", params![required_str(skill,"id")?,required_str(skill,"name")?,required_str(skill,"version")?,required_str(skill,"status")?,skill.get("sourceTaskId").and_then(Value::as_str),serde_json::to_string(skill)?,now])?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn persists_snapshot_and_normalized_records() {
        let db = DesktopDb::memory().unwrap();
        let snapshot = json!({
          "tasks": [{"id":"task-1","title":"test","status":"queued","stage":"preparing_media","progress":0,"media":{},"config":{},"localVersion":1,"cloudVersion":null,"syncStatus":"local_only","interrupted":false,"createdAt":"2026-08-03T00:00:00Z","updatedAt":"2026-08-03T00:00:00Z","segments":[],"events":[]}],
          "models": [], "skills": [], "privacy": {}
        });
        db.save_snapshot(&snapshot).unwrap();
        assert_eq!(db.load_snapshot().unwrap(), snapshot);
    }

    #[test]
    fn transcript_save_creates_immutable_local_version() {
        let db = DesktopDb::memory().unwrap();
        let snapshot = json!({"tasks":[{"id":"task-1","title":"test","status":"completed","stage":"completed","progress":100,"media":{},"config":{},"localVersion":1,"cloudVersion":null,"syncStatus":"local_only","interrupted":false,"createdAt":"2026-08-03T00:00:00Z","updatedAt":"2026-08-03T00:00:00Z","segments":[],"events":[]}],"models":[],"skills":[],"privacy":{}});
        db.save_snapshot(&snapshot).unwrap();
        let segments = json!([{"id":"seg-1","speaker":"A","startMs":0,"endMs":1000,"text":"hello","reviewStatus":"reviewed"}]);
        db.save_transcript("task-1", &segments).unwrap();
        db.save_transcript("task-1", &segments).unwrap();
        let connection = db.connection.lock().unwrap();
        let count: i64 = connection
            .query_row(
                "SELECT COUNT(*) FROM local_versions WHERE task_id='task-1'",
                [],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(count, 2);
    }

    #[test]
    fn persists_lists_and_clears_diagnostic_logs() {
        let db = DesktopDb::memory().unwrap();
        let saved = db.record_diagnostic_log(&json!({
            "traceId": "media-test", "action": "media.process", "stage": "transcription",
            "status": "error", "code": "MEDIA_TRANSCRIPT_RESULT_MISSING",
            "message": "真实稿件提取失败", "location": "media.rs:process_media/transcription",
            "detail": "No such file or directory"
        })).unwrap();
        assert_eq!(saved["code"], "MEDIA_TRANSCRIPT_RESULT_MISSING");
        let logs = db.list_diagnostic_logs(10).unwrap();
        assert_eq!(logs.len(), 1);
        assert_eq!(logs[0]["traceId"], "media-test");
        db.clear_diagnostic_logs().unwrap();
        assert!(db.list_diagnostic_logs(10).unwrap().is_empty());
    }

    #[test]
    fn skill_workbench_state_normalizes_sources_and_candidates() {
        let db = DesktopDb::memory().unwrap();
        let state = json!({
          "session": {
            "stage":"candidate_saved",
            "source":{"id":"source-1","mode":"verified_transcript","label":"授权稿件 1","value":"verified-1","authorized":true,"mediaLocalOnly":false,"createdAt":"2026-08-03T00:00:00Z"},
            "transcript":"真实稿件正文","transcriptQuality":"verified",
            "draft":{"name":"候选"},
            "events":[{"id":"event-1","label":"候选已保存","detail":"单条授权真实稿件","at":"2026-08-03T00:01:00Z"}]
          },
          "candidates":[{
            "id":"candidate-1","name":"候选","status":"exported","sourceLabel":"授权稿件 1","sourceCount":1,"updatedAt":"2026-08-03T00:05:00Z",
            "sources":[
              {"id":"evidence-1","source":{"id":"source-1","mode":"verified_transcript","label":"授权稿件 1","value":"verified-1","authorized":true,"mediaLocalOnly":false,"createdAt":"2026-08-03T00:00:00Z"},"transcript":"稿件一","fingerprint":"fp-1","addedAt":"2026-08-03T00:01:00Z"}
            ],
            "modelEvaluation":{"status":"passed","score":86,"evaluator":"reviewer-model","summary":"通过","evaluatedAt":"2026-08-03T00:03:30Z"},
            "humanReview":{"status":"approved","reviewer":"主审 A","notes":"批准","reviewedAt":"2026-08-03T00:04:00Z"},
            "release":{"version":"wb-test","path":"/tmp/skill-pack.json","exportedAt":"2026-08-03T00:05:00Z"}
          }]
        });
        db.save_skill_workbench_state(&state).unwrap();
        assert_eq!(db.load_skill_workbench_state().unwrap().unwrap(), state);
        let connection = db.connection.lock().unwrap();
        let source_count: i64 = connection
            .query_row("SELECT COUNT(*) FROM authorized_sources", [], |row| {
                row.get(0)
            })
            .unwrap();
        let candidate_count: i64 = connection
            .query_row("SELECT COUNT(*) FROM candidate_skills", [], |row| {
                row.get(0)
            })
            .unwrap();
        let evidence_count: i64 = connection
            .query_row("SELECT COUNT(*) FROM candidate_sources", [], |row| {
                row.get(0)
            })
            .unwrap();
        let evaluation_count: i64 = connection
            .query_row("SELECT COUNT(*) FROM candidate_evaluations", [], |row| {
                row.get(0)
            })
            .unwrap();
        let review_count: i64 = connection
            .query_row("SELECT COUNT(*) FROM candidate_reviews", [], |row| {
                row.get(0)
            })
            .unwrap();
        let release_count: i64 = connection
            .query_row("SELECT COUNT(*) FROM release_exports", [], |row| row.get(0))
            .unwrap();
        assert_eq!(
            (
                source_count,
                candidate_count,
                evidence_count,
                evaluation_count,
                review_count,
                release_count
            ),
            (1, 1, 1, 1, 1, 1)
        );
    }
}
