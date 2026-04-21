//! Local SQLite store for goals (Swift parity).
//!
//! Ports `desktop/Desktop/Sources/Rewind/Core/GoalStorage.swift` and
//! `GoalRecord.swift`. Two tables:
//!
//! - `goals` — one row per goal, mirrors the backend `Goal` shape plus local
//!   sync bookkeeping (`backend_synced`, `deleted`) and a `source` column
//!   (`user` / `ai` / `onboarding_step_flow`) that the backend doesn't
//!   currently persist. Source is needed locally so `goalGenerationService`
//!   can auto-remove stale AI goals without touching user-created ones.
//! - `goal_progress_history` — one row per progress update, keyed by
//!   `(goal_id, date)`. Matches Swift's per-day history granularity.
//!
//! The crown jewel is `sync_server_goals`: upsert every goal from the server
//! response, then mark any local synced-and-still-active goal absent from the
//! response as deleted. Unsynced local goals (newly created offline) are
//! never touched. This is the reconciliation rule that keeps multi-device
//! deletion consistent.

use std::path::Path;
use std::sync::Mutex;

use chrono::Utc;
use rusqlite::{params, Connection, OptionalExtension, Result};
use serde::{Deserialize, Serialize};
use tauri::{command, AppHandle, Manager, State};

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Goal {
    pub id: String,
    pub title: String,
    pub description: Option<String>,
    pub goal_type: String, // "boolean" | "scale" | "numeric"
    pub target_value: f64,
    pub current_value: f64,
    pub min_value: f64,
    pub max_value: f64,
    pub unit: Option<String>,
    pub is_active: bool,
    pub completed_at: Option<String>,
    pub source: Option<String>,
    pub backend_id: Option<String>,
    pub backend_synced: bool,
    pub deleted: bool,
    pub created_at: String,
    pub updated_at: String,
}

/// Input for `upsert_goal`. `id` may be omitted for new local-only goals
/// (in which case we mint `local_{uuid}` to stay compatible with the Swift
/// convention).
#[derive(Debug, Clone, Deserialize)]
pub struct GoalInput {
    pub id: Option<String>,
    pub title: String,
    pub description: Option<String>,
    pub goal_type: String,
    pub target_value: f64,
    pub current_value: f64,
    pub min_value: f64,
    pub max_value: f64,
    pub unit: Option<String>,
    pub is_active: bool,
    pub completed_at: Option<String>,
    pub source: Option<String>,
    pub backend_id: Option<String>,
    pub backend_synced: Option<bool>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GoalHistoryEntry {
    pub date: String,      // YYYY-MM-DD
    pub value: f64,
    pub recorded_at: String,
}

// ---------------------------------------------------------------------------
// Storage
// ---------------------------------------------------------------------------

pub struct GoalsDb {
    conn: Mutex<Connection>,
}

impl GoalsDb {
    pub fn init(app_data_dir: &Path) -> Result<Self> {
        let dir = app_data_dir.join("proactive");
        std::fs::create_dir_all(&dir).map_err(|e| {
            rusqlite::Error::SqliteFailure(
                rusqlite::ffi::Error::new(rusqlite::ffi::SQLITE_CANTOPEN),
                Some(format!("create proactive dir: {}", e)),
            )
        })?;

        let db_path = dir.join("goals.db");
        tracing::info!("Opening goals database at {:?}", db_path);

        let conn = Connection::open(&db_path)?;
        let _mode: String = conn.query_row("PRAGMA journal_mode=WAL", [], |row| row.get(0))?;
        conn.execute_batch("PRAGMA foreign_keys = ON;")?;
        conn.execute_batch(MIGRATION_V1)?;

        Ok(Self { conn: Mutex::new(conn) })
    }

    fn now() -> String {
        Utc::now().to_rfc3339()
    }

