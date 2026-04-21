//! Local SQLite-backed persistence for transcription sessions.
//!
//! Mirrors `../tauri-plugin-screen-capture/src/database.rs` pattern: WAL
//! journal mode, v1 migration via `execute_batch`, one `Mutex<Connection>`.
//!
//! This is ground truth for the Swift-parity "persist-then-POST" flow — every
//! finalized segment is written here at the same moment it lands in the
//! in-memory Vec, so a crash / backend failure / stop-before-upload cannot
//! lose the meeting. The retry service (`retry.rs`) scans this DB and
//! reconciles with the backend.

use std::path::Path;
use std::sync::Mutex;

use chrono::Utc;
use rusqlite::{params, Connection, Result};

/// A recorded transcription session (one meeting = one row).
#[derive(Debug, Clone, serde::Serialize)]
pub struct LocalSession {
    pub id: i64,
    pub started_at: String,
    pub finished_at: Option<String>,
    pub source: String,
    pub language: String,
    pub timezone: String,
    pub input_device_name: Option<String>,
    pub status: String,
    pub backend_id: Option<String>,
    pub last_error: Option<String>,
    pub retry_count: i32,
    pub next_retry_at: Option<String>,
    pub created_at: String,
    pub updated_at: String,
}

/// A single finalized transcript segment attached to a session.
#[derive(Debug, Clone, serde::Serialize)]
pub struct LocalSegment {
    pub id: i64,
    pub session_id: i64,
    pub text: String,
    pub speaker: String,
    pub speaker_id: i64,
    pub is_user: bool,
    pub start_time: f64,
    pub end_time: f64,
    pub created_at: String,
}

/// SQLite-backed store for transcription sessions + segments.
pub struct TranscriptionStorage {
    conn: Mutex<Connection>,
}

impl TranscriptionStorage {
    /// Open (or create) the DB at `{app_data_dir}/transcription/transcription.db`.
    pub fn init(app_data_dir: &Path) -> Result<Self> {
        let dir = app_data_dir.join("transcription");
        std::fs::create_dir_all(&dir).map_err(|e| {
            rusqlite::Error::SqliteFailure(
                rusqlite::ffi::Error::new(rusqlite::ffi::SQLITE_CANTOPEN),
                Some(format!("Failed to create transcription dir: {}", e)),
            )
        })?;

        let db_path = dir.join("transcription.db");
        tracing::info!("Opening transcription database at {:?}", db_path);

        let conn = Connection::open(&db_path)?;

        // WAL journal mode — returns a row, so must use query_row.
        let _mode: String =
            conn.query_row("PRAGMA journal_mode=WAL", [], |row| row.get(0))?;
        tracing::info!("SQLite journal mode: {}", _mode);

        // Enable ON DELETE CASCADE.
        conn.execute_batch("PRAGMA foreign_keys = ON;")?;

        conn.execute_batch(MIGRATION_V1)?;

        tracing::info!("Transcription database ready");
        Ok(Self { conn: Mutex::new(conn) })
    }

    // -----------------------------------------------------------------
    // Mutations
    // -----------------------------------------------------------------

    /// Insert a new row in `recording` status and return its rowid.
    pub fn start_session(
        &self,
        source: &str,
        language: &str,
        timezone: &str,
        input_device_name: Option<&str>,
    ) -> Result<i64> {
        let now = Utc::now().to_rfc3339();
        let conn = self.conn.lock().expect("db mutex poisoned");
        conn.execute(
            "INSERT INTO transcription_sessions \
             (started_at, source, language, timezone, input_device_name, status, created_at, updated_at) \
             VALUES (?1, ?2, ?3, ?4, ?5, 'recording', ?6, ?6)",
            params![now, source, language, timezone, input_device_name, now],
        )?;
        Ok(conn.last_insert_rowid())
    }

    /// Append a finalized segment to a session.
    #[allow(clippy::too_many_arguments)]
    pub fn append_segment(
        &self,
        session_id: i64,
        text: &str,
        speaker: &str,
        speaker_id: i64,
        is_user: bool,
        start_time: f64,
        end_time: f64,
    ) -> Result<()> {
        let now = Utc::now().to_rfc3339();
        let conn = self.conn.lock().expect("db mutex poisoned");
        conn.execute(
            "INSERT INTO transcription_segments \
             (session_id, text, speaker, speaker_id, is_user, start_time, end_time, created_at) \
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)",
            params![
                session_id,
                text,
                speaker,
                speaker_id,
                if is_user { 1 } else { 0 },
                start_time,
                end_time,
                now,
            ],
        )?;
        Ok(())
    }

