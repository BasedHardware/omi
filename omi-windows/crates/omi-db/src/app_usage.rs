use anyhow::Result;
use chrono::Utc;
use rusqlite::params;

use crate::Database;

#[derive(Debug, Clone)]
pub struct AppUsageRow {
    pub app_name: String,
    pub date: String,
    pub total_seconds: i64,
}

impl Database {
    pub fn record_app_usage(&self, app_name: &str, seconds: i64) -> Result<()> {
        let date = Utc::now().format("%Y-%m-%d").to_string();
        let id = format!("{app_name}:{date}");
        let conn = self.conn();
        conn.execute(
            "INSERT INTO app_usage (id, app_name, date, total_seconds) VALUES (?1, ?2, ?3, ?4)
             ON CONFLICT(app_name, date) DO UPDATE SET total_seconds = total_seconds + ?4",
            params![id, app_name, date, seconds],
        )?;
        Ok(())
    }

    pub fn get_today_app_usage(&self) -> Result<Vec<AppUsageRow>> {
        let today = Utc::now().format("%Y-%m-%d").to_string();
        let conn = self.conn();
        let mut stmt = conn.prepare(
            "SELECT app_name, date, total_seconds FROM app_usage WHERE date = ?1 ORDER BY total_seconds DESC",
        )?;
        let rows = stmt.query_map([today], |row| {
            Ok(AppUsageRow {
                app_name: row.get(0)?,
                date: row.get(1)?,
                total_seconds: row.get(2)?,
            })
        })?;
        Ok(rows.filter_map(|r| r.ok()).collect())
    }

    pub fn get_top_apps_today(&self, limit: usize) -> Result<Vec<(String, i64)>> {
        let rows = self.get_today_app_usage()?;
        Ok(rows.into_iter().take(limit).map(|r| (r.app_name, r.total_seconds)).collect())
    }
}
