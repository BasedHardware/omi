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
}
