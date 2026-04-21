//! Local SQLite store for AI-extracted memories (MemoryAssistant parity with Swift).
//!
//! Mirrors the Swift `MemoryStorage` under
//! `desktop/Desktop/Sources/Rewind/Core/`. Schema lives in its own DB file at
//! `{app_data_dir}/proactive/memories.db`, separate from `staged_tasks.db`.
//!
//! Commands are exposed as `#[tauri::command]` and called from
//! `services/memoryAssistant.ts` via `invoke()`.

use std::path::Path;
use std::sync::Mutex;

use chrono::Utc;
use rusqlite::{params, Connection, OptionalExtension, Result};
use serde::{Deserialize, Serialize};
use tauri::{command, AppHandle, Manager, State};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Memory {
    pub id: String,
    pub content: String,
    pub category: String,
    pub visibility: Option<String>,
    pub confidence: Option<f64>,
    pub source_app: Option<String>,
    pub window_title: Option<String>,
    pub context_summary: Option<String>,
    pub current_activity: Option<String>,
    pub headline: Option<String>,
    pub reasoning: Option<String>,
    pub tags_json: Option<String>,
    pub screenshot_id: Option<i64>,
    pub backend_id: Option<String>,
    pub backend_synced: bool,
    pub is_dismissed: bool,
    pub deleted: bool,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct MemoryInput {
    pub id: Option<String>,
    pub content: String,
    pub category: String,
    pub visibility: Option<String>,
    pub confidence: Option<f64>,
    pub source_app: Option<String>,
    pub window_title: Option<String>,
    pub context_summary: Option<String>,
    pub current_activity: Option<String>,
    pub headline: Option<String>,
    pub reasoning: Option<String>,
    pub tags_json: Option<String>,
    pub screenshot_id: Option<i64>,
}

pub struct MemoriesDb {
    conn: Mutex<Connection>,
}

impl MemoriesDb {
    pub fn init(app_data_dir: &Path) -> Result<Self> {
        let dir = app_data_dir.join("proactive");
        std::fs::create_dir_all(&dir).map_err(|e| {
            rusqlite::Error::SqliteFailure(
                rusqlite::ffi::Error::new(rusqlite::ffi::SQLITE_CANTOPEN),
                Some(format!("create proactive dir: {}", e)),
            )
        })?;

        let db_path = dir.join("memories.db");
        tracing::info!("Opening memories database at {:?}", db_path);

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

    fn insert(&self, input: MemoryInput) -> Result<String> {
        let id = input.id.unwrap_or_else(|| uuid::Uuid::new_v4().to_string());
        let now = Self::now();
        let visibility = input.visibility.unwrap_or_else(|| "private".to_string());

        let conn = self.conn.lock().expect("memories db poisoned");
        conn.execute(
            r#"
            INSERT INTO memories (
                id, content, category, visibility, confidence,
                source_app, window_title, context_summary, current_activity,
                headline, reasoning, tags_json, screenshot_id,
                backend_id, backend_synced, is_dismissed, deleted,
                created_at, updated_at
            ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, NULL, 0, 0, 0, ?14, ?15)
            "#,
            params![
                id,
                input.content,
                input.category,
                visibility,
                input.confidence,
                input.source_app,
                input.window_title,
                input.context_summary,
                input.current_activity,
                input.headline,
                input.reasoning,
                input.tags_json,
                input.screenshot_id,
                now,
                now,
            ],
        )?;
        Ok(id)
    }

    fn list(&self, limit: i64) -> Result<Vec<Memory>> {
        let conn = self.conn.lock().expect("memories db poisoned");
        let mut stmt = conn.prepare(
            "SELECT id, content, category, visibility, confidence,
                    source_app, window_title, context_summary, current_activity,
                    headline, reasoning, tags_json, screenshot_id,
                    backend_id, backend_synced, is_dismissed, deleted,
                    created_at, updated_at
             FROM memories
             WHERE deleted = 0 AND is_dismissed = 0
             ORDER BY datetime(created_at) DESC
             LIMIT ?1",
        )?;
        let rows = stmt
            .query_map(params![limit], map_row)?
            .collect::<Result<Vec<_>>>()?;
        Ok(rows)
    }

    fn list_by_tag(&self, tag: &str, limit: i64) -> Result<Vec<Memory>> {
        let conn = self.conn.lock().expect("memories db poisoned");
        let mut stmt = conn.prepare(
            "SELECT id, content, category, visibility, confidence,
                    source_app, window_title, context_summary, current_activity,
                    headline, reasoning, tags_json, screenshot_id,
                    backend_id, backend_synced, is_dismissed, deleted,
                    created_at, updated_at
             FROM memories
             WHERE tags_json LIKE '%\"' || ?1 || '\"%' AND deleted = 0
             ORDER BY datetime(created_at) DESC
             LIMIT ?2",
        )?;
        let rows = stmt
            .query_map(params![tag, limit], map_row)?
            .collect::<Result<Vec<_>>>()?;
        Ok(rows)
    }

    fn get_by_id(&self, id: &str) -> Result<Option<Memory>> {
        let conn = self.conn.lock().expect("memories db poisoned");
        conn.query_row(
            "SELECT id, content, category, visibility, confidence,
                    source_app, window_title, context_summary, current_activity,
                    headline, reasoning, tags_json, screenshot_id,
                    backend_id, backend_synced, is_dismissed, deleted,
                    created_at, updated_at
             FROM memories WHERE id = ?1",
            params![id],
            map_row,
        )
        .optional()
    }

    fn set_backend_id(&self, id: &str, backend_id: &str) -> Result<()> {
        let conn = self.conn.lock().expect("memories db poisoned");
        conn.execute(
            "UPDATE memories SET backend_id = ?2, backend_synced = 1, updated_at = ?3 WHERE id = ?1",
            params![id, backend_id, Self::now()],
        )?;
        Ok(())
    }

    fn dismiss(&self, id: &str) -> Result<()> {
        let conn = self.conn.lock().expect("memories db poisoned");
        conn.execute(
            "UPDATE memories SET is_dismissed = 1, updated_at = ?2 WHERE id = ?1",
            params![id, Self::now()],
        )?;
        Ok(())
    }

    fn delete(&self, id: &str, hard: bool) -> Result<()> {
        let conn = self.conn.lock().expect("memories db poisoned");
        if hard {
            conn.execute("DELETE FROM memories WHERE id = ?1", params![id])?;
        } else {
            conn.execute(
                "UPDATE memories SET deleted = 1, updated_at = ?2 WHERE id = ?1",
                params![id, Self::now()],
            )?;
        }
        Ok(())
    }
}

fn map_row(row: &rusqlite::Row<'_>) -> Result<Memory> {
    Ok(Memory {
        id: row.get(0)?,
        content: row.get(1)?,
        category: row.get(2)?,
        visibility: row.get(3)?,
        confidence: row.get(4)?,
        source_app: row.get(5)?,
        window_title: row.get(6)?,
        context_summary: row.get(7)?,
        current_activity: row.get(8)?,
        headline: row.get(9)?,
        reasoning: row.get(10)?,
        tags_json: row.get(11)?,
        screenshot_id: row.get(12)?,
        backend_id: row.get(13)?,
        backend_synced: row.get::<_, i64>(14)? != 0,
        is_dismissed: row.get::<_, i64>(15)? != 0,
        deleted: row.get::<_, i64>(16)? != 0,
        created_at: row.get(17)?,
        updated_at: row.get(18)?,
    })
}

type DbState<'a> = State<'a, MemoriesDb>;

#[command]
pub fn insert_memory(db: DbState<'_>, input: MemoryInput) -> Result<String, String> {
    db.insert(input).map_err(|e| e.to_string())
}

#[command]
pub fn get_memories(db: DbState<'_>, limit: Option<i64>) -> Result<Vec<Memory>, String> {
    db.list(limit.unwrap_or(200)).map_err(|e| e.to_string())
}

#[command]
pub fn get_memories_by_tag(
    db: DbState<'_>,
    tag: String,
    limit: Option<i64>,
) -> Result<Vec<Memory>, String> {
    db.list_by_tag(&tag, limit.unwrap_or(50))
        .map_err(|e| e.to_string())
}

#[command]
pub fn get_memory_by_id(db: DbState<'_>, id: String) -> Result<Option<Memory>, String> {
    db.get_by_id(&id).map_err(|e| e.to_string())
}

#[command]
pub fn set_memory_backend_id(
    db: DbState<'_>,
    id: String,
    backend_id: String,
) -> Result<(), String> {
    db.set_backend_id(&id, &backend_id).map_err(|e| e.to_string())
}

#[command]
pub fn dismiss_memory(db: DbState<'_>, id: String) -> Result<(), String> {
    db.dismiss(&id).map_err(|e| e.to_string())
}

#[command]
pub fn delete_memory(db: DbState<'_>, id: String, hard: Option<bool>) -> Result<(), String> {
    db.delete(&id, hard.unwrap_or(false)).map_err(|e| e.to_string())
}

pub fn init_and_manage(app: &AppHandle) -> Result<(), String> {
    let dir = app
        .path()
        .app_data_dir()
        .map_err(|e| format!("app_data_dir: {}", e))?;
    let db = MemoriesDb::init(&dir).map_err(|e| format!("memories db init: {}", e))?;
    app.manage(db);
    Ok(())
}

const MIGRATION_V1: &str = r#"
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    category TEXT NOT NULL,
    visibility TEXT DEFAULT 'private',
    confidence REAL,
    source_app TEXT,
    window_title TEXT,
    context_summary TEXT,
    current_activity TEXT,
    headline TEXT,
    reasoning TEXT,
    tags_json TEXT,
    screenshot_id INTEGER,
    backend_id TEXT,
    backend_synced INTEGER NOT NULL DEFAULT 0,
    is_dismissed INTEGER NOT NULL DEFAULT 0,
    deleted INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memories_deleted ON memories(deleted);
"#;
