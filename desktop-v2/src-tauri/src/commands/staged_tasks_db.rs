//! Local SQLite store for staged tasks (TaskAssistant parity with Swift).
//!
//! Mirrors `desktop/Desktop/Sources/ProactiveAssistants/Storage/ProactiveStorage.swift`
//! and `EmbeddingService.swift`'s on-disk index. Schema:
//!
//! - `staged_tasks` — extracted tasks awaiting review/promotion. Includes a
//!   raw `embedding BLOB` column (3072 f32s, normalized) so we can compute
//!   cosine similarity in-process without depending on sqlite-vec.
//! - `staged_tasks_fts` — FTS5 virtual table over `description` for keyword
//!   search (used by the `search_keywords` Gemini tool).
//! - `dedup_logs` — audit trail of every duplicate group the dedup service
//!   removed.
//!
//! All commands are exposed as `#[tauri::command]` and called from
//! `services/taskAssistant.ts` via `invoke()`.

use std::path::Path;
use std::sync::Mutex;

use chrono::Utc;
use rusqlite::{params, Connection, OptionalExtension, Result};
use serde::{Deserialize, Serialize};
use tauri::{command, AppHandle, Manager, State};

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/// One staged task row. Field names match the JSON keys consumed by the
/// frontend (`stagedTaskStore.ts`).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StagedTask {
    pub id: String,
    pub description: String,
    pub priority: Option<String>,
    pub tags_json: Option<String>,
    pub due_at: Option<String>,
    pub confidence: Option<f64>,
    pub source_app: Option<String>,
    pub window_title: Option<String>,
    pub context_summary: Option<String>,
    pub current_activity: Option<String>,
    pub metadata_json: Option<String>,
    pub relevance_score: Option<f64>,
    pub screenshot_id: Option<i64>,
    pub created_at: String,
    pub updated_at: String,
    pub backend_id: Option<String>,
    pub deleted: bool,
    pub completed: bool,
}

/// Input payload for `upsert_staged_task`. `id` may be omitted to mint a UUID.
#[derive(Debug, Clone, Deserialize)]
pub struct StagedTaskInput {
    pub id: Option<String>,
    pub description: String,
    pub priority: Option<String>,
    pub tags_json: Option<String>,
    pub due_at: Option<String>,
    pub confidence: Option<f64>,
    pub source_app: Option<String>,
    pub window_title: Option<String>,
    pub context_summary: Option<String>,
    pub current_activity: Option<String>,
    pub metadata_json: Option<String>,
    pub relevance_score: Option<f64>,
    pub screenshot_id: Option<i64>,
}

/// Search result with similarity score (cosine, 0..1).
#[derive(Debug, Clone, Serialize)]
pub struct SimilarTask {
    pub task: StagedTask,
    pub similarity: f64,
}

/// Item returned by `get_items_missing_embeddings` so the embedding service
/// can backfill in batches. The `kind` distinguishes staged tasks from any
/// future tables (only `staged_task` today).
#[derive(Debug, Clone, Serialize)]
pub struct EmbeddingBacklogItem {
    pub kind: String,
    pub id: String,
    pub text: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct DedupLogInput {
    pub kept_id: String,
    pub deleted_ids: Vec<String>,
    pub reason: String,
}

// ---------------------------------------------------------------------------
// Storage
// ---------------------------------------------------------------------------

pub struct StagedTasksDb {
    conn: Mutex<Connection>,
}

impl StagedTasksDb {
    pub fn init(app_data_dir: &Path) -> Result<Self> {
        let dir = app_data_dir.join("proactive");
        std::fs::create_dir_all(&dir).map_err(|e| {
            rusqlite::Error::SqliteFailure(
                rusqlite::ffi::Error::new(rusqlite::ffi::SQLITE_CANTOPEN),
                Some(format!("create proactive dir: {}", e)),
            )
        })?;

        let db_path = dir.join("staged_tasks.db");
        tracing::info!("Opening staged-tasks database at {:?}", db_path);

        let conn = Connection::open(&db_path)?;

        let _mode: String =
            conn.query_row("PRAGMA journal_mode=WAL", [], |row| row.get(0))?;
        conn.execute_batch("PRAGMA foreign_keys = ON;")?;
        conn.execute_batch(MIGRATION_V1)?;

        Ok(Self { conn: Mutex::new(conn) })
    }