    /// Mark a session as finished — status moves to `pending_upload` so the
    /// retry service will pick it up on the next tick.
    pub fn finish_session(&self, session_id: i64) -> Result<()> {
        let now = Utc::now().to_rfc3339();
        let conn = self.conn.lock().expect("db mutex poisoned");
        conn.execute(
            "UPDATE transcription_sessions \
             SET finished_at = ?1, status = 'pending_upload', updated_at = ?1 \
             WHERE id = ?2",
            params![now, session_id],
        )?;
        Ok(())
    }

    /// Move a session into `uploading` state just before POSTing.
    pub fn mark_uploading(&self, session_id: i64) -> Result<()> {
        let now = Utc::now().to_rfc3339();
        let conn = self.conn.lock().expect("db mutex poisoned");
        conn.execute(
            "UPDATE transcription_sessions SET status = 'uploading', updated_at = ?1 WHERE id = ?2",
            params![now, session_id],
        )?;
        Ok(())
    }

    /// Record a successful upload.
    pub fn mark_completed(&self, session_id: i64, backend_id: &str) -> Result<()> {
        let now = Utc::now().to_rfc3339();
        let conn = self.conn.lock().expect("db mutex poisoned");
        conn.execute(
            "UPDATE transcription_sessions \
             SET status = 'completed', backend_id = ?1, last_error = NULL, updated_at = ?2 \
             WHERE id = ?3",
            params![backend_id, now, session_id],
        )?;
        Ok(())
    }

    /// Record a failed upload.
    pub fn mark_failed(&self, session_id: i64, error: &str) -> Result<()> {
        let now = Utc::now().to_rfc3339();
        let conn = self.conn.lock().expect("db mutex poisoned");
        conn.execute(
            "UPDATE transcription_sessions \
             SET status = 'failed', last_error = ?1, updated_at = ?2 \
             WHERE id = ?3",
            params![error, now, session_id],
        )?;
        Ok(())
    }

    /// Increment `retry_count` and set the next eligible retry time.
    pub fn increment_retry(&self, session_id: i64, next_retry_at_iso: &str) -> Result<()> {
        let now = Utc::now().to_rfc3339();
        let conn = self.conn.lock().expect("db mutex poisoned");
        conn.execute(
            "UPDATE transcription_sessions \
             SET retry_count = retry_count + 1, next_retry_at = ?1, updated_at = ?2 \
             WHERE id = ?3",
            params![next_retry_at_iso, now, session_id],
        )?;
        Ok(())
    }

    /// Delete a session (and cascade its segments).
    pub fn delete_session(&self, session_id: i64) -> Result<()> {
        let conn = self.conn.lock().expect("db mutex poisoned");
        conn.execute(
            "DELETE FROM transcription_sessions WHERE id = ?1",
            params![session_id],
        )?;
        Ok(())
    }

    // -----------------------------------------------------------------
    // Reads
    // -----------------------------------------------------------------

    /// All sessions, most recent first.
    pub fn list_sessions(&self) -> Result<Vec<LocalSession>> {
        let conn = self.conn.lock().expect("db mutex poisoned");
        let mut stmt = conn.prepare(
            "SELECT id, started_at, finished_at, source, language, timezone, \
                    input_device_name, status, backend_id, last_error, retry_count, \
                    next_retry_at, created_at, updated_at \
             FROM transcription_sessions ORDER BY started_at DESC",
        )?;
        let rows = stmt.query_map([], map_session)?;
        rows.collect()
    }

    /// All sessions with a specific status.
    pub fn list_by_status(&self, status: &str) -> Result<Vec<LocalSession>> {
        let conn = self.conn.lock().expect("db mutex poisoned");
        let mut stmt = conn.prepare(
            "SELECT id, started_at, finished_at, source, language, timezone, \
                    input_device_name, status, backend_id, last_error, retry_count, \
                    next_retry_at, created_at, updated_at \
             FROM transcription_sessions WHERE status = ?1 ORDER BY started_at ASC",
        )?;
        let rows = stmt.query_map(params![status], map_session)?;
        rows.collect()
    }

    /// Failed sessions that still have retry budget and whose backoff has
    /// elapsed (or has no backoff set yet).
    pub fn list_failed_ready(&self, max_retries: i32) -> Result<Vec<LocalSession>> {
        let now = Utc::now().to_rfc3339();
        let conn = self.conn.lock().expect("db mutex poisoned");
        let mut stmt = conn.prepare(
            "SELECT id, started_at, finished_at, source, language, timezone, \
                    input_device_name, status, backend_id, last_error, retry_count, \
                    next_retry_at, created_at, updated_at \
             FROM transcription_sessions \
             WHERE status = 'failed' \
               AND retry_count < ?1 \
               AND (next_retry_at IS NULL OR next_retry_at <= ?2) \
             ORDER BY started_at ASC",
        )?;
        let rows = stmt.query_map(params![max_retries, now], map_session)?;
        rows.collect()
    }

