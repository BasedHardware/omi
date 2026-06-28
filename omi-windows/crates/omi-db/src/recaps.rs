use anyhow::Result;
use chrono::Utc;
use rusqlite::params;

use crate::schema::DailyRecap;
use crate::Database;

impl Database {
    pub fn insert_daily_recap(
        &self,
        date: &str,
        summary: &str,
        stats_json: Option<&str>,
    ) -> Result<String> {
        let id = uuid::Uuid::new_v4().to_string();
        let now = Utc::now().to_rfc3339();
        let conn = self.conn();
        conn.execute(
            "INSERT OR REPLACE INTO daily_recaps (id, date, summary, stats_json, created_at)
             VALUES (?1, ?2, ?3, ?4, ?5)",
            params![id, date, summary, stats_json, now],
        )?;
        Ok(id)
    }

    pub fn get_recap_for_date(&self, date: &str) -> Result<Option<DailyRecap>> {
        let conn = self.conn();
        conn.query_row(
            "SELECT id, date, summary, stats_json, created_at FROM daily_recaps WHERE date = ?1",
            params![date],
            |row| {
                Ok(DailyRecap {
                    id: row.get(0)?,
                    date: row.get(1)?,
                    summary: row.get(2)?,
                    stats_json: row.get(3)?,
                    created_at: row
                        .get::<_, String>(4)?
                        .parse()
                        .unwrap_or_else(|_| Utc::now()),
                })
            },
        )
        .optional()
        .map_err(Into::into)
    }

    pub fn list_recaps(&self, limit: usize) -> Result<Vec<DailyRecap>> {
        let conn = self.conn();
        let mut stmt = conn.prepare(
            "SELECT id, date, summary, stats_json, created_at
             FROM daily_recaps ORDER BY date DESC LIMIT ?1",
        )?;
        let rows = stmt.query_map(params![limit as i64], |row| {
            Ok(DailyRecap {
                id: row.get(0)?,
                date: row.get(1)?,
                summary: row.get(2)?,
                stats_json: row.get(3)?,
                created_at: row
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

    pub fn get_today_stats(&self) -> Result<DayStats> {
        let conn = self.conn();
        let today = Utc::now().format("%Y-%m-%d").to_string();

        let conversations: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM conversations WHERE started_at >= ?1",
                params![format!("{today}T00:00:00")],
                |row| row.get(0),
            )
            .unwrap_or(0);

        let memories: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM memories WHERE created_at >= ?1",
                params![format!("{today}T00:00:00")],
                |row| row.get(0),
            )
            .unwrap_or(0);

        let screenshots: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM screenshots WHERE captured_at >= ?1",
                params![format!("{today}T00:00:00")],
                |row| row.get(0),
            )
            .unwrap_or(0);

        let tasks_completed: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM action_items WHERE completed = 1",
                [],
                |row| row.get(0),
            )
            .unwrap_or(0);

        let clipboard_items: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM clipboard_entries WHERE captured_at >= ?1",
                params![format!("{today}T00:00:00")],
                |row| row.get(0),
            )
            .unwrap_or(0);

        let mut stmt = conn.prepare(
            "SELECT DISTINCT window_title FROM screenshots
             WHERE captured_at >= ?1 AND window_title IS NOT NULL
             LIMIT 20",
        )?;
        let apps: Vec<String> = stmt
            .query_map(params![format!("{today}T00:00:00")], |row| row.get(0))?
            .filter_map(|r| r.ok())
            .collect();

        Ok(DayStats {
            conversations,
            memories,
            screenshots,
            tasks_completed,
            clipboard_items,
            apps_used: apps,
        })
    }
}

pub struct DayStats {
    pub conversations: i64,
    pub memories: i64,
    pub screenshots: i64,
    pub tasks_completed: i64,
    pub clipboard_items: i64,
    pub apps_used: Vec<String>,
}

trait OptionalExt<T> {
    fn optional(self) -> Result<Option<T>, rusqlite::Error>;
}

impl<T> OptionalExt<T> for rusqlite::Result<T> {
    fn optional(self) -> Result<Option<T>, rusqlite::Error> {
        match self {
            Ok(v) => Ok(Some(v)),
            Err(rusqlite::Error::QueryReturnedNoRows) => Ok(None),
            Err(e) => Err(e),
        }
    }
}