    fn upsert(&self, input: GoalInput) -> Result<Goal> {
        let id = input.id.unwrap_or_else(|| format!("local_{}", uuid::Uuid::new_v4()));
        let now = Self::now();
        let backend_synced = input.backend_synced.unwrap_or(false);

        let conn = self.conn.lock().expect("goals db poisoned");

        conn.execute(
            r#"
            INSERT INTO goals (
                id, title, description, goal_type,
                target_value, current_value, min_value, max_value, unit,
                is_active, completed_at, source,
                backend_id, backend_synced, deleted,
                created_at, updated_at
            ) VALUES (
                ?1, ?2, ?3, ?4,
                ?5, ?6, ?7, ?8, ?9,
                ?10, ?11, ?12,
                ?13, ?14, 0,
                ?15, ?15
            )
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                description = excluded.description,
                goal_type = excluded.goal_type,
                target_value = excluded.target_value,
                current_value = excluded.current_value,
                min_value = excluded.min_value,
                max_value = excluded.max_value,
                unit = excluded.unit,
                is_active = excluded.is_active,
                completed_at = excluded.completed_at,
                source = COALESCE(excluded.source, goals.source),
                backend_id = COALESCE(excluded.backend_id, goals.backend_id),
                backend_synced = excluded.backend_synced,
                updated_at = excluded.updated_at
            "#,
            params![
                id,
                input.title,
                input.description,
                input.goal_type,
                input.target_value,
                input.current_value,
                input.min_value,
                input.max_value,
                input.unit,
                input.is_active as i32,
                input.completed_at,
                input.source,
                input.backend_id,
                backend_synced as i32,
                now,
            ],
        )?;

        drop(conn);
        self.get_by_id(&id)?
            .ok_or_else(|| rusqlite::Error::QueryReturnedNoRows)
    }

    fn get_by_id(&self, id: &str) -> Result<Option<Goal>> {
        let conn = self.conn.lock().expect("goals db poisoned");
        conn.query_row(SELECT_COLS, params![id], map_row).optional()
    }

    fn list_active(&self) -> Result<Vec<Goal>> {
        let conn = self.conn.lock().expect("goals db poisoned");
        let mut stmt = conn.prepare(
            "SELECT id, title, description, goal_type, target_value, current_value,
                    min_value, max_value, unit, is_active, completed_at, source,
                    backend_id, backend_synced, deleted, created_at, updated_at
             FROM goals
             WHERE deleted = 0 AND is_active = 1
             ORDER BY datetime(created_at) ASC",
        )?;
        let rows = stmt.query_map([], map_row)?.collect::<Result<Vec<_>>>()?;
        Ok(rows)
    }

    fn list_completed(&self, limit: usize) -> Result<Vec<Goal>> {
        let conn = self.conn.lock().expect("goals db poisoned");
        let mut stmt = conn.prepare(
            "SELECT id, title, description, goal_type, target_value, current_value,
                    min_value, max_value, unit, is_active, completed_at, source,
                    backend_id, backend_synced, deleted, created_at, updated_at
             FROM goals
             WHERE is_active = 0 AND completed_at IS NOT NULL
             ORDER BY datetime(completed_at) DESC
             LIMIT ?1",
        )?;
        let rows = stmt
            .query_map(params![limit as i64], map_row)?
            .collect::<Result<Vec<_>>>()?;
        Ok(rows)
    }

    fn list_unsynced(&self) -> Result<Vec<Goal>> {
        let conn = self.conn.lock().expect("goals db poisoned");
        let mut stmt = conn.prepare(
            "SELECT id, title, description, goal_type, target_value, current_value,
                    min_value, max_value, unit, is_active, completed_at, source,
                    backend_id, backend_synced, deleted, created_at, updated_at
             FROM goals
             WHERE backend_synced = 0 AND deleted = 0
             ORDER BY datetime(created_at) ASC",
        )?;
        let rows = stmt.query_map([], map_row)?.collect::<Result<Vec<_>>>()?;
        Ok(rows)
    }

    fn update_progress(&self, id: &str, current_value: f64) -> Result<()> {
        let conn = self.conn.lock().expect("goals db poisoned");
        conn.execute(
            "UPDATE goals SET current_value = ?2, updated_at = ?3 WHERE id = ?1",
            params![id, current_value, Self::now()],
        )?;
        Ok(())
    }

