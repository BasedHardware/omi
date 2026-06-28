use anyhow::Result;
use chrono::Utc;
use rusqlite::params;

use crate::schema::IndexedFile;
use crate::Database;

impl Database {
    pub fn upsert_indexed_file(
        &self,
        file_path: &str,
        file_name: &str,
        extension: Option<&str>,
        size_bytes: i64,
        modified_at: &str,
    ) -> Result<String> {
        let conn = self.conn();
        let now = Utc::now().to_rfc3339();

        let existing: Option<String> = conn
            .query_row(
                "SELECT id FROM indexed_files WHERE file_path = ?1",
                params![file_path],
                |row| row.get(0),
            )
            .ok();

        if let Some(id) = existing {
            conn.execute(
                "UPDATE indexed_files SET file_name=?1, extension=?2, size_bytes=?3, modified_at=?4, indexed_at=?5 WHERE id=?6",
                params![file_name, extension, size_bytes, modified_at, now, id],
            )?;
            Ok(id)
        } else {
            let id = uuid::Uuid::new_v4().to_string();
            conn.execute(
                "INSERT INTO indexed_files (id, file_path, file_name, extension, size_bytes, modified_at, indexed_at)
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
                params![id, file_path, file_name, extension, size_bytes, modified_at, now],
            )?;
            conn.execute(
                "INSERT INTO files_fts (id, file_name, file_path, extension)
                 VALUES (?1, ?2, ?3, ?4)",
                params![id, file_name, file_path, extension.unwrap_or("")],
            )?;
            Ok(id)
        }
    }

    pub fn search_files(&self, query: &str, limit: usize) -> Result<Vec<IndexedFile>> {
        let conn = self.conn();
        let mut stmt = conn.prepare(
            "SELECT f.id, f.file_path, f.file_name, f.extension, f.size_bytes, f.modified_at, f.indexed_at
             FROM indexed_files f
             JOIN files_fts fts ON f.id = fts.id
             WHERE files_fts MATCH ?1
             ORDER BY f.modified_at DESC LIMIT ?2",
        )?;
        let rows = stmt.query_map(params![query, limit as i64], Self::row_to_indexed_file)?;
        let mut out = Vec::new();
        for r in rows {
            out.push(r?);
        }
        Ok(out)
    }

    pub fn list_recent_files(&self, limit: usize) -> Result<Vec<IndexedFile>> {
        let conn = self.conn();
        let mut stmt = conn.prepare(
            "SELECT id, file_path, file_name, extension, size_bytes, modified_at, indexed_at
             FROM indexed_files ORDER BY modified_at DESC LIMIT ?1",
        )?;
        let rows = stmt.query_map(params![limit as i64], Self::row_to_indexed_file)?;
        let mut out = Vec::new();
        for r in rows {
            out.push(r?);
        }
        Ok(out)
    }

    pub fn delete_stale_files(&self, before_indexed_at: &str) -> Result<usize> {
        let conn = self.conn();
        let deleted = conn.execute(
            "DELETE FROM indexed_files WHERE indexed_at < ?1",
            params![before_indexed_at],
        )?;
        Ok(deleted)
    }

    pub fn count_indexed_files(&self) -> Result<i64> {
        let conn = self.conn();
        conn.query_row("SELECT COUNT(*) FROM indexed_files", [], |row| row.get(0))
            .map_err(Into::into)
    }

    fn row_to_indexed_file(row: &rusqlite::Row) -> rusqlite::Result<IndexedFile> {
        Ok(IndexedFile {
            id: row.get(0)?,
            file_path: row.get(1)?,
            file_name: row.get(2)?,
            extension: row.get(3)?,
            size_bytes: row.get(4)?,
            modified_at: row
                .get::<_, String>(5)?
                .parse()
                .unwrap_or_else(|_| Utc::now()),
            indexed_at: row
                .get::<_, String>(6)?
                .parse()
                .unwrap_or_else(|_| Utc::now()),
        })
    }
}
