use anyhow::Result;
use chrono::Utc;
use rusqlite::params;

use crate::schema::Memory;
use crate::Database;

impl Database {
    /// Insert a memory extracted from a conversation.
    pub fn insert_memory(
        &self,
        conversation_id: Option<&str>,
        content: &str,
        category: Option<&str>,
    ) -> Result<String> {
        let id = uuid::Uuid::new_v4().to_string();
        let now = Utc::now().to_rfc3339();
        let conn = self.conn();
        conn.execute(
            "INSERT INTO memories (id, conversation_id, content, category, created_at)
             VALUES (?1, ?2, ?3, ?4, ?5)",
            params![id, conversation_id, content, category, now],
        )?;
        Ok(id)
    }

    /// List recent memories, most recent first.
    pub fn list_memories(&self, limit: usize) -> Result<Vec<Memory>> {
        let conn = self.conn();
        let mut stmt = conn.prepare(
            "SELECT id, conversation_id, content, category, created_at
             FROM memories ORDER BY created_at DESC LIMIT ?1"
        )?;
        let rows = stmt.query_map(params![limit as i64], |row| {
            Ok(Memory {
                id: row.get(0)?,
                conversation_id: row.get(1)?,
                content: row.get(2)?,
                category: row.get(3)?,
                created_at: row.get::<_, String>(4)?
                    .parse()
                    .unwrap_or_else(|_| Utc::now()),
            })
        })?;
        let mut memories = Vec::new();
        for r in rows { memories.push(r?); }
        Ok(memories)
    }

    /// Get recent memories as a single text block for context injection.
    pub fn get_memories_text(&self, limit: usize) -> Result<String> {
        let memories = self.list_memories(limit)?;
        Ok(memories.iter()
            .map(|m| format!("- [{}] {}", m.category.as_deref().unwrap_or("general"), m.content))
            .collect::<Vec<_>>()
            .join("\n"))
    }

    /// Delete a memory by id.
    pub fn delete_memory(&self, id: &str) -> Result<()> {
        let conn = self.conn();
        conn.execute("DELETE FROM memories WHERE id = ?1", params![id])?;
        Ok(())
    }

    /// Return existing memories whose content is sufficiently similar to `content`.
    /// Uses a simple normalized overlap check on word tokens — no external deps.
    pub fn find_similar_memories(&self, content: &str, threshold: f64) -> Result<Vec<Memory>> {
        let all = self.list_memories(500)?;
        let needle_words = word_tokens(content);
        let similar = all.into_iter()
            .filter(|m| {
                let hay_words = word_tokens(&m.content);
                jaccard(&needle_words, &hay_words) >= threshold
            })
            .collect();
        Ok(similar)
    }

    /// Get all memories as a compact numbered list for LLM dedup context.
    pub fn list_memories_for_dedup(&self, limit: usize) -> Result<String> {
        let mems = self.list_memories(limit)?;
        if mems.is_empty() { return Ok(String::new()); }
        Ok(mems.iter().enumerate()
            .map(|(i, m)| format!("{}. [{}] {}", i + 1,
                m.category.as_deref().unwrap_or("general"), m.content))
            .collect::<Vec<_>>()
            .join("\n"))
    }
}

// ── Dedup helpers ─────────────────────────────────────────────────────────────

fn word_tokens(s: &str) -> std::collections::HashSet<String> {
    s.to_lowercase()
        .split(|c: char| !c.is_alphanumeric())
        .filter(|w| w.len() > 2)
        .map(str::to_string)
        .collect()
}

fn jaccard(a: &std::collections::HashSet<String>, b: &std::collections::HashSet<String>) -> f64 {
    if a.is_empty() && b.is_empty() { return 1.0; }
    let inter = a.intersection(b).count() as f64;
    let union = a.union(b).count() as f64;
    if union == 0.0 { 0.0 } else { inter / union }
}