    fn soft_delete(&self, id: &str) -> Result<()> {
        let conn = self.conn.lock().expect("goals db poisoned");
        conn.execute(
            "UPDATE goals SET deleted = 1, is_active = 0, updated_at = ?2 WHERE id = ?1",
            params![id, Self::now()],
        )?;
        Ok(())
    }

    fn mark_completed(&self, id: &str) -> Result<()> {
        let conn = self.conn.lock().expect("goals db poisoned");
        let now = Self::now();
        conn.execute(
            "UPDATE goals SET is_active = 0, completed_at = ?2, updated_at = ?2 WHERE id = ?1",
            params![id, now],
        )?;
        Ok(())
    }

    fn mark_synced(&self, id: &str, backend_id: &str) -> Result<()> {
        let conn = self.conn.lock().expect("goals db poisoned");
        conn.execute(
            "UPDATE goals SET backend_id = ?2, backend_synced = 1, updated_at = ?3 WHERE id = ?1",
            params![id, backend_id, Self::now()],
        )?;
        Ok(())
    }

    /// Ports Swift `GoalStorage.syncServerGoals` (lines 82–127).
    ///
    /// 1. Upsert every goal from the server into local (by `backend_id`).
    /// 2. Reconcile: any synced-and-still-active local goal absent from the
    ///    server response is marked deleted locally. Leaves unsynced locals
    ///    alone so offline-created goals survive until they sync.
    fn sync_server_goals(&self, goals: Vec<GoalInput>) -> Result<()> {
        let mut conn = self.conn.lock().expect("goals db poisoned");
        let tx = conn.transaction()?;

        let mut server_backend_ids: Vec<String> = Vec::with_capacity(goals.len());

        for g in goals {
            let bid = g.backend_id.clone().unwrap_or_default();
            if bid.is_empty() {
                continue;
            }
            server_backend_ids.push(bid.clone());

            // Try to match an existing local row by backend_id; otherwise insert.
            let existing_id: Option<String> = tx
                .query_row(
                    "SELECT id FROM goals WHERE backend_id = ?1",
                    params![bid],
                    |row| row.get::<_, String>(0),
                )
                .optional()?;

            let now = Self::now();
            match existing_id {
                Some(local_id) => {
                    tx.execute(
                        r#"
                        UPDATE goals SET
                            title = ?2,
                            description = ?3,
                            goal_type = ?4,
                            target_value = ?5,
                            current_value = ?6,
                            min_value = ?7,
                            max_value = ?8,
                            unit = ?9,
                            is_active = ?10,
                            completed_at = ?11,
                            source = COALESCE(?12, source),
                            backend_synced = 1,
                            deleted = 0,
                            updated_at = ?13
                        WHERE id = ?1
                        "#,
                        params![
                            local_id,
                            g.title,
                            g.description,
                            g.goal_type,
                            g.target_value,
                            g.current_value,
                            g.min_value,
                            g.max_value,
                            g.unit,
                            g.is_active as i32,
                            g.completed_at,
                            g.source,
                            now,
                        ],
                    )?;
                }
                None => {
                    tx.execute(
                        r#"
                        INSERT INTO goals (
                            id, title, description, goal_type,
                            target_value, current_value, min_value, max_value, unit,
                            is_active, completed_at, source,
                            backend_id, backend_synced, deleted,
                            created_at, updated_at
                        ) VALUES (
                            ?1, ?2, ?3, ?4,
                            ?5, ?6, ?7, ?8, ?9,
                            ?10, ?11, ?12,
                            ?13, 1, 0,
                            ?14, ?14
                        )
                        "#,
                        params![
                            bid,
                            g.title,
                            g.description,
                            g.goal_type,
                            g.target_value,
                            g.current_value,
                            g.min_value,
                            g.max_value,
                            g.unit,
                            g.is_active as i32,
                            g.completed_at,
                            g.source,
                            bid,
                            now,
                        ],
                    )?;
                }
            }
        }

        // Reconcile: mark synced+active locals absent from server as deleted.
        // Build a prepared query that filters out server-present IDs. Using
        // execute_batch-style NOT IN is safe here since the list is small.
        let placeholders = server_backend_ids
            .iter()
            .map(|_| "?")
            .collect::<Vec<_>>()
            .join(",");
        let now = Self::now();

        if server_backend_ids.is_empty() {
            tx.execute(
                "UPDATE goals SET is_active = 0, deleted = 1, updated_at = ?1
                 WHERE backend_synced = 1 AND deleted = 0 AND is_active = 1",
                params![now],
            )?;
        } else {
            let sql = format!(
                "UPDATE goals SET is_active = 0, deleted = 1, updated_at = ?
                 WHERE backend_synced = 1 AND deleted = 0 AND is_active = 1
                   AND backend_id NOT IN ({})",
                placeholders
            );
            let mut stmt = tx.prepare(&sql)?;
            let mut bindings: Vec<&dyn rusqlite::ToSql> = vec![&now];
            for bid in server_backend_ids.iter() {
                bindings.push(bid);
            }
            stmt.execute(rusqlite::params_from_iter(bindings.iter().copied()))?;
        }

        tx.commit()?;
        Ok(())
    }

