use rusqlite::{Connection, Result, params};
use std::path::Path;
use std::sync::Mutex;

/// A single screenshot row returned from list/search queries (no image_data to keep payloads small).
#[derive(Debug, Clone, serde::Serialize)]
pub struct ScreenshotRow {
    pub id: i64,
    pub timestamp: String,
    pub app_name: String,
    pub window_title: String,
    pub ocr_text: Option<String>,
    pub dhash: Option<String>,
    pub width: u32,
    pub height: u32,
}

/// A row that needs an embedding computed (used by the TS backfill loop).
#[derive(Debug, Clone, serde::Serialize)]
pub struct EmbeddingBacklogItem {
    pub id: i64,
    pub ocr_text: String,
    pub app_name: String,
    pub window_title: String,
}

/// A single semantic-search hit: screenshot id + cosine similarity score.
#[derive(Debug, Clone, serde::Serialize)]
pub struct SemanticHit {
    pub id: i64,
    pub similarity: f32,
}

/// Input payload for saving a companion session.
#[derive(Debug, serde::Deserialize)]
pub struct CompanionSessionInput {
    /// Unix milliseconds at the moment the user asked the question.
    pub timestamp: i64,
    /// Transcribed question text (empty until a transcript round-trip is wired up).
    pub transcript: String,
    /// Gemini's text answer.
    pub answer: String,
    /// JSON array of `{x,y,label}` objects in overlay-window-local CSS points.
    pub points_json: String,
    /// FK to screenshots.id — null when the screenshot wasn't persisted (e.g. dHash dupe).
    pub screenshot_id: Option<i64>,
    /// Index of the display the question was asked on.
    pub display_id: u32,
    // ---- Telemetry fields (V4) — all optional for backward compatibility ----
    /// "single" (Mode A) or "chain" (Mode B). Drives downstream analysis of how
    /// often each mode fires.
    #[serde(default)]
    pub mode: Option<String>,
    /// JSON array of chain steps: `[{ instruction, target_label }, ...]`. Empty for single-shot.
    #[serde(default)]
    pub steps_json: Option<String>,
    /// Full raw Gemini response (the JSON payload from the structured-output
    /// call) so we can debug mode-selection drift without re-running the model.
    #[serde(default)]
    pub gemini_raw_json: Option<String>,
    /// Frontmost macOS app name at PTT-press time ("Google Chrome", "Safari", "Slack").
    #[serde(default)]
    pub active_app: Option<String>,
    /// Frontmost app bundle id ("com.google.Chrome").
    #[serde(default)]
    pub active_bundle_id: Option<String>,
    /// Wall-clock from PTT-press to last user-visible artifact (TTS finish or chain end).
    #[serde(default)]
    pub duration_ms: Option<i64>,
}

/// A full companion session row returned from the database.
#[derive(Debug, Clone, serde::Serialize)]
pub struct CompanionSession {
    pub id: i64,
    pub timestamp: i64,
    pub transcript: String,
    pub answer: String,
    pub points_json: String,
    pub screenshot_id: Option<i64>,
    pub display_id: u32,
    pub mode: Option<String>,
    pub steps_json: Option<String>,
    pub gemini_raw_json: Option<String>,
    pub active_app: Option<String>,
    pub active_bundle_id: Option<String>,
    pub duration_ms: Option<i64>,
    /// Did the chain run to completion? Null for single-shot answers, false
    /// for chains that were cancelled (Esc) or aborted (grounding failure),
    /// true when all steps finished.
    pub chain_completed: Option<bool>,
    /// How many of the N planned chain steps the user actually clicked through.
    pub chain_steps_completed: Option<i64>,
    /// JSON array recording how each point/step was grounded:
    /// `["ax", "ocr", "gemini", ...]`.
    pub grounding_methods_json: Option<String>,
    /// Error text if the interaction failed (mic, Gemini, no screenshot, etc.).
    pub error: Option<String>,
}