    /// All segments for a session, ordered by start_time then id.
    pub fn get_segments(&self, session_id: i64) -> Result<Vec<LocalSegment>> {
        let conn = self.conn.lock().expect("db mutex poisoned");
        let mut stmt = conn.prepare(
            "SELECT id, session_id, text, speaker, speaker_id, is_user, \
                    start_time, end_time, created_at \
             FROM transcription_segments \
             WHERE session_id = ?1 \
             ORDER BY start_time ASC, id ASC",
        )?;
        let rows = stmt.query_map(params![session_id], map_segment)?;
        rows.collect()
    }

    /// Fetch a single session by id.
    pub fn get_session(&self, session_id: i64) -> Result<Option<LocalSession>> {
        let conn = self.conn.lock().expect("db mutex poisoned");
        let mut stmt = conn.prepare(
            "SELECT id, started_at, finished_at, source, language, timezone, \
                    input_device_name, status, backend_id, last_error, retry_count, \
                    next_retry_at, created_at, updated_at \
             FROM transcription_sessions WHERE id = ?1",
        )?;
        let mut rows = stmt.query_map(params![session_id], map_session)?;
        rows.next().transpose()
    }

    /// Sessions that were still in `recording` when the app was killed.
    pub fn get_crashed_sessions(&self) -> Result<Vec<LocalSession>> {
        self.list_by_status("recording")
    }

    /// Sessions stuck in `uploading` with no progress for `older_than_secs`
    /// — likely killed mid-POST. Caller will push them back to
    /// `pending_upload` so they retry.
    pub fn get_stuck_uploading(&self, older_than_secs: i64) -> Result<Vec<LocalSession>> {
        let cutoff = (Utc::now() - chrono::Duration::seconds(older_than_secs)).to_rfc3339();
        let conn = self.conn.lock().expect("db mutex poisoned");
        let mut stmt = conn.prepare(
            "SELECT id, started_at, finished_at, source, language, timezone, \
                    input_device_name, status, backend_id, last_error, retry_count, \
                    next_retry_at, created_at, updated_at \
             FROM transcription_sessions \
             WHERE status = 'uploading' AND updated_at < ?1 \
             ORDER BY updated_at ASC",
        )?;
        let rows = stmt.query_map(params![cutoff], map_session)?;
        rows.collect()
    }

    /// Number of segments attached to a session.
    pub fn get_segment_count(&self, session_id: i64) -> Result<i64> {
        let conn = self.conn.lock().expect("db mutex poisoned");
        let count: i64 = conn.query_row(
            "SELECT COUNT(*) FROM transcription_segments WHERE session_id = ?1",
            params![session_id],
            |row| row.get(0),
        )?;
        Ok(count)
    }
}

// ---------------------------------------------------------------------------
// Row mappers
// ---------------------------------------------------------------------------

fn map_session(row: &rusqlite::Row<'_>) -> rusqlite::Result<LocalSession> {
    Ok(LocalSession {
        id: row.get(0)?,
        started_at: row.get(1)?,
        finished_at: row.get(2)?,
        source: row.get(3)?,
        language: row.get(4)?,
        timezone: row.get(5)?,
        input_device_name: row.get(6)?,
        status: row.get(7)?,
        backend_id: row.get(8)?,
        last_error: row.get(9)?,
        retry_count: row.get(10)?,
        next_retry_at: row.get(11)?,
        created_at: row.get(12)?,
        updated_at: row.get(13)?,
    })
}

fn map_segment(row: &rusqlite::Row<'_>) -> rusqlite::Result<LocalSegment> {
    let is_user_int: i64 = row.get(5)?;
    Ok(LocalSegment {
        id: row.get(0)?,
        session_id: row.get(1)?,
        text: row.get(2)?,
        speaker: row.get(3)?,
        speaker_id: row.get(4)?,
        is_user: is_user_int != 0,
        start_time: row.get(6)?,
        end_time: row.get(7)?,
        created_at: row.get(8)?,
    })
}

// ---------------------------------------------------------------------------
// Schema
// ---------------------------------------------------------------------------

const MIGRATION_V1: &str = "
CREATE TABLE IF NOT EXISTS transcription_sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  source TEXT NOT NULL DEFAULT 'desktop_v2',
  language TEXT NOT NULL,
  timezone TEXT NOT NULL,
  input_device_name TEXT,
  status TEXT NOT NULL DEFAULT 'recording',
  backend_id TEXT,
  last_error TEXT,
  retry_count INTEGER NOT NULL DEFAULT 0,
  next_retry_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS transcription_segments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id INTEGER NOT NULL REFERENCES transcription_sessions(id) ON DELETE CASCADE,
  text TEXT NOT NULL,
  speaker TEXT NOT NULL,
  speaker_id INTEGER NOT NULL,
  is_user INTEGER NOT NULL,
  start_time REAL NOT NULL,
  end_time REAL NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_segments_session ON transcription_segments(session_id);
CREATE INDEX IF NOT EXISTS idx_sessions_status  ON transcription_sessions(status);
";
