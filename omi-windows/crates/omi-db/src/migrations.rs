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

    if current < 4 {
        tracing::info!("Running migration v4: clipboard_entries");
        conn.execute_batch(MIGRATION_V4)?;
        conn.execute("INSERT INTO schema_version (version) VALUES (4)", [])?;
    }

    if current < 5 {
        tracing::info!("Running migration v5: indexed_files");
        conn.execute_batch(MIGRATION_V5)?;
        conn.execute("INSERT INTO schema_version (version) VALUES (5)", [])?;
    }

    if current < 6 {
        tracing::info!("Running migration v6: daily_recaps + goals");
        conn.execute_batch(MIGRATION_V6)?;
        conn.execute("INSERT INTO schema_version (version) VALUES (6)", [])?;
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

const MIGRATION_V4: &str = "
CREATE TABLE IF NOT EXISTS clipboard_entries (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    content_type TEXT NOT NULL DEFAULT 'text',
    source_app TEXT,
    captured_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_clipboard_captured ON clipboard_entries(captured_at DESC);

CREATE VIRTUAL TABLE IF NOT EXISTS clipboard_fts USING fts5(
    id UNINDEXED,
    content,
    source_app,
    content_rowid='rowid'
);
";

const MIGRATION_V5: &str = "
CREATE TABLE IF NOT EXISTS indexed_files (
    id TEXT PRIMARY KEY,
    file_path TEXT NOT NULL UNIQUE,
    file_name TEXT NOT NULL,
    extension TEXT,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    modified_at TEXT NOT NULL,
    indexed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_files_modified ON indexed_files(modified_at DESC);

CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5(
    id UNINDEXED,
    file_name,
    file_path,
    extension,
    content_rowid='rowid'
);
";

const MIGRATION_V6: &str = "
CREATE TABLE IF NOT EXISTS daily_recaps (
    id TEXT PRIMARY KEY,
    date TEXT NOT NULL UNIQUE,
    summary TEXT NOT NULL,
    stats_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS goals (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    progress_pct INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_goals_status ON goals(status);
";