    fn now() -> String {
        Utc::now().to_rfc3339()
    }

    fn upsert(&self, input: StagedTaskInput) -> Result<StagedTask> {
        let id = input.id.unwrap_or_else(|| uuid::Uuid::new_v4().to_string());
        let now = Self::now();

        let conn = self.conn.lock().expect("staged_tasks db poisoned");

        // Upsert via INSERT … ON CONFLICT(id). Embedding column is left NULL
        // here — the embedding service backfills via `update_embedding`.
        conn.execute(
            r#"
            INSERT INTO staged_tasks (
                id, description, priority, tags_json, due_at, confidence,
                source_app, window_title, context_summary, current_activity,
                metadata_json, relevance_score, screenshot_id,
                created_at, updated_at, deleted, completed
            ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, 0, 0)
            ON CONFLICT(id) DO UPDATE SET
                description = excluded.description,
                priority = excluded.priority,
                tags_json = excluded.tags_json,
                due_at = excluded.due_at,
                confidence = excluded.confidence,
                source_app = excluded.source_app,
                window_title = excluded.window_title,
                context_summary = excluded.context_summary,
                current_activity = excluded.current_activity,
                metadata_json = excluded.metadata_json,
                relevance_score = excluded.relevance_score,
                screenshot_id = excluded.screenshot_id,
                updated_at = excluded.updated_at
            "#,
            params![
                id,
                input.description,
                input.priority,
                input.tags_json,
                input.due_at,
                input.confidence,
                input.source_app,
                input.window_title,
                input.context_summary,
                input.current_activity,
                input.metadata_json,
                input.relevance_score,
                input.screenshot_id,
                now,
                now,
            ],
        )?;

        // Sync the FTS row. (External-content tables aren't used here so we
        // can keep the schema dead simple — manual upsert into the FTS
        // virtual table.)
        conn.execute("DELETE FROM staged_tasks_fts WHERE id = ?1", params![id])?;
        conn.execute(
            "INSERT INTO staged_tasks_fts (id, description) VALUES (?1, ?2)",
            params![id, input.description],
        )?;

        drop(conn);
        self.get_by_id(&id)?
            .ok_or_else(|| rusqlite::Error::QueryReturnedNoRows)
    }

    fn get_by_id(&self, id: &str) -> Result<Option<StagedTask>> {
        let conn = self.conn.lock().expect("staged_tasks db poisoned");
        conn.query_row(
            "SELECT id, description, priority, tags_json, due_at, confidence,
                    source_app, window_title, context_summary, current_activity,
                    metadata_json, relevance_score, screenshot_id,
                    created_at, updated_at, backend_id, deleted, completed
             FROM staged_tasks WHERE id = ?1",
            params![id],
            map_row,
        )
        .optional()
    }

    fn list_active(&self, limit: usize) -> Result<Vec<StagedTask>> {
        let conn = self.conn.lock().expect("staged_tasks db poisoned");
        let mut stmt = conn.prepare(
            "SELECT id, description, priority, tags_json, due_at, confidence,
                    source_app, window_title, context_summary, current_activity,
                    metadata_json, relevance_score, screenshot_id,
                    created_at, updated_at, backend_id, deleted, completed
             FROM staged_tasks
             WHERE deleted = 0
             ORDER BY datetime(created_at) DESC
             LIMIT ?1",
        )?;
        let rows = stmt
            .query_map(params![limit as i64], map_row)?
            .collect::<Result<Vec<_>>>()?;
        Ok(rows)
    }

    fn list_recent_for_prompt(&self, hours: i64, limit: usize) -> Result<Vec<StagedTask>> {
        let cutoff = Utc::now() - chrono::Duration::hours(hours);
        let conn = self.conn.lock().expect("staged_tasks db poisoned");
        let mut stmt = conn.prepare(
            "SELECT id, description, priority, tags_json, due_at, confidence,
                    source_app, window_title, context_summary, current_activity,
                    metadata_json, relevance_score, screenshot_id,
                    created_at, updated_at, backend_id, deleted, completed
             FROM staged_tasks
             WHERE deleted = 0 AND datetime(created_at) >= datetime(?1)
             ORDER BY datetime(created_at) DESC
             LIMIT ?2",
        )?;
        let rows = stmt
            .query_map(params![cutoff.to_rfc3339(), limit as i64], map_row)?
            .collect::<Result<Vec<_>>>()?;
        Ok(rows)
    }