    fn insert_progress_history(
        &self,
        goal_id: &str,
        value: f64,
    ) -> Result<GoalHistoryEntry> {
        let now = Self::now();
        let date = now.get(..10).unwrap_or(&now).to_string();

        let conn = self.conn.lock().expect("goals db poisoned");
        conn.execute(
            r#"
            INSERT INTO goal_progress_history (goal_id, date, value, recorded_at)
            VALUES (?1, ?2, ?3, ?4)
            ON CONFLICT(goal_id, date) DO UPDATE SET
                value = excluded.value,
                recorded_at = excluded.recorded_at
            "#,
            params![goal_id, date, value, now],
        )?;

        Ok(GoalHistoryEntry { date, value, recorded_at: now })
    }

    fn get_progress_history(
        &self,
        goal_id: &str,
        days: i64,
    ) -> Result<Vec<GoalHistoryEntry>> {
        let cutoff = Utc::now() - chrono::Duration::days(days);
        let cutoff_date = cutoff.format("%Y-%m-%d").to_string();

        let conn = self.conn.lock().expect("goals db poisoned");
        let mut stmt = conn.prepare(
            "SELECT date, value, recorded_at FROM goal_progress_history
             WHERE goal_id = ?1 AND date >= ?2
             ORDER BY date DESC",
        )?;
        let rows = stmt
            .query_map(params![goal_id, cutoff_date], |row| {
                Ok(GoalHistoryEntry {
                    date: row.get(0)?,
                    value: row.get(1)?,
                    recorded_at: row.get(2)?,
                })
            })?
            .collect::<Result<Vec<_>>>()?;
        Ok(rows)
    }

