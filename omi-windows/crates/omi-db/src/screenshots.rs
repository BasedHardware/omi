use anyhow::Result;
use chrono::Utc;
use rusqlite::params;

use crate::schema::Screenshot;
use crate::Database;

impl Database {
    /// Insert a new screenshot record. Returns the generated id.
    pub fn insert_screenshot(
        &self,
        app_name: Option<&str>,
        window_title: Option<&str>,
        ocr_text: Option<&str>,
        thumbnail_path: Option<&str>,
    ) -> Result<String> {
        let id = uuid::Uuid::new_v4().to_string();
        let now = Utc::now().to_rfc3339();
        let conn = self.conn();
        conn.execute(
            "INSERT INTO screenshots (id, captured_at, app_name, window_title, ocr_text, thumbnail_path)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
            params![id, now, app_name, window_title, ocr_text, thumbnail_path],
        )?;
        // Update FTS index
        conn.execute(
            "INSERT INTO screenshots_fts (id, ocr_text, app_name, window_title)
             VALUES (?1, ?2, ?3, ?4)",
            params![id, ocr_text.unwrap_or(""), app_name.unwrap_or(""), window_title.unwrap_or("")],
        )?;
        Ok(id)
    }

    /// List recent screenshots, newest first.
    pub fn list_screenshots(&self, limit: usize) -> Result<Vec<Screenshot>> {
        let conn = self.conn();
        let mut stmt = conn.prepare(
            "SELECT id, captured_at, app_name, window_title, ocr_text, thumbnail_path
             FROM screenshots ORDER BY captured_at DESC LIMIT ?1"
        )?;
        let rows = stmt.query_map(params![limit as i64], |row| {
            Ok(Screenshot {
                id: row.get(0)?,
                captured_at: row.get::<_, String>(1)?.parse().unwrap_or_else(|_| Utc::now()),
                app_name: row.get(2)?,
                window_title: row.get(3)?,
                ocr_text: row.get(4)?,
                thumbnail_path: row.get(5)?,
            })
        })?;
        let mut out = Vec::new();
        for r in rows { out.push(r?); }
        Ok(out)
    }

    /// Full-text search screenshots by OCR/window text.
    pub fn search_screenshots(&self, query: &str, limit: usize) -> Result<Vec<Screenshot>> {
        let conn = self.conn();
        let mut stmt = conn.prepare(
            "SELECT s.id, s.captured_at, s.app_name, s.window_title, s.ocr_text, s.thumbnail_path
             FROM screenshots s
             JOIN screenshots_fts f ON s.id = f.id
             WHERE screenshots_fts MATCH ?1
             ORDER BY s.captured_at DESC LIMIT ?2"
        )?;
        let rows = stmt.query_map(params![query, limit as i64], |row| {
            Ok(Screenshot {
                id: row.get(0)?,
                captured_at: row.get::<_, String>(1)?.parse().unwrap_or_else(|_| Utc::now()),
                app_name: row.get(2)?,
                window_title: row.get(3)?,
                ocr_text: row.get(4)?,
                thumbnail_path: row.get(5)?,
            })
        })?;
        let mut out = Vec::new();
        for r in rows { out.push(r?); }
        Ok(out)
    }

    /// Delete screenshots older than `days` days to manage disk usage.
    pub fn prune_old_screenshots(&self, days: u32) -> Result<usize> {
        let conn = self.conn();
        let deleted = conn.execute(
            "DELETE FROM screenshots WHERE captured_at < datetime('now', ?1)",
            params![format!("-{days} days")],
        )?;
        Ok(deleted)
    }
}