/// Patch applied to an existing companion_sessions row when the chain
/// controller finishes — captures the outcome (completed vs cancelled,
/// how many steps the user actually did, which grounding methods fired).
#[derive(Debug, serde::Deserialize)]
pub struct CompanionSessionPatch {
    pub id: i64,
    #[serde(default)]
    pub chain_completed: Option<bool>,
    #[serde(default)]
    pub chain_steps_completed: Option<i64>,
    #[serde(default)]
    pub grounding_methods_json: Option<String>,
    #[serde(default)]
    pub duration_ms: Option<i64>,
    #[serde(default)]
    pub error: Option<String>,
}

/// SQLite-backed persistence for Rewind screenshots.
pub struct RewindDatabase {
    conn: Mutex<Connection>,
}

impl RewindDatabase {
    /// Open (or create) the Rewind database at `{app_data_dir}/rewind/rewind.db`.
    pub fn init(app_data_dir: &Path) -> Result<Self> {
        let rewind_dir = app_data_dir.join("rewind");
        std::fs::create_dir_all(&rewind_dir).map_err(|e| {
            rusqlite::Error::SqliteFailure(
                rusqlite::ffi::Error::new(rusqlite::ffi::SQLITE_CANTOPEN),
                Some(format!("Failed to create rewind dir: {}", e)),
            )
        })?;

        let db_path = rewind_dir.join("rewind.db");
        tracing::info!("Opening Rewind database at {:?}", db_path);

        let conn = Connection::open(&db_path)?;

        // Enable WAL for better concurrent read performance.
        // PRAGMA journal_mode returns a result row, so use query_row instead of execute_batch.
        let _mode: String =
            conn.query_row("PRAGMA journal_mode=WAL", [], |row| row.get(0))?;
        tracing::info!("SQLite journal mode: {}", _mode);

        // Run migrations gated on user_version.
        let version: i64 = conn.query_row("PRAGMA user_version", [], |row| row.get(0))?;
        if version < 1 {
            conn.execute_batch(MIGRATION_V1)?;
            conn.execute_batch("PRAGMA user_version = 1")?;
            tracing::info!("Ran Rewind DB migration V1");
        }
        if version < 2 {
            conn.execute_batch(MIGRATION_V2)?;
            conn.execute_batch("PRAGMA user_version = 2")?;
            tracing::info!("Ran Rewind DB migration V2 (embeddings)");
        }
        if version < 3 {
            conn.execute_batch(MIGRATION_V3)?;
            conn.execute_batch("PRAGMA user_version = 3")?;
            tracing::info!("Ran Rewind DB migration V3 (companion_sessions)");
        }
        if version < 4 {
            conn.execute_batch(MIGRATION_V4)?;
            conn.execute_batch("PRAGMA user_version = 4")?;
            tracing::info!("Ran Rewind DB migration V4 (companion telemetry)");
        }

        tracing::info!("Rewind database ready");
        Ok(Self { conn: Mutex::new(conn) })
    }

    /// Insert a new screenshot record and return its row ID.
    #[allow(clippy::too_many_arguments)]
    pub fn insert_screenshot(
        &self,
        timestamp: &str,
        app_name: &str,
        window_title: &str,
        image_data: &[u8],
        ocr_text: Option<&str>,
        ocr_blocks_json: Option<&str>,
        dhash: Option<&str>,
        width: u32,
        height: u32,
    ) -> Result<i64> {
        let conn = self.conn.lock().expect("db mutex poisoned");
        conn.execute(
            "INSERT INTO screenshots \
             (timestamp, app_name, window_title, image_data, ocr_text, ocr_blocks_json, dhash, width, height) \
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)",
            params![
                timestamp,
                app_name,
                window_title,
                image_data,
                ocr_text,
                ocr_blocks_json,
                dhash,
                width,
                height,
            ],
        )?;
        Ok(conn.last_insert_rowid())
    }

    /// Full-text search over OCR text, window title, and app name.
    /// Returns results ordered by BM25 rank (best match first), then newest first.
    pub fn search_fts(&self, query: &str, limit: u32) -> Result<Vec<ScreenshotRow>> {
        let conn = self.conn.lock().expect("db mutex poisoned");
        let mut stmt = conn.prepare(
            "SELECT s.id, s.timestamp, s.app_name, s.window_title, s.ocr_text, s.dhash, s.width, s.height \
             FROM screenshots s \
             JOIN screenshots_fts f ON f.rowid = s.id \
             WHERE screenshots_fts MATCH ?1 \
             ORDER BY bm25(screenshots_fts), s.timestamp DESC \
             LIMIT ?2",
        )?;
        let rows = stmt.query_map(params![query, limit], map_row)?;
        rows.collect()
    }

