use anyhow::Result;
use chrono::Utc;
use rusqlite::params;

use crate::schema::ClipboardEntry;
use crate::Database;

impl Database {
    pub fn insert_clipboard_entry(
        &self,
        content: &str,
        content_type: &str,
        source_app: Option<&str>,
    ) -> Result<String> {
        let id = uuid::Uuid::new_v4().to_string();
        let now = Utc::now().to_rfc3339();
        let conn = self.conn();
        conn.execute(
            "INSERT INTO clipboard_entries (id, content, content_type, source_app, captured_at)
             VALUES (?1, ?2, ?3, ?4, ?5)",
            params![id, content, content_type, source_app, now],
        )?;
        conn.execute(
            "INSERT INTO clipboard_fts (id, content, source_app)
             VALUES (?1, ?2, ?3)",
            params![id, content, source_app.unwrap_or("")],
        )?;
        Ok(id)
    }

    pub fn list_clipboard_entries(&self, limit: usize) -> Result<Vec<ClipboardEntry>> {
        let conn = self.conn();
        let mut stmt = conn.prepare(
            "SELECT id, content, content_type, source_app, captured_at
             FROM clipboard_entries ORDER BY captured_at DESC LIMIT ?1",
        )?;
        let rows = stmt.query_map(params![limit as i64], |row| {
            Ok(ClipboardEntry {
                id: row.get(0)?,
                content: row.get(1)?,
                content_type: row.get(2)?,
                source_app: row.get(3)?,
                captured_at: row
                    .get::<_, String>(4)?
                    .parse()
                    .unwrap_or_else(|_| Utc::now()),
            })
        })?;
        let mut out = Vec::new();
        for r in rows {
            out.push(r?);
        }
        Ok(out)
    }

    pub fn search_clipboard(&self, query: &str, limit: usize) -> Result<Vec<ClipboardEntry>> {
        let conn = self.conn();
        let mut stmt = conn.prepare(
            "SELECT c.id, c.content, c.content_type, c.source_app, c.captured_at
             FROM clipboard_entries c
             JOIN clipboard_fts f ON c.id = f.id
             WHERE clipboard_fts MATCH ?1
             ORDER BY c.captured_at DESC LIMIT ?2",
        )?;
        let rows = stmt.query_map(params![query, limit as i64], |row| {
            Ok(ClipboardEntry {
                id: row.get(0)?,
                content: row.get(1)?,
                content_type: row.get(2)?,
                source_app: row.get(3)?,
                captured_at: row
                    .get::<_, String>(4)?
                    .parse()
                    .unwrap_or_else(|_| Utc::now()),
            })
        })?;
        let mut out = Vec::new();
        for r in rows {
            out.push(r?);
        }
        Ok(out)
    }

    pub fn get_clipboard_text(&self, limit: usize) -> Result<String> {
        let entries = self.list_clipboard_entries(limit)?;
        Ok(entries
            .iter()
            .map(|e| {
                let app = e.source_app.as_deref().unwrap_or("unknown");
                let preview = if e.content.len() > 120 {
                    format!("{}…", &e.content[..120])
                } else {
                    e.content.clone()
                };
                format!(
                    "- [{}] ({}) {}",
                    e.captured_at.format("%H:%M"),
                    app,
                    preview
                )
            })
            .collect::<Vec<_>>()
            .join("\n"))
    }

    pub fn prune_old_clipboard(&self, days: u32) -> Result<usize> {
        let conn = self.conn();
        let deleted = conn.execute(
            "DELETE FROM clipboard_entries WHERE captured_at < datetime('now', ?1)",
            params![format!("-{days} days")],
        )?;
        Ok(deleted)
    }
}