    fn delete(&self, id: &str, hard: bool) -> Result<()> {
        let conn = self.conn.lock().expect("staged_tasks db poisoned");
        if hard {
            conn.execute("DELETE FROM staged_tasks WHERE id = ?1", params![id])?;
            conn.execute("DELETE FROM staged_tasks_fts WHERE id = ?1", params![id])?;
        } else {
            conn.execute(
                "UPDATE staged_tasks SET deleted = 1, updated_at = ?2 WHERE id = ?1",
                params![id, Self::now()],
            )?;
        }
        Ok(())
    }

    fn set_completed(&self, id: &str, completed: bool) -> Result<()> {
        let conn = self.conn.lock().expect("staged_tasks db poisoned");
        conn.execute(
            "UPDATE staged_tasks SET completed = ?2, updated_at = ?3 WHERE id = ?1",
            params![id, completed as i32, Self::now()],
        )?;
        Ok(())
    }

    fn set_backend_id(&self, id: &str, backend_id: &str) -> Result<()> {
        let conn = self.conn.lock().expect("staged_tasks db poisoned");
        conn.execute(
            "UPDATE staged_tasks SET backend_id = ?2, updated_at = ?3 WHERE id = ?1",
            params![id, backend_id, Self::now()],
        )?;
        Ok(())
    }

    fn save_embedding(&self, id: &str, embedding: &[f32]) -> Result<()> {
        let bytes: Vec<u8> = embedding
            .iter()
            .flat_map(|f| f.to_le_bytes())
            .collect();
        let conn = self.conn.lock().expect("staged_tasks db poisoned");
        conn.execute(
            "UPDATE staged_tasks SET embedding = ?2 WHERE id = ?1",
            params![id, bytes],
        )?;
        Ok(())
    }

    fn items_missing_embeddings(&self, limit: usize) -> Result<Vec<EmbeddingBacklogItem>> {
        let conn = self.conn.lock().expect("staged_tasks db poisoned");
        let mut stmt = conn.prepare(
            "SELECT id, description FROM staged_tasks
             WHERE deleted = 0 AND embedding IS NULL
             ORDER BY datetime(created_at) DESC
             LIMIT ?1",
        )?;
        let rows = stmt
            .query_map(params![limit as i64], |row| {
                Ok(EmbeddingBacklogItem {
                    kind: "staged_task".to_string(),
                    id: row.get::<_, String>(0)?,
                    text: row.get::<_, String>(1)?,
                })
            })?
            .collect::<Result<Vec<_>>>()?;
        Ok(rows)
    }

    /// Cosine over the in-DB BLOB embeddings. We pre-normalize on write, so
    /// cosine = dot product. Vectors that fail to parse (length mismatch)
    /// are skipped.
    fn search_similar(&self, query: &[f32], top_k: usize, min_sim: f32) -> Result<Vec<SimilarTask>> {
        let conn = self.conn.lock().expect("staged_tasks db poisoned");
        let mut stmt = conn.prepare(
            "SELECT id, description, priority, tags_json, due_at, confidence,
                    source_app, window_title, context_summary, current_activity,
                    metadata_json, relevance_score, screenshot_id,
                    created_at, updated_at, backend_id, deleted, completed,
                    embedding
             FROM staged_tasks
             WHERE deleted = 0 AND embedding IS NOT NULL",
        )?;

        let mut scored: Vec<SimilarTask> = stmt
            .query_map([], |row| {
                let task = map_row(row)?;
                let blob: Vec<u8> = row.get(18)?;
                Ok((task, blob))
            })?
            .filter_map(|res| res.ok())
            .filter_map(|(task, blob)| {
                let vec = parse_embedding(&blob)?;
                if vec.len() != query.len() {
                    return None;
                }
                let sim = dot(&vec, query);
                if sim < min_sim {
                    return None;
                }
                Some(SimilarTask {
                    task,
                    similarity: sim as f64,
                })
            })
            .collect();

        scored.sort_by(|a, b| {
            b.similarity
                .partial_cmp(&a.similarity)
                .unwrap_or(std::cmp::Ordering::Equal)
        });
        scored.truncate(top_k);
        Ok(scored)
    }