    /// Retrieve a single screenshot by ID (metadata only, no image_data).
    pub fn get_screenshot(&self, id: i64) -> Result<Option<ScreenshotRow>> {
        let conn = self.conn.lock().expect("db mutex poisoned");
        let mut stmt = conn.prepare(
            "SELECT id, timestamp, app_name, window_title, ocr_text, dhash, width, height \
             FROM screenshots WHERE id = ?1",
        )?;
        let mut rows = stmt.query_map(params![id], map_row)?;
        rows.next().transpose()
    }

    /// Paginated list of recent screenshots, newest first, metadata only.
    pub fn get_recent(&self, limit: u32, offset: u32) -> Result<Vec<ScreenshotRow>> {
        let conn = self.conn.lock().expect("db mutex poisoned");
        let mut stmt = conn.prepare(
            "SELECT id, timestamp, app_name, window_title, ocr_text, dhash, width, height \
             FROM screenshots \
             ORDER BY timestamp DESC \
             LIMIT ?1 OFFSET ?2",
        )?;
        let rows = stmt.query_map(params![limit, offset], map_row)?;
        rows.collect()
    }

    /// Retrieve just the raw image BLOB for a specific screenshot.
    pub fn get_image_data(&self, id: i64) -> Result<Option<Vec<u8>>> {
        let conn = self.conn.lock().expect("db mutex poisoned");
        let mut stmt =
            conn.prepare("SELECT image_data FROM screenshots WHERE id = ?1")?;
        let mut rows = stmt.query_map(params![id], |row| row.get::<_, Vec<u8>>(0))?;
        rows.next().transpose()
    }

    /// Total number of screenshot records in the database.
    #[allow(dead_code)]
    pub fn get_screenshot_count(&self) -> Result<u64> {
        let conn = self.conn.lock().expect("db mutex poisoned");
        let count: i64 =
            conn.query_row("SELECT COUNT(*) FROM screenshots", [], |row| row.get(0))?;
        Ok(count as u64)
    }

    /// Delete all screenshots with a timestamp earlier than `before_timestamp`.
    /// Returns the number of deleted rows.
    pub fn delete_older_than(&self, before_timestamp: &str) -> Result<u64> {
        let conn = self.conn.lock().expect("db mutex poisoned");
        let deleted =
            conn.execute("DELETE FROM screenshots WHERE timestamp < ?1", params![before_timestamp])?;
        Ok(deleted as u64)
    }

    /// Delete a single screenshot by ID. Returns true if a row was deleted.
    pub fn delete_screenshot(&self, id: i64) -> Result<bool> {
        let conn = self.conn.lock().expect("db mutex poisoned");
        let deleted = conn.execute("DELETE FROM screenshots WHERE id = ?1", params![id])?;
        Ok(deleted > 0)
    }

    /// Delete ALL screenshots. Returns the number of deleted rows.
    pub fn delete_all(&self) -> Result<u64> {
        let conn = self.conn.lock().expect("db mutex poisoned");
        let deleted = conn.execute("DELETE FROM screenshots", [])?;
        Ok(deleted as u64)
    }

    // -----------------------------------------------------------------------
    // Semantic search: store + read + scan embeddings as LE f32 BLOBs.
    // Ported from desktop-v2/src-tauri/src/commands/staged_tasks_db.rs.
    // -----------------------------------------------------------------------

    /// Persist an embedding (normalized f32 vector) against an existing row.
    pub fn update_screenshot_embedding(&self, id: i64, embedding: &[f32]) -> Result<()> {
        let bytes: Vec<u8> = embedding.iter().flat_map(|f| f.to_le_bytes()).collect();
        let conn = self.conn.lock().expect("db mutex poisoned");
        conn.execute(
            "UPDATE screenshots SET embedding = ?2 WHERE id = ?1",
            params![id, bytes],
        )?;
        Ok(())
    }

