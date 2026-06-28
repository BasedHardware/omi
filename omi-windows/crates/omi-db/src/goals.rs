use anyhow::Result;
use chrono::Utc;
use rusqlite::params;

use crate::schema::Goal;
use crate::Database;

impl Database {
    pub fn insert_goal(&self, content: &str) -> Result<String> {
        let id = uuid::Uuid::new_v4().to_string();
        let now = Utc::now().to_rfc3339();
        let conn = self.conn();
        conn.execute(
            "INSERT INTO goals (id, content, status, progress_pct, created_at)
             VALUES (?1, ?2, 'active', 0, ?3)",
            params![id, content, now],
        )?;
        Ok(id)
    }

    pub fn list_goals(&self, status: Option<&str>) -> Result<Vec<Goal>> {
        let conn = self.conn();
        let (sql, p): (&str, Vec<Box<dyn rusqlite::types::ToSql>>) = match status {
            Some(s) => (
                "SELECT id, content, status, progress_pct, created_at, completed_at
                 FROM goals WHERE status = ?1 ORDER BY created_at DESC",
                vec![Box::new(s.to_string())],
            ),
            None => (
                "SELECT id, content, status, progress_pct, created_at, completed_at
                 FROM goals ORDER BY created_at DESC",
                vec![],
            ),
        };
        let mut stmt = conn.prepare(sql)?;
        let rows = stmt.query_map(rusqlite::params_from_iter(p.iter()), Self::row_to_goal)?;
        let mut out = Vec::new();
        for r in rows {
            out.push(r?);
        }
        Ok(out)
    }

    pub fn update_goal_progress(&self, id: &str, progress_pct: i32) -> Result<()> {
        let conn = self.conn();
        if progress_pct >= 100 {
            let now = Utc::now().to_rfc3339();
            conn.execute(
                "UPDATE goals SET progress_pct = 100, status = 'completed', completed_at = ?1 WHERE id = ?2",
                params![now, id],
            )?;
        } else {
            conn.execute(
                "UPDATE goals SET progress_pct = ?1 WHERE id = ?2",
                params![progress_pct, id],
            )?;
        }
        Ok(())
    }

    pub fn delete_goal(&self, id: &str) -> Result<()> {
        let conn = self.conn();
        conn.execute("DELETE FROM goals WHERE id = ?1", params![id])?;
        Ok(())
    }

    fn row_to_goal(row: &rusqlite::Row) -> rusqlite::Result<Goal> {
        Ok(Goal {
            id: row.get(0)?,
            content: row.get(1)?,
            status: row.get(2)?,
            progress_pct: row.get(3)?,
            created_at: row
                .get::<_, String>(4)?
                .parse()
                .unwrap_or_else(|_| Utc::now()),
            completed_at: row
                .get::<_, Option<String>>(5)?
                .and_then(|s| s.parse().ok()),
        })
    }
}