    fn clear_all(&self) -> Result<()> {
        let conn = self.conn.lock().expect("goals db poisoned");
        conn.execute("DELETE FROM goal_progress_history", [])?;
        conn.execute("DELETE FROM goals", [])?;
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const SELECT_COLS: &str =
    "SELECT id, title, description, goal_type, target_value, current_value,
            min_value, max_value, unit, is_active, completed_at, source,
            backend_id, backend_synced, deleted, created_at, updated_at
     FROM goals WHERE id = ?1";

fn map_row(row: &rusqlite::Row<'_>) -> Result<Goal> {
    Ok(Goal {
        id: row.get(0)?,
        title: row.get(1)?,
        description: row.get(2)?,
        goal_type: row.get(3)?,
        target_value: row.get(4)?,
        current_value: row.get(5)?,
        min_value: row.get(6)?,
        max_value: row.get(7)?,
        unit: row.get(8)?,
        is_active: row.get::<_, i64>(9)? != 0,
        completed_at: row.get(10)?,
        source: row.get(11)?,
        backend_id: row.get(12)?,
        backend_synced: row.get::<_, i64>(13)? != 0,
        deleted: row.get::<_, i64>(14)? != 0,
        created_at: row.get(15)?,
        updated_at: row.get(16)?,
    })
}

// ---------------------------------------------------------------------------
// Tauri commands
// ---------------------------------------------------------------------------

type DbState<'a> = State<'a, GoalsDb>;

#[command]
pub fn upsert_goal(db: DbState<'_>, input: GoalInput) -> Result<Goal, String> {
    db.upsert(input).map_err(|e| e.to_string())
}

#[command]
pub fn get_goals(db: DbState<'_>) -> Result<Vec<Goal>, String> {
    db.list_active().map_err(|e| e.to_string())
}

#[command]
pub fn get_completed_goals(
    db: DbState<'_>,
    limit: Option<usize>,
) -> Result<Vec<Goal>, String> {
    db.list_completed(limit.unwrap_or(100)).map_err(|e| e.to_string())
}

#[command]
pub fn get_unsynced_goals(db: DbState<'_>) -> Result<Vec<Goal>, String> {
    db.list_unsynced().map_err(|e| e.to_string())
}

#[command]
pub fn update_goal_progress(
    db: DbState<'_>,
    id: String,
    current_value: f64,
) -> Result<(), String> {
    db.update_progress(&id, current_value).map_err(|e| e.to_string())
}

#[command]
pub fn soft_delete_goal(db: DbState<'_>, id: String) -> Result<(), String> {
    db.soft_delete(&id).map_err(|e| e.to_string())
}

#[command]
pub fn mark_goal_completed(db: DbState<'_>, id: String) -> Result<(), String> {
    db.mark_completed(&id).map_err(|e| e.to_string())
}

#[command]
pub fn mark_goal_synced(
    db: DbState<'_>,
    id: String,
    backend_id: String,
) -> Result<(), String> {
    db.mark_synced(&id, &backend_id).map_err(|e| e.to_string())
}

#[command]
pub fn sync_server_goals(db: DbState<'_>, goals: Vec<GoalInput>) -> Result<(), String> {
    db.sync_server_goals(goals).map_err(|e| e.to_string())
}

#[command]
pub fn insert_goal_progress_history(
    db: DbState<'_>,
    goal_id: String,
    value: f64,
) -> Result<GoalHistoryEntry, String> {
    db.insert_progress_history(&goal_id, value)
        .map_err(|e| e.to_string())
}

#[command]
pub fn get_goal_progress_history(
    db: DbState<'_>,
    goal_id: String,
    days: Option<i64>,
) -> Result<Vec<GoalHistoryEntry>, String> {
    db.get_progress_history(&goal_id, days.unwrap_or(30))
        .map_err(|e| e.to_string())
}

#[command]
pub fn clear_goals_db(db: DbState<'_>) -> Result<(), String> {
    db.clear_all().map_err(|e| e.to_string())
}

// ---------------------------------------------------------------------------
// Setup helper — call from `main.rs::setup`
// ---------------------------------------------------------------------------

pub fn init_and_manage(app: &AppHandle) -> Result<(), String> {
    let dir = app
        .path()
        .app_data_dir()
        .map_err(|e| format!("app_data_dir: {}", e))?;
    let db = GoalsDb::init(&dir).map_err(|e| format!("goals db init: {}", e))?;
    app.manage(db);
    Ok(())
}

// ---------------------------------------------------------------------------
// Schema
// ---------------------------------------------------------------------------

const MIGRATION_V1: &str = r#"
CREATE TABLE IF NOT EXISTS goals (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    goal_type TEXT NOT NULL DEFAULT 'scale',
    target_value REAL NOT NULL DEFAULT 1.0,
    current_value REAL NOT NULL DEFAULT 0.0,
    min_value REAL NOT NULL DEFAULT 0.0,
    max_value REAL NOT NULL DEFAULT 10.0,
    unit TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    completed_at TEXT,
    source TEXT,
    backend_id TEXT,
    backend_synced INTEGER NOT NULL DEFAULT 0,
    deleted INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_goals_active
    ON goals(deleted, is_active, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_goals_backend_id
    ON goals(backend_id);
CREATE INDEX IF NOT EXISTS idx_goals_completed_at
    ON goals(completed_at DESC);

CREATE TABLE IF NOT EXISTS goal_progress_history (
    goal_id TEXT NOT NULL,
    date TEXT NOT NULL,
    value REAL NOT NULL,
    recorded_at TEXT NOT NULL,
    PRIMARY KEY (goal_id, date),
    FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_goal_history_goal_date
    ON goal_progress_history(goal_id, date DESC);
"#;
