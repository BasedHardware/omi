use anyhow::Result;
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

use crate::Database;

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum SearchResultKind {
    Memory,
    Screenshot,
    Clipboard,
    File,
    Conversation,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct UnifiedSearchResult {
    pub kind: SearchResultKind,
    pub id: String,
    pub title: String,
    pub snippet: String,
    pub timestamp: DateTime<Utc>,
}

impl Database {
    pub fn search_all(&self, query: &str, limit: usize) -> Result<Vec<UnifiedSearchResult>> {
        let mut results = Vec::new();
        let per_source = (limit / 5).max(3);

        if let Ok(memories) = self.search_memories_text(query, per_source) {
            results.extend(memories);
        }

        if let Ok(screenshots) = self.search_screenshots_unified(query, per_source) {
            results.extend(screenshots);
        }

        if let Ok(clipboard) = self.search_clipboard_unified(query, per_source) {
            results.extend(clipboard);
        }

        if let Ok(files) = self.search_files_unified(query, per_source) {
            results.extend(files);
        }

        if let Ok(convos) = self.search_conversations_unified(query, per_source) {
            results.extend(convos);
        }

        results.sort_by(|a, b| b.timestamp.cmp(&a.timestamp));
        results.truncate(limit);
        Ok(results)
    }

    fn search_memories_text(
        &self,
        query: &str,
        limit: usize,
    ) -> Result<Vec<UnifiedSearchResult>> {
        let conn = self.conn();
        let pattern = format!("%{query}%");
        let mut stmt = conn.prepare(
            "SELECT id, content, category, created_at FROM memories
             WHERE content LIKE ?1 ORDER BY created_at DESC LIMIT ?2",
        )?;
        let rows = stmt.query_map(rusqlite::params![pattern, limit as i64], |row| {
            let content: String = row.get(1)?;
            let snippet = if content.len() > 150 {
                format!("{}…", &content[..150])
            } else {
                content.clone()
            };
            Ok(UnifiedSearchResult {
                kind: SearchResultKind::Memory,
                id: row.get(0)?,
                title: row
                    .get::<_, Option<String>>(2)?
                    .unwrap_or_else(|| "Memory".to_string()),
                snippet,
                timestamp: row
                    .get::<_, String>(3)?
                    .parse()
                    .unwrap_or_else(|_| Utc::now()),
            })
        })?;
        rows.collect::<Result<Vec<_>, _>>().map_err(Into::into)
    }

    fn search_screenshots_unified(
        &self,
        query: &str,
        limit: usize,
    ) -> Result<Vec<UnifiedSearchResult>> {
        let screenshots = self.search_screenshots(query, limit)?;
        Ok(screenshots
            .into_iter()
            .map(|s| {
                let snippet = s
                    .ocr_text
                    .as_deref()
                    .map(|t| {
                        if t.len() > 150 {
                            format!("{}…", &t[..150])
                        } else {
                            t.to_string()
                        }
                    })
                    .unwrap_or_default();
                UnifiedSearchResult {
                    kind: SearchResultKind::Screenshot,
                    id: s.id,
                    title: s.window_title.unwrap_or_else(|| "Screenshot".to_string()),
                    snippet,
                    timestamp: s.captured_at,
                }
            })
            .collect())
    }

    fn search_clipboard_unified(
        &self,
        query: &str,
        limit: usize,
    ) -> Result<Vec<UnifiedSearchResult>> {
        let conn = self.conn();
        let pattern = format!("%{query}%");
        let mut stmt = conn.prepare(
            "SELECT id, content, source_app, captured_at FROM clipboard_entries
             WHERE content LIKE ?1 ORDER BY captured_at DESC LIMIT ?2",
        )?;
        let rows = stmt.query_map(rusqlite::params![pattern, limit as i64], |row| {
            let content: String = row.get(1)?;
            let snippet = if content.len() > 150 {
                format!("{}…", &content[..150])
            } else {
                content
            };
            Ok(UnifiedSearchResult {
                kind: SearchResultKind::Clipboard,
                id: row.get(0)?,
                title: row
                    .get::<_, Option<String>>(2)?
                    .unwrap_or_else(|| "Clipboard".to_string()),
                snippet,
                timestamp: row
                    .get::<_, String>(3)?
                    .parse()
                    .unwrap_or_else(|_| Utc::now()),
            })
        })?;
        rows.collect::<Result<Vec<_>, _>>().map_err(Into::into)
    }

    fn search_files_unified(
        &self,
        query: &str,
        limit: usize,
    ) -> Result<Vec<UnifiedSearchResult>> {
        let conn = self.conn();
        let pattern = format!("%{query}%");
        let mut stmt = conn.prepare(
            "SELECT id, file_path, file_name, extension, modified_at FROM indexed_files
             WHERE file_name LIKE ?1 OR file_path LIKE ?1
             ORDER BY modified_at DESC LIMIT ?2",
        )?;
        let rows = stmt.query_map(rusqlite::params![pattern, limit as i64], |row| {
            Ok(UnifiedSearchResult {
                kind: SearchResultKind::File,
                id: row.get(0)?,
                title: row.get::<_, String>(2)?,
                snippet: row.get::<_, String>(1)?,
                timestamp: row
                    .get::<_, String>(4)?
                    .parse()
                    .unwrap_or_else(|_| Utc::now()),
            })
        })?;
        rows.collect::<Result<Vec<_>, _>>().map_err(Into::into)
    }

    fn search_conversations_unified(
        &self,
        query: &str,
        limit: usize,
    ) -> Result<Vec<UnifiedSearchResult>> {
        let conn = self.conn();
        let pattern = format!("%{query}%");
        let mut stmt = conn.prepare(
            "SELECT id, title, summary, started_at FROM conversations
             WHERE title LIKE ?1 OR summary LIKE ?1
             ORDER BY started_at DESC LIMIT ?2",
        )?;
        let rows = stmt.query_map(rusqlite::params![pattern, limit as i64], |row| {
            let snippet = row
                .get::<_, Option<String>>(2)?
                .unwrap_or_default();
            let snippet = if snippet.len() > 150 {
                format!("{}…", &snippet[..150])
            } else {
                snippet
            };
            Ok(UnifiedSearchResult {
                kind: SearchResultKind::Conversation,
                id: row.get(0)?,
                title: row
                    .get::<_, Option<String>>(1)?
                    .unwrap_or_else(|| "Conversation".to_string()),
                snippet,
                timestamp: row
                    .get::<_, String>(3)?
                    .parse()
                    .unwrap_or_else(|_| Utc::now()),
            })
        })?;
        rows.collect::<Result<Vec<_>, _>>().map_err(Into::into)
    }
}
