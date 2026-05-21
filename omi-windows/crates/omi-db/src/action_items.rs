use anyhow::Result;
use chrono::Utc;
use rusqlite::params;

use crate::schema::ActionItem;
use crate::Database;

impl Database {
    /// Insert an action item extracted from a conversation.
    pub fn insert_action_item(
        &self,
        conversation_id: Option<&str>,
        content: &str,
    ) -> Result<String> {
        let id = uuid::Uuid::new_v4().to_string();
        let now = Utc::now().to_rfc3339();
        let conn = self.conn();
        conn.execute(
            "INSERT INTO action_items (id, conversation_id, content, completed, created_at)
             VALUES (?1, ?2, ?3, 0, ?4)",
            params![id, conversation_id, content, now],
        )?;
        Ok(id)
    }

    /// Toggle an action item's completed state.
    pub fn toggle_action_item(&self, id: &str) -> Result<bool> {
        let conn = self.conn();
        conn.execute(
            "UPDATE action_items SET completed = NOT completed WHERE id = ?1",
            params![id],
        )?;
        let completed: bool = conn.query_row(
            "SELECT completed FROM action_items WHERE id = ?1",
            params![id],
            |r| r.get(0),
        )?;
        Ok(completed)
    }

    /// List all action items, incomplete first then by date.
    pub fn list_action_items(&self, limit: usize) -> Result<Vec<ActionItem>> {
        let conn = self.conn();
        let mut stmt = conn.prepare(
            "SELECT id, conversation_id, content, completed, created_at
             FROM action_items
             ORDER BY completed ASC, created_at DESC LIMIT ?1"
        )?;
        let rows = stmt.query_map(params![limit as i64], |row| {
            Ok(ActionItem {
                id: row.get(0)?,
                conversation_id: row.get(1)?,
                content: row.get(2)?,
                completed: row.get::<_, i32>(3)? != 0,
                created_at: row.get::<_, String>(4)?.parse().unwrap_or_else(|_| Utc::now()),
            })
        })?;
        let mut items = Vec::new();
        for r in rows { items.push(r?); }
        Ok(items)
    }

    /// Delete a completed action item.
    pub fn delete_action_item(&self, id: &str) -> Result<()> {
        let conn = self.conn();
        conn.execute("DELETE FROM action_items WHERE id = ?1", params![id])?;
        Ok(())
    }

    /// Delete all completed action items.
    pub fn delete_completed_action_items(&self) -> Result<usize> {
        let conn = self.conn();
        Ok(conn.execute("DELETE FROM action_items WHERE completed = 1", [])?)
    }

    /// Return open tasks as a compact numbered list for LLM dedup context.
    pub fn list_open_action_items_for_dedup(&self, limit: usize) -> Result<String> {
        let items = self.list_action_items(limit)?;
        let open: Vec<_> = items.iter().filter(|i| !i.completed).collect();
        if open.is_empty() { return Ok(String::new()); }
        Ok(open.iter().enumerate()
            .map(|(i, t)| format!("{}. {}", i + 1, t.content))
            .collect::<Vec<_>>()
            .join("\n"))
    }

    /// Check whether any existing open task is sufficiently similar to `content`.
    pub fn has_similar_action_item(&self, content: &str, threshold: f64) -> Result<bool> {
        let items = self.list_action_items(200)?;
        let needle = action_word_tokens(content);
        Ok(items.iter()
            .filter(|i| !i.completed)
            .any(|i| action_jaccard(&needle, &action_word_tokens(&i.content)) >= threshold))
    }
}

// ── Dedup helpers ─────────────────────────────────────────────────────────────

fn action_word_tokens(s: &str) -> std::collections::HashSet<String> {
    s.to_lowercase()
        .split(|c: char| !c.is_alphanumeric())
        .filter(|w| w.len() > 2)
        .map(str::to_string)
        .collect()
}

fn action_jaccard(a: &std::collections::HashSet<String>, b: &std::collections::HashSet<String>) -> f64 {
    if a.is_empty() && b.is_empty() { return 1.0; }
    let inter = a.intersection(b).count() as f64;
    let union = a.union(b).count() as f64;
    if union == 0.0 { 0.0 } else { inter / union }
}
