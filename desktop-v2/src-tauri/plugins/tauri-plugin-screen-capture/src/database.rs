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
