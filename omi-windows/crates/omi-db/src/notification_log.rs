use anyhow::Result;
use chrono::{DateTime, Local, NaiveDateTime};

use crate::Database;

#[derive(Debug, Clone)]
pub struct NotificationRecord {
    pub id: String,
    pub title: String,
    pub body: String,
    pub priority: u8,
    pub created_at: DateTime<Local>,
}

impl Database {
    pub fn insert_notification(&self, title: &str, body: &str, priority: u8) -> Result<()> {
        let id = uuid::Uuid::new_v4().to_string();
        let conn = self.conn();
        conn.execute(
            "INSERT INTO notification_history (id, title, body, priority) VALUES (?1, ?2, ?3, ?4)",
            rusqlite::params![id, title, body, priority as i32],
        )?;
        Ok(())
    }

    pub fn list_notifications(&self, limit: usize) -> Result<Vec<NotificationRecord>> {
        let conn = self.conn();
        let mut stmt = conn.prepare(
            "SELECT id, title, body, priority, created_at
             FROM notification_history
             ORDER BY created_at DESC
             LIMIT ?1"
        )?;
        let rows = stmt.query_map(rusqlite::params![limit as i64], |row| {
            let ts: String = row.get(4)?;
            let ndt = NaiveDateTime::parse_from_str(&ts, "%Y-%m-%d %H:%M:%S")
                .unwrap_or_default();
            let dt = ndt.and_local_timezone(Local).unwrap();
            Ok(NotificationRecord {
                id: row.get(0)?,
                title: row.get(1)?,
                body: row.get(2)?,
                priority: row.get::<_, i32>(3)? as u8,
                created_at: dt,
            })
        })?;
        let mut result = Vec::new();
        for r in rows {
            result.push(r?);
        }
        Ok(result)
    }

    pub fn clear_notifications(&self) -> Result<()> {
        let conn = self.conn();
        conn.execute("DELETE FROM notification_history", [])?;
        Ok(())
    }
}