    /// FTS5 keyword search. The query string is sanitized to remove FTS5
    /// special chars and joined with `OR` (matches Swift behavior).
    fn search_keywords(&self, query: &str, limit: usize) -> Result<Vec<StagedTask>> {
        let cleaned = sanitize_fts(query);
        if cleaned.is_empty() {
            return Ok(vec![]);
        }
        let conn = self.conn.lock().expect("staged_tasks db poisoned");
        let mut stmt = conn.prepare(
            "SELECT t.id, t.description, t.priority, t.tags_json, t.due_at, t.confidence,
                    t.source_app, t.window_title, t.context_summary, t.current_activity,
                    t.metadata_json, t.relevance_score, t.screenshot_id,
                    t.created_at, t.updated_at, t.backend_id, t.deleted, t.completed
             FROM staged_tasks_fts f
             JOIN staged_tasks t ON t.id = f.id
             WHERE f.description MATCH ?1 AND t.deleted = 0
             ORDER BY rank
             LIMIT ?2",
        )?;
        let rows = stmt
            .query_map(params![cleaned, limit as i64], map_row)?
            .collect::<Result<Vec<_>>>()?;
        Ok(rows)
    }

    fn insert_dedup_log(&self, input: DedupLogInput) -> Result<()> {
        let conn = self.conn.lock().expect("staged_tasks db poisoned");
        conn.execute(
            "INSERT INTO dedup_logs (id, kept_id, deleted_ids_json, reason, created_at)
             VALUES (?1, ?2, ?3, ?4, ?5)",
            params![
                uuid::Uuid::new_v4().to_string(),
                input.kept_id,
                serde_json::to_string(&input.deleted_ids).unwrap_or_else(|_| "[]".into()),
                input.reason,
                Self::now(),
            ],
        )?;
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

fn map_row(row: &rusqlite::Row<'_>) -> Result<StagedTask> {
    Ok(StagedTask {
        id: row.get(0)?,
        description: row.get(1)?,
        priority: row.get(2)?,
        tags_json: row.get(3)?,
        due_at: row.get(4)?,
        confidence: row.get(5)?,
        source_app: row.get(6)?,
        window_title: row.get(7)?,
        context_summary: row.get(8)?,
        current_activity: row.get(9)?,
        metadata_json: row.get(10)?,
        relevance_score: row.get(11)?,
        screenshot_id: row.get(12)?,
        created_at: row.get(13)?,
        updated_at: row.get(14)?,
        backend_id: row.get(15)?,
        deleted: row.get::<_, i64>(16)? != 0,
        completed: row.get::<_, i64>(17)? != 0,
    })
}

fn parse_embedding(blob: &[u8]) -> Option<Vec<f32>> {
    if blob.len() % 4 != 0 {
        return None;
    }
    Some(
        blob.chunks_exact(4)
            .map(|c| f32::from_le_bytes([c[0], c[1], c[2], c[3]]))
            .collect(),
    )
}

fn dot(a: &[f32], b: &[f32]) -> f32 {
    a.iter().zip(b.iter()).map(|(x, y)| x * y).sum()
}

/// Strip FTS5 special chars and join tokens with OR. Matches Swift's
/// `executeKeywordSearch` behavior (`TaskAssistant.swift`).
fn sanitize_fts(query: &str) -> String {
    let bad: &[char] = &['"', '\'', '(', ')', '*', '^', ':', '-', '+', '\\', '/'];
    let cleaned: String = query
        .chars()
        .map(|c| if bad.contains(&c) { ' ' } else { c })
        .collect();
    cleaned
        .split_whitespace()
        .filter(|t| t.len() >= 2)
        .map(|t| format!("{}*", t))
        .collect::<Vec<_>>()
        .join(" OR ")
}

// ---------------------------------------------------------------------------
// Tauri commands
// ---------------------------------------------------------------------------

type DbState<'a> = State<'a, StagedTasksDb>;

#[command]
pub fn upsert_staged_task(db: DbState<'_>, input: StagedTaskInput) -> Result<StagedTask, String> {
    db.upsert(input).map_err(|e| e.to_string())
}

#[command]
pub fn get_staged_tasks(db: DbState<'_>, limit: Option<usize>) -> Result<Vec<StagedTask>, String> {
    db.list_active(limit.unwrap_or(200)).map_err(|e| e.to_string())
}

#[command]
pub fn get_recent_staged_tasks(
    db: DbState<'_>,
    hours: Option<i64>,
    limit: Option<usize>,
) -> Result<Vec<StagedTask>, String> {
    db.list_recent_for_prompt(hours.unwrap_or(48), limit.unwrap_or(50))
        .map_err(|e| e.to_string())
}

#[command]
pub fn delete_staged_task(db: DbState<'_>, id: String, hard: Option<bool>) -> Result<(), String> {
    db.delete(&id, hard.unwrap_or(false)).map_err(|e| e.to_string())
}

#[command]
pub fn set_staged_task_completed(
    db: DbState<'_>,
    id: String,
    completed: bool,
) -> Result<(), String> {
    db.set_completed(&id, completed).map_err(|e| e.to_string())
}

#[command]
pub fn set_staged_task_backend_id(
    db: DbState<'_>,
    id: String,
    backend_id: String,
) -> Result<(), String> {
    db.set_backend_id(&id, &backend_id).map_err(|e| e.to_string())
}

#[command]
pub fn save_staged_task_embedding(
    db: DbState<'_>,
    id: String,
    embedding: Vec<f32>,
) -> Result<(), String> {
    db.save_embedding(&id, &embedding).map_err(|e| e.to_string())
}

#[command]
pub fn items_missing_embeddings(
    db: DbState<'_>,
    limit: Option<usize>,
) -> Result<Vec<EmbeddingBacklogItem>, String> {
    db.items_missing_embeddings(limit.unwrap_or(100))
        .map_err(|e| e.to_string())
}

#[command]
pub fn search_similar_staged_tasks(
    db: DbState<'_>,
    query_embedding: Vec<f32>,
    top_k: Option<usize>,
    min_similarity: Option<f32>,
) -> Result<Vec<SimilarTask>, String> {
    db.search_similar(
        &query_embedding,
        top_k.unwrap_or(10),
        min_similarity.unwrap_or(0.3),
    )
    .map_err(|e| e.to_string())
}

#[command]
pub fn search_keywords_staged_tasks(
    db: DbState<'_>,
    query: String,
    limit: Option<usize>,
) -> Result<Vec<StagedTask>, String> {
    db.search_keywords(&query, limit.unwrap_or(10))
        .map_err(|e| e.to_string())
}

#[command]
pub fn insert_dedup_log(db: DbState<'_>, input: DedupLogInput) -> Result<(), String> {
    db.insert_dedup_log(input).map_err(|e| e.to_string())
}

// ---------------------------------------------------------------------------
// Setup helper — call from `main.rs::setup`
// ---------------------------------------------------------------------------

pub fn init_and_manage(app: &AppHandle) -> Result<(), String> {
    let dir = app
        .path()
        .app_data_dir()
        .map_err(|e| format!("app_data_dir: {}", e))?;
    let db = StagedTasksDb::init(&dir).map_err(|e| format!("staged_tasks db init: {}", e))?;
    app.manage(db);
    Ok(())
}

// ---------------------------------------------------------------------------
// Schema
// ---------------------------------------------------------------------------

const MIGRATION_V1: &str = r#"
CREATE TABLE IF NOT EXISTS staged_tasks (
    id TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    priority TEXT,
    tags_json TEXT,
    due_at TEXT,
    confidence REAL,
    source_app TEXT,
    window_title TEXT,
    context_summary TEXT,
    current_activity TEXT,
    metadata_json TEXT,
    relevance_score REAL,
    screenshot_id INTEGER,
    embedding BLOB,
    backend_id TEXT,
    deleted INTEGER NOT NULL DEFAULT 0,
    completed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_staged_tasks_created
    ON staged_tasks(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_staged_tasks_active
    ON staged_tasks(deleted, created_at DESC);

CREATE VIRTUAL TABLE IF NOT EXISTS staged_tasks_fts
    USING fts5(id UNINDEXED, description, tokenize = 'porter unicode61');

CREATE TABLE IF NOT EXISTS dedup_logs (
    id TEXT PRIMARY KEY,
    kept_id TEXT NOT NULL,
    deleted_ids_json TEXT NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL
);
"#;