    /// Return screenshots that have OCR text but no embedding yet. Used by
    /// the TS backfill loop on app startup.
    pub fn get_screenshots_missing_embeddings(
        &self,
        limit: u32,
    ) -> Result<Vec<EmbeddingBacklogItem>> {
        let conn = self.conn.lock().expect("db mutex poisoned");
        let mut stmt = conn.prepare(
            "SELECT id, ocr_text, app_name, window_title \
             FROM screenshots \
             WHERE embedding IS NULL \
               AND ocr_text IS NOT NULL \
               AND length(ocr_text) >= 20 \
             ORDER BY timestamp DESC \
             LIMIT ?1",
        )?;
        let rows = stmt
            .query_map(params![limit], |row| {
                Ok(EmbeddingBacklogItem {
                    id: row.get(0)?,
                    ocr_text: row.get::<_, String>(1)?,
                    app_name: row.get(2)?,
                    window_title: row.get(3)?,
                })
            })?
            .collect::<Result<Vec<_>>>()?;
        Ok(rows)
    }

    /// Cosine-similarity search across stored embeddings. Vectors are
    /// pre-normalized on write, so cosine = dot product. Streams rows and
    /// keeps only hits above `min_sim`, returning up to `top_k` sorted desc.
    pub fn search_similar_screenshots(
        &self,
        query: &[f32],
        top_k: usize,
        min_sim: f32,
    ) -> Result<Vec<SemanticHit>> {
        let conn = self.conn.lock().expect("db mutex poisoned");
        let mut stmt = conn.prepare(
            "SELECT id, embedding FROM screenshots WHERE embedding IS NOT NULL",
        )?;

        let mut scored: Vec<SemanticHit> = stmt
            .query_map([], |row| {
                let id: i64 = row.get(0)?;
                let blob: Vec<u8> = row.get(1)?;
                Ok((id, blob))
            })?
            .filter_map(|res| res.ok())
            .filter_map(|(id, blob)| {
                let vec = parse_embedding(&blob)?;
                if vec.len() != query.len() {
                    return None;
                }
                let sim = dot(&vec, query);
                if sim < min_sim {
                    return None;
                }
                Some(SemanticHit { id, similarity: sim })
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

    // -----------------------------------------------------------------------
    // Companion sessions
    // -----------------------------------------------------------------------

    /// Insert a companion Q&A session and return its new row id.
    pub fn insert_companion_session(&self, input: &CompanionSessionInput) -> Result<i64> {
        let conn = self.conn.lock().expect("db mutex poisoned");
        conn.execute(
            "INSERT INTO companion_sessions \
             (timestamp, transcript, answer, points_json, screenshot_id, display_id, \
              mode, steps_json, gemini_raw_json, active_app, active_bundle_id, duration_ms) \
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12)",
            params![
                input.timestamp,
                input.transcript,
                input.answer,
                input.points_json,
                input.screenshot_id,
                input.display_id,
                input.mode,
                input.steps_json,
                input.gemini_raw_json,
                input.active_app,
                input.active_bundle_id,
                input.duration_ms,
            ],
        )?;
        Ok(conn.last_insert_rowid())
    }

    /// Patch an existing companion_sessions row with chain outcome /
    /// post-Gemini telemetry. Only non-None fields in `patch` are written.
    pub fn update_companion_session(&self, patch: &CompanionSessionPatch) -> Result<()> {
        let conn = self.conn.lock().expect("db mutex poisoned");
        // Build the SET clause dynamically so we don't clobber existing columns
        // with NULL when a caller only wants to update a subset.
        let mut sets: Vec<&str> = Vec::new();
        let mut vals: Vec<Box<dyn rusqlite::ToSql>> = Vec::new();
        if let Some(b) = patch.chain_completed {
            sets.push("chain_completed = ?");
            vals.push(Box::new(if b { 1i64 } else { 0i64 }));
        }
        if let Some(n) = patch.chain_steps_completed {
            sets.push("chain_steps_completed = ?");
            vals.push(Box::new(n));
        }
        if let Some(ref s) = patch.grounding_methods_json {
            sets.push("grounding_methods_json = ?");
            vals.push(Box::new(s.clone()));
        }
        if let Some(d) = patch.duration_ms {
            sets.push("duration_ms = ?");
            vals.push(Box::new(d));
        }
        if let Some(ref e) = patch.error {
            sets.push("error = ?");
            vals.push(Box::new(e.clone()));
        }
        if sets.is_empty() {
            return Ok(());
        }
        let sql = format!(
            "UPDATE companion_sessions SET {} WHERE id = ?",
            sets.join(", ")
        );
        vals.push(Box::new(patch.id));
        let val_refs: Vec<&dyn rusqlite::ToSql> = vals.iter().map(|v| v.as_ref()).collect();
        conn.execute(&sql, val_refs.as_slice())?;
        Ok(())
    }

    /// Return the most recent companion sessions, newest first.
    pub fn get_recent_companion_sessions(&self, limit: u32) -> Result<Vec<CompanionSession>> {
        let conn = self.conn.lock().expect("db mutex poisoned");
        let mut stmt = conn.prepare(
            "SELECT id, timestamp, transcript, answer, points_json, screenshot_id, display_id, \
                    mode, steps_json, gemini_raw_json, active_app, active_bundle_id, duration_ms, \
                    chain_completed, chain_steps_completed, grounding_methods_json, error \
             FROM companion_sessions \
             ORDER BY timestamp DESC \
             LIMIT ?1",
        )?;
        let rows = stmt.query_map(params![limit], map_companion_session_row)?;
        rows.collect()
    }

    /// Delete a single companion session by id.
    pub fn delete_companion_session(&self, id: i64) -> Result<()> {
        let conn = self.conn.lock().expect("db mutex poisoned");
        conn.execute("DELETE FROM companion_sessions WHERE id = ?1", params![id])?;
        Ok(())
    }

    /// Return the dhash of the most recently stored screenshot, used for deduplication.
    #[allow(dead_code)]
    pub fn get_latest_dhash(&self) -> Result<Option<String>> {
        let conn = self.conn.lock().expect("db mutex poisoned");
        let mut stmt = conn.prepare(
            "SELECT dhash FROM screenshots ORDER BY timestamp DESC LIMIT 1",
        )?;
        let mut rows = stmt.query_map([], |row| row.get::<_, Option<String>>(0))?;
        match rows.next() {
            Some(Ok(dhash)) => Ok(dhash),
            Some(Err(e)) => Err(e),
            None => Ok(None),
        }
    }
}

/// Decode a little-endian f32 BLOB. Returns None on length mismatch.
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

/// Plain dot product. Vectors are pre-normalized on write, so this equals
/// cosine similarity.
fn dot(a: &[f32], b: &[f32]) -> f32 {
    a.iter().zip(b.iter()).map(|(x, y)| x * y).sum()
}

/// Map a SQLite row to a `CompanionSession`.
fn map_companion_session_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<CompanionSession> {
    let chain_completed: Option<i64> = row.get(13)?;
    Ok(CompanionSession {
        id: row.get(0)?,
        timestamp: row.get(1)?,
        transcript: row.get(2)?,
        answer: row.get(3)?,
        points_json: row.get(4)?,
        screenshot_id: row.get(5)?,
        display_id: row.get::<_, u32>(6)?,
        mode: row.get(7)?,
        steps_json: row.get(8)?,
        gemini_raw_json: row.get(9)?,
        active_app: row.get(10)?,
        active_bundle_id: row.get(11)?,
        duration_ms: row.get(12)?,
        chain_completed: chain_completed.map(|n| n != 0),
        chain_steps_completed: row.get(14)?,
        grounding_methods_json: row.get(15)?,
        error: row.get(16)?,
    })
}

/// Map a SQLite row to a `ScreenshotRow` (columns: id, timestamp, app_name,
/// window_title, ocr_text, dhash, width, height).
fn map_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<ScreenshotRow> {
    Ok(ScreenshotRow {
        id: row.get(0)?,
        timestamp: row.get(1)?,
        app_name: row.get(2)?,
        window_title: row.get(3)?,
        ocr_text: row.get(4)?,
        dhash: row.get(5)?,
        width: row.get::<_, u32>(6)?,
        height: row.get::<_, u32>(7)?,
    })
}

// ---------------------------------------------------------------------------
// Database schema
// ---------------------------------------------------------------------------

const MIGRATION_V1: &str = "
CREATE TABLE IF NOT EXISTS screenshots (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp      TEXT    NOT NULL,
    app_name       TEXT    NOT NULL DEFAULT '',
    window_title   TEXT    NOT NULL DEFAULT '',
    image_data     BLOB    NOT NULL,
    ocr_text       TEXT,
    ocr_blocks_json TEXT,
    dhash          TEXT,
    width          INTEGER NOT NULL DEFAULT 0,
    height         INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_screenshots_timestamp
    ON screenshots(timestamp);

CREATE INDEX IF NOT EXISTS idx_screenshots_app_name
    ON screenshots(app_name);

-- FTS5 virtual table for full-text search over OCR text.
CREATE VIRTUAL TABLE IF NOT EXISTS screenshots_fts USING fts5(
    ocr_text, window_title, app_name,
    content='screenshots',
    content_rowid='id'
);

-- Keep the FTS index in sync with the main table.
CREATE TRIGGER IF NOT EXISTS screenshots_ai AFTER INSERT ON screenshots BEGIN
    INSERT INTO screenshots_fts(rowid, ocr_text, window_title, app_name)
    VALUES (new.id, new.ocr_text, new.window_title, new.app_name);
END;

CREATE TRIGGER IF NOT EXISTS screenshots_ad AFTER DELETE ON screenshots BEGIN
    INSERT INTO screenshots_fts(screenshots_fts, rowid, ocr_text, window_title, app_name)
    VALUES ('delete', old.id, old.ocr_text, old.window_title, old.app_name);
END;

CREATE TRIGGER IF NOT EXISTS screenshots_au AFTER UPDATE ON screenshots BEGIN
    INSERT INTO screenshots_fts(screenshots_fts, rowid, ocr_text, window_title, app_name)
    VALUES ('delete', old.id, old.ocr_text, old.window_title, old.app_name);
    INSERT INTO screenshots_fts(rowid, ocr_text, window_title, app_name)
    VALUES (new.id, new.ocr_text, new.window_title, new.app_name);
END;
";

// V2: add an `embedding` BLOB column (little-endian f32 vector, 3072-dim)
// for Gemini gemini-embedding-001 semantic search. A partial index on the
// NULL-embedding rows keeps the backfill query cheap.
const MIGRATION_V2: &str = "
ALTER TABLE screenshots ADD COLUMN embedding BLOB;

CREATE INDEX IF NOT EXISTS idx_screenshots_missing_embedding
    ON screenshots(id) WHERE embedding IS NULL;
";

// V3: companion sessions — one row per Q&A interaction (Phase 5 persistence).
const MIGRATION_V3: &str = "
CREATE TABLE IF NOT EXISTS companion_sessions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp     INTEGER NOT NULL,
    transcript    TEXT    NOT NULL DEFAULT '',
    answer        TEXT    NOT NULL,
    points_json   TEXT    NOT NULL,
    screenshot_id INTEGER,
    display_id    INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(screenshot_id) REFERENCES screenshots(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_companion_sessions_timestamp
    ON companion_sessions(timestamp DESC);
";

// V4: telemetry columns for companion_sessions — captures the full picture of
// each interaction (mode, raw Gemini response, active app, chain outcome,
// grounding method) so we can analyze patterns and improve the prompt /
// grounding pipeline over time. All columns are nullable for backward compat
// with V3-shaped rows already in user databases.
const MIGRATION_V4: &str = "
ALTER TABLE companion_sessions ADD COLUMN mode                  TEXT;
ALTER TABLE companion_sessions ADD COLUMN steps_json            TEXT;
ALTER TABLE companion_sessions ADD COLUMN gemini_raw_json       TEXT;
ALTER TABLE companion_sessions ADD COLUMN active_app            TEXT;
ALTER TABLE companion_sessions ADD COLUMN active_bundle_id      TEXT;
ALTER TABLE companion_sessions ADD COLUMN duration_ms           INTEGER;
ALTER TABLE companion_sessions ADD COLUMN chain_completed       INTEGER;
ALTER TABLE companion_sessions ADD COLUMN chain_steps_completed INTEGER;
ALTER TABLE companion_sessions ADD COLUMN grounding_methods_json TEXT;
ALTER TABLE companion_sessions ADD COLUMN error                 TEXT;
";
