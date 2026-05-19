use anyhow::Result;
use rusqlite::Connection;

/// Run all pending migrations.
pub fn run(conn: &Connection) -> Result<()> {
    conn.execute_batch(
        "CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER NOT NULL
        );"
    )?;

    let current: i64 = conn
        .query_row(
            "SELECT COALESCE(MAX(version), 0) FROM schema_version",
            [],
            |row| row.get(0),
        )
        .unwrap_or(0);

    if current < 1 {
        tracing::info!("Running migration v1: conversations + segments");
        conn.execute_batch(MIGRATION_V1)?;
        conn.execute("INSERT INTO schema_version (version) VALUES (1)", [])?;
    }

    if current < 2 {
        tracing::info!("Running migration v2: memories + action_items");
        conn.execute_batch(MIGRATION_V2)?;
        conn.execute("INSERT INTO schema_version (version) VALUES (2)", [])?;
    }

    if current < 3 {
        tracing::info!("Running migration v3: screenshots");
        conn.execute_batch(MIGRATION_V3)?;
        conn.execute("INSERT INTO schema_version (version) VALUES (3)", [])?;
    }

    Ok(())
}

const MIGRATION_V1: &str = "
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    duration_secs REAL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'recording',
    summary TEXT
);

CREATE TABLE IF NOT EXISTS segments (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    speaker INTEGER NOT NULL DEFAULT 0,
    text TEXT NOT NULL,
    start_time REAL NOT NULL,
    end_time REAL NOT NULL,
    is_final INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_segments_conversation ON segments(conversation_id);
";

const MIGRATION_V3: &str = "
CREATE TABLE IF NOT EXISTS screenshots (
    id TEXT PRIMARY KEY,
    captured_at TEXT NOT NULL DEFAULT (datetime('now')),
    app_name TEXT,
    window_title TEXT,
    ocr_text TEXT,
    thumbnail_path TEXT
);

CREATE INDEX IF NOT EXISTS idx_screenshots_captured ON screenshots(captured_at DESC);

CREATE VIRTUAL TABLE IF NOT EXISTS screenshots_fts USING fts5(
    id UNINDEXED,
    ocr_text,
    app_name,
    window_title,
    content='screenshots',
    content_rowid='rowid'
);
";

const MIGRATION_V2: &str = "
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
    content TEXT NOT NULL,
    category TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS action_items (
    id TEXT PRIMARY KEY,
    conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
    content TEXT NOT NULL,
    completed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
";
