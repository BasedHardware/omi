use anyhow::Result;
use chrono::Utc;
use rusqlite::params;

use crate::schema::{Conversation, Segment};
use crate::Database;

impl Database {
    /// Create a new conversation and return its ID.
    pub fn create_conversation(&self, title: Option<&str>) -> Result<String> {
        let id = uuid::Uuid::new_v4().to_string();
        let now = Utc::now().to_rfc3339();
        let conn = self.conn();
        conn.execute(
            "INSERT INTO conversations (id, title, started_at, status) VALUES (?1, ?2, ?3, 'recording')",
            params![id, title, now],
        )?;
        Ok(id)
    }

    /// Mark a conversation as completed.
    pub fn complete_conversation(&self, id: &str) -> Result<()> {
        let now = Utc::now().to_rfc3339();
        let conn = self.conn();
        conn.execute(
            "UPDATE conversations SET status = 'completed', ended_at = ?1 WHERE id = ?2",
            params![now, id],
        )?;

        // Calculate duration
        conn.execute(
            "UPDATE conversations SET duration_secs = (
                julianday(ended_at) - julianday(started_at)
            ) * 86400.0 WHERE id = ?1",
            params![id],
        )?;
        Ok(())
    }

    /// Insert a transcript segment.
    pub fn insert_segment(
        &self,
        conversation_id: &str,
        speaker: i32,
        text: &str,
        start_time: f64,
        end_time: f64,
        is_final: bool,
    ) -> Result<String> {
        let id = uuid::Uuid::new_v4().to_string();
        let conn = self.conn();
        conn.execute(
            "INSERT INTO segments (id, conversation_id, speaker, text, start_time, end_time, is_final)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
            params![id, conversation_id, speaker, text, start_time, end_time, is_final as i32],
        )?;
        Ok(id)
    }

    /// List all conversations, most recent first.
    pub fn list_conversations(&self, limit: usize) -> Result<Vec<Conversation>> {
        let conn = self.conn();
        let mut stmt = conn.prepare(
            "SELECT id, title, started_at, ended_at, duration_secs, status, summary
             FROM conversations ORDER BY started_at DESC LIMIT ?1"
        )?;

        let rows = stmt.query_map(params![limit as i64], |row| {
            Ok(Conversation {
                id: row.get(0)?,
                title: row.get(1)?,
                started_at: row.get::<_, String>(2)?
                    .parse()
                    .unwrap_or_else(|_| Utc::now()),
                ended_at: row.get::<_, Option<String>>(3)?
                    .and_then(|s| s.parse().ok()),
                duration_secs: row.get(4)?,
                status: row.get(5)?,
                summary: row.get(6)?,
            })
        })?;

        let mut conversations = Vec::new();
        for row in rows {
            conversations.push(row?);
        }
        Ok(conversations)
    }

    /// Get all segments for a conversation.
    pub fn get_segments(&self, conversation_id: &str) -> Result<Vec<Segment>> {
        let conn = self.conn();
        let mut stmt = conn.prepare(
            "SELECT id, conversation_id, speaker, text, start_time, end_time, is_final, created_at
             FROM segments WHERE conversation_id = ?1 AND is_final = 1
             ORDER BY start_time ASC"
        )?;

        let rows = stmt.query_map(params![conversation_id], |row| {
            Ok(Segment {
                id: row.get(0)?,
                conversation_id: row.get(1)?,
                speaker: row.get(2)?,
                text: row.get(3)?,
                start_time: row.get(4)?,
                end_time: row.get(5)?,
                is_final: row.get::<_, i32>(6)? != 0,
                created_at: row.get::<_, String>(7)?
                    .parse()
                    .unwrap_or_else(|_| Utc::now()),
            })
        })?;

        let mut segments = Vec::new();
        for row in rows {
            segments.push(row?);
        }
        Ok(segments)
    }

    /// Get full transcript text for a conversation.
    pub fn get_transcript_text(&self, conversation_id: &str) -> Result<String> {
        let segments = self.get_segments(conversation_id)?;
        let text = segments
            .iter()
            .map(|s| format!("Speaker {}: {}", s.speaker, s.text))
            .collect::<Vec<_>>()
            .join("\n");
        Ok(text)
    }
}
