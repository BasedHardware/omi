use anyhow::Result;
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashSet;

use crate::Database;

#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum SearchResultKind {
    Memory,
    Screenshot,
    Clipboard,
    File,
    Conversation,
    KnowledgeBase,
}

impl SearchResultKind {
    pub fn label(&self) -> &'static str {
        match self {
            Self::Memory => "Memory",
            Self::Screenshot => "Screenshot",
            Self::Clipboard => "Clipboard",
            Self::File => "File",
            Self::Conversation => "Conversation",
            Self::KnowledgeBase => "Knowledge",
        }
    }

    fn priority_bonus(&self) -> f64 {
        match self {
            Self::Memory => 4.0,
            Self::Conversation => 3.0,
            Self::Clipboard => 2.0,
            Self::KnowledgeBase => 2.5,
            Self::File => 1.0,
            Self::Screenshot => 0.5,
        }
    }

    pub fn all_local() -> HashSet<Self> {
        [Self::Memory, Self::Screenshot, Self::Clipboard, Self::File, Self::Conversation]
            .into_iter()
            .collect()
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UnifiedSearchResult {
    pub kind: SearchResultKind,
    pub id: String,
    pub title: String,
    pub snippet: String,
    pub timestamp: DateTime<Utc>,
    pub score: f64,
}

impl PartialEq for UnifiedSearchResult {
    fn eq(&self, other: &Self) -> bool {
        self.id == other.id && self.kind == other.kind
    }
}

fn compute_score(
    kind: &SearchResultKind,
    title: &str,
    snippet: &str,
    query: &str,
    timestamp: &DateTime<Utc>,
) -> f64 {
    let query_lower = query.to_lowercase();
    let mut score = 0.0;

    // Title match bonus
    if title.to_lowercase().contains(&query_lower) {
        score += 10.0;
    }

    // Match density in snippet (up to 5 occurrences)
    let snippet_lower = snippet.to_lowercase();
    let occurrences = snippet_lower.matches(&query_lower).count().min(5);
    score += occurrences as f64 * 2.0;

    // Recency bonus: exponential decay with 1-week half-life
    let hours_ago = Utc::now()
        .signed_duration_since(*timestamp)
        .num_hours()
        .max(0) as f64;
    score += 5.0 * (-hours_ago / 168.0).exp();

    // Source priority
    score += kind.priority_bonus();

    score
}

impl Database {
    pub fn search_all(&self, query: &str, limit: usize) -> Result<Vec<UnifiedSearchResult>> {
        self.search_filtered(query, limit, &SearchResultKind::all_local())
    }

    pub fn search_filtered(
        &self,
        query: &str,
        limit: usize,
        sources: &HashSet<SearchResultKind>,
    ) -> Result<Vec<UnifiedSearchResult>> {
        let mut results = Vec::new();
        let per_source = (limit / sources.len().max(1)).max(3);

        if sources.contains(&SearchResultKind::Memory) {
            if let Ok(r) = self.search_memories_text(query, per_source) {
                results.extend(r);
            }
        }
        if sources.contains(&SearchResultKind::Screenshot) {
            if let Ok(r) = self.search_screenshots_unified(query, per_source) {
                results.extend(r);
            }
        }
        if sources.contains(&SearchResultKind::Clipboard) {
            if let Ok(r) = self.search_clipboard_unified(query, per_source) {
                results.extend(r);
            }
        }
        if sources.contains(&SearchResultKind::File) {
            if let Ok(r) = self.search_files_unified(query, per_source) {
                results.extend(r);
            }
        }
        if sources.contains(&SearchResultKind::Conversation) {
            if let Ok(r) = self.search_conversations_unified(query, per_source) {
                results.extend(r);
            }
        }

        // Score and sort
        for r in &mut results {
            r.score = compute_score(&r.kind, &r.title, &r.snippet, query, &r.timestamp);
        }
        results.sort_by(|a, b| b.score.partial_cmp(&a.score).unwrap_or(std::cmp::Ordering::Equal));
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
                content
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
                score: 0.0,
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
                    score: 0.0,
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
                score: 0.0,
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
                score: 0.0,
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
                score: 0.0,
            })
        })?;
        rows.collect::<Result<Vec<_>, _>>().map_err(Into::into)
    }
}
