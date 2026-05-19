pub mod schema;
pub mod screenshots;
pub mod transcriptions;
pub mod memories;
pub mod action_items;
pub mod migrations;

use anyhow::{Context, Result};
use rusqlite::Connection;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};

/// Thread-safe database handle.
#[derive(Clone)]
pub struct Database {
    conn: Arc<Mutex<Connection>>,
}

impl Database {
    /// Open or create the database at `%APPDATA%/omi/omi.db`.
    pub fn open() -> Result<Self> {
        let path = db_path();
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)
                .context("Failed to create database directory")?;
        }

        tracing::info!("Opening database at {}", path.display());
        let conn = Connection::open(&path)
            .context("Failed to open SQLite database")?;

        // Enable WAL mode for better concurrency
        conn.execute_batch("PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON;")?;

        let db = Self {
            conn: Arc::new(Mutex::new(conn)),
        };

        db.run_migrations()?;
        Ok(db)
    }

    /// Run schema migrations.
    fn run_migrations(&self) -> Result<()> {
        let conn = self.conn.lock().unwrap();
        migrations::run(&conn)
    }

    /// Get a lock on the connection for queries.
    pub fn conn(&self) -> std::sync::MutexGuard<'_, Connection> {
        self.conn.lock().unwrap()
    }
}

fn db_path() -> PathBuf {
    let base = std::env::var("APPDATA")
        .unwrap_or_else(|_| ".".into());
    PathBuf::from(base).join("omi").join("omi.db")
}
