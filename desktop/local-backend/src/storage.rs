use std::path::Path;
use std::sync::{Arc, Mutex};

use anyhow::{Context, Result};
use chrono::{DateTime, Utc};
use rusqlite::{params, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

const MIGRATIONS: &[Migration] = &[
    Migration {
        version: 1,
        name: "initial_local_storage",
        sql: r#"
        CREATE TABLE conversations (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            overview TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'open',
            started_at TEXT NOT NULL,
            ended_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted_at TEXT,
            cloud_id TEXT,
            sync_version INTEGER NOT NULL DEFAULT 0,
            sync_state TEXT NOT NULL DEFAULT 'local',
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE INDEX idx_conversations_session_id ON conversations(session_id);
        CREATE INDEX idx_conversations_updated_at ON conversations(updated_at);
        CREATE INDEX idx_conversations_deleted_at ON conversations(deleted_at);

        CREATE TABLE transcript_segments (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            session_id TEXT NOT NULL,
            speaker_id TEXT,
            speaker_label TEXT,
            text TEXT NOT NULL,
            start_ms INTEGER NOT NULL,
            end_ms INTEGER NOT NULL,
            segment_index INTEGER NOT NULL,
            source TEXT NOT NULL DEFAULT 'local',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted_at TEXT,
            cloud_id TEXT,
            sync_version INTEGER NOT NULL DEFAULT 0,
            sync_state TEXT NOT NULL DEFAULT 'local',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            UNIQUE(conversation_id, segment_index)
        );

        CREATE INDEX idx_transcript_segments_conversation ON transcript_segments(conversation_id, segment_index);
        CREATE INDEX idx_transcript_segments_session ON transcript_segments(session_id);

        CREATE TABLE memories (
            id TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            category TEXT,
            conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted_at TEXT,
            cloud_id TEXT,
            sync_version INTEGER NOT NULL DEFAULT 0,
            sync_state TEXT NOT NULL DEFAULT 'local',
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE action_items (
            id TEXT PRIMARY KEY,
            conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'open',
            due_at TEXT,
            completed_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted_at TEXT,
            cloud_id TEXT,
            sync_version INTEGER NOT NULL DEFAULT 0,
            sync_state TEXT NOT NULL DEFAULT 'local',
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE local_settings (
            key TEXT PRIMARY KEY,
            value_json TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted_at TEXT,
            cloud_id TEXT,
            sync_version INTEGER NOT NULL DEFAULT 0,
            sync_state TEXT NOT NULL DEFAULT 'local'
        );

        CREATE TABLE local_profiles (
            id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL DEFAULT '',
            timezone TEXT,
            locale TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted_at TEXT,
            cloud_id TEXT,
            sync_version INTEGER NOT NULL DEFAULT 0,
            sync_state TEXT NOT NULL DEFAULT 'local',
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE processing_jobs (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('queued', 'running', 'completed', 'failed')),
            target_conversation_id TEXT REFERENCES conversations(id) ON DELETE CASCADE,
            retry_count INTEGER NOT NULL DEFAULT 0,
            max_retries INTEGER NOT NULL DEFAULT 3,
            last_error TEXT,
            payload_json TEXT NOT NULL DEFAULT '{}',
            result_json TEXT NOT NULL DEFAULT '{}',
            queued_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            failed_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted_at TEXT,
            cloud_id TEXT,
            sync_version INTEGER NOT NULL DEFAULT 0,
            sync_state TEXT NOT NULL DEFAULT 'local'
        );

        CREATE INDEX idx_processing_jobs_status ON processing_jobs(status, queued_at);
        CREATE INDEX idx_processing_jobs_conversation ON processing_jobs(target_conversation_id);

        CREATE TABLE sync_outbox (
            id TEXT PRIMARY KEY,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            operation TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            attempt_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            next_attempt_at TEXT,
            completed_at TEXT
        );

        CREATE INDEX idx_sync_outbox_status ON sync_outbox(status, next_attempt_at, created_at);
        CREATE INDEX idx_sync_outbox_entity ON sync_outbox(entity_type, entity_id);

        CREATE TABLE local_files (
            id TEXT PRIMARY KEY,
            conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
            kind TEXT NOT NULL,
            path TEXT NOT NULL,
            media_type TEXT,
            byte_size INTEGER,
            checksum TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted_at TEXT,
            cloud_id TEXT,
            sync_version INTEGER NOT NULL DEFAULT 0,
            sync_state TEXT NOT NULL DEFAULT 'local',
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE INDEX idx_local_files_conversation ON local_files(conversation_id);

        CREATE VIRTUAL TABLE conversation_search USING fts5(
            conversation_id UNINDEXED,
            source_type UNINDEXED,
            source_id UNINDEXED,
            title,
            overview,
            transcript_text,
            tokenize = 'unicode61'
        );

        CREATE TRIGGER conversations_ai AFTER INSERT ON conversations BEGIN
            INSERT INTO conversation_search(conversation_id, source_type, source_id, title, overview, transcript_text)
            VALUES (new.id, 'conversation', new.id, new.title, new.overview, '');
        END;

        CREATE TRIGGER conversations_au AFTER UPDATE OF title, overview, deleted_at ON conversations BEGIN
            DELETE FROM conversation_search WHERE source_type = 'conversation' AND source_id = old.id;
            INSERT INTO conversation_search(conversation_id, source_type, source_id, title, overview, transcript_text)
            SELECT new.id, 'conversation', new.id, new.title, new.overview, ''
            WHERE new.deleted_at IS NULL;
        END;

        CREATE TRIGGER conversations_ad AFTER DELETE ON conversations BEGIN
            DELETE FROM conversation_search WHERE conversation_id = old.id;
        END;

        CREATE TRIGGER transcript_segments_ai AFTER INSERT ON transcript_segments BEGIN
            INSERT INTO conversation_search(conversation_id, source_type, source_id, title, overview, transcript_text)
            SELECT new.conversation_id, 'segment', new.id, c.title, c.overview, new.text
            FROM conversations c
            WHERE c.id = new.conversation_id AND new.deleted_at IS NULL AND c.deleted_at IS NULL;
        END;

        CREATE TRIGGER transcript_segments_au AFTER UPDATE OF text, deleted_at ON transcript_segments BEGIN
            DELETE FROM conversation_search WHERE source_type = 'segment' AND source_id = old.id;
            INSERT INTO conversation_search(conversation_id, source_type, source_id, title, overview, transcript_text)
            SELECT new.conversation_id, 'segment', new.id, c.title, c.overview, new.text
            FROM conversations c
            WHERE c.id = new.conversation_id AND new.deleted_at IS NULL AND c.deleted_at IS NULL;
        END;

        CREATE TRIGGER transcript_segments_ad AFTER DELETE ON transcript_segments BEGIN
            DELETE FROM conversation_search WHERE source_type = 'segment' AND source_id = old.id;
        END;
    "#,
    },
    Migration {
        version: 2,
        name: "conversation_starred",
        sql: r#"
        ALTER TABLE conversations ADD COLUMN starred INTEGER NOT NULL DEFAULT 0;
        CREATE INDEX idx_conversations_starred ON conversations(starred, updated_at);
    "#,
    },
];

#[derive(Clone)]
pub struct Store {
    conn: Arc<Mutex<Connection>>,
}

struct Migration {
    version: i64,
    name: &'static str,
    sql: &'static str,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Conversation {
    pub id: String,
    pub session_id: String,
    pub title: String,
    pub overview: String,
    pub status: String,
    pub started_at: DateTime<Utc>,
    pub ended_at: Option<DateTime<Utc>>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    pub deleted_at: Option<DateTime<Utc>>,
    pub cloud_id: Option<String>,
    pub sync_version: i64,
    pub sync_state: String,
    pub metadata_json: String,
    pub starred: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TranscriptSegment {
    pub id: String,
    pub conversation_id: String,
    pub session_id: String,
    pub speaker_id: Option<String>,
    pub speaker_label: Option<String>,
    pub text: String,
    pub start_ms: i64,
    pub end_ms: i64,
    pub segment_index: i64,
    pub source: String,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    pub deleted_at: Option<DateTime<Utc>>,
    pub cloud_id: Option<String>,
    pub sync_version: i64,
    pub sync_state: String,
    pub metadata_json: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SearchResult {
    pub conversation_id: String,
    pub title: String,
    pub overview: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ProcessingJob {
    pub id: String,
    pub kind: String,
    pub status: ProcessingJobStatus,
    pub target_conversation_id: Option<String>,
    pub retry_count: i64,
    pub max_retries: i64,
    pub last_error: Option<String>,
    pub payload_json: String,
    pub result_json: String,
    pub queued_at: DateTime<Utc>,
    pub started_at: Option<DateTime<Utc>>,
    pub completed_at: Option<DateTime<Utc>>,
    pub failed_at: Option<DateTime<Utc>>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    pub deleted_at: Option<DateTime<Utc>>,
    pub cloud_id: Option<String>,
    pub sync_version: i64,
    pub sync_state: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Memory {
    pub id: String,
    pub content: String,
    pub category: Option<String>,
    pub conversation_id: Option<String>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    pub deleted_at: Option<DateTime<Utc>>,
    pub cloud_id: Option<String>,
    pub sync_version: i64,
    pub sync_state: String,
    pub metadata_json: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ActionItem {
    pub id: String,
    pub conversation_id: Option<String>,
    pub title: String,
    pub description: String,
    pub status: String,
    pub due_at: Option<DateTime<Utc>>,
    pub completed_at: Option<DateTime<Utc>>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    pub deleted_at: Option<DateTime<Utc>>,
    pub cloud_id: Option<String>,
    pub sync_version: i64,
    pub sync_state: String,
    pub metadata_json: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct LocalProfile {
    pub id: String,
    pub display_name: String,
    pub timezone: Option<String>,
    pub locale: Option<String>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    pub deleted_at: Option<DateTime<Utc>>,
    pub cloud_id: Option<String>,
    pub sync_version: i64,
    pub sync_state: String,
    pub metadata_json: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct LocalSetting {
    pub key: String,
    pub value_json: String,
    pub updated_at: DateTime<Utc>,
    pub deleted_at: Option<DateTime<Utc>>,
    pub cloud_id: Option<String>,
    pub sync_version: i64,
    pub sync_state: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ProcessingJobStatus {
    Queued,
    Running,
    Completed,
    Failed,
}

impl Store {
    pub fn open(path: impl AsRef<Path>) -> Result<Self> {
        let conn = Connection::open(path.as_ref()).with_context(|| {
            format!("failed to open SQLite store at {}", path.as_ref().display())
        })?;
        configure_connection(&conn)?;
        run_migrations(&conn)?;

        Ok(Self {
            conn: Arc::new(Mutex::new(conn)),
        })
    }

    #[cfg(test)]
    pub(crate) fn open_in_memory() -> Result<Self> {
        let conn = Connection::open_in_memory().context("failed to open in-memory SQLite store")?;
        configure_connection(&conn)?;
        run_migrations(&conn)?;

        Ok(Self {
            conn: Arc::new(Mutex::new(conn)),
        })
    }

    pub fn conversations(&self) -> ConversationRepository {
        ConversationRepository {
            conn: Arc::clone(&self.conn),
        }
    }

    pub fn transcripts(&self) -> TranscriptRepository {
        TranscriptRepository {
            conn: Arc::clone(&self.conn),
        }
    }

    pub fn processing_jobs(&self) -> ProcessingJobRepository {
        ProcessingJobRepository {
            conn: Arc::clone(&self.conn),
        }
    }

    pub fn search(&self) -> SearchRepository {
        SearchRepository {
            conn: Arc::clone(&self.conn),
        }
    }

    pub fn memories(&self) -> MemoryRepository {
        MemoryRepository {
            conn: Arc::clone(&self.conn),
        }
    }

    pub fn action_items(&self) -> ActionItemRepository {
        ActionItemRepository {
            conn: Arc::clone(&self.conn),
        }
    }

    pub fn profile(&self) -> ProfileRepository {
        ProfileRepository {
            conn: Arc::clone(&self.conn),
        }
    }

    pub fn settings(&self) -> SettingsRepository {
        SettingsRepository {
            conn: Arc::clone(&self.conn),
        }
    }
}

pub struct ConversationRepository {
    conn: Arc<Mutex<Connection>>,
}

impl ConversationRepository {
    pub fn create(&self, new: NewConversation) -> Result<Conversation> {
        let now = Utc::now();
        let conversation = Conversation {
            id: new.id,
            session_id: new.session_id,
            title: new.title,
            overview: new.overview,
            status: "open".to_string(),
            started_at: new.started_at.unwrap_or(now),
            ended_at: None,
            created_at: now,
            updated_at: now,
            deleted_at: None,
            cloud_id: None,
            sync_version: 0,
            sync_state: "local".to_string(),
            metadata_json: json_or_empty_object(new.metadata)?,
            starred: false,
        };

        let conn = self.conn.lock().expect("SQLite connection mutex poisoned");
        conn.execute(
            r#"
            INSERT INTO conversations (
                id, session_id, title, overview, status, started_at, ended_at, created_at,
                updated_at, deleted_at, cloud_id, sync_version, sync_state, metadata_json, starred
            )
            VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15)
            "#,
            params![
                conversation.id,
                conversation.session_id,
                conversation.title,
                conversation.overview,
                conversation.status,
                conversation.started_at,
                conversation.ended_at,
                conversation.created_at,
                conversation.updated_at,
                conversation.deleted_at,
                conversation.cloud_id,
                conversation.sync_version,
                conversation.sync_state,
                conversation.metadata_json,
                conversation.starred
            ],
        )
        .context("failed to insert conversation")?;

        Ok(conversation)
    }

    pub fn get(&self, id: &str) -> Result<Option<Conversation>> {
        let conn = self.conn.lock().expect("SQLite connection mutex poisoned");
        conn.query_row(
            r#"
            SELECT id, session_id, title, overview, status, started_at, ended_at, created_at,
                   updated_at, deleted_at, cloud_id, sync_version, sync_state, metadata_json, starred
            FROM conversations
            WHERE id = ?1 AND deleted_at IS NULL
            "#,
            params![id],
            map_conversation,
        )
        .optional()
        .context("failed to fetch conversation")
    }

    pub fn list(&self, limit: i64) -> Result<Vec<Conversation>> {
        self.list_filtered(limit, 0, None, None, None)
    }

    pub fn list_filtered(
        &self,
        limit: i64,
        offset: i64,
        start_date: Option<DateTime<Utc>>,
        end_date: Option<DateTime<Utc>>,
        starred: Option<bool>,
    ) -> Result<Vec<Conversation>> {
        let conn = self.conn.lock().expect("SQLite connection mutex poisoned");
        let mut stmt = conn
            .prepare(
                r#"
                SELECT id, session_id, title, overview, status, started_at, ended_at, created_at,
                       updated_at, deleted_at, cloud_id, sync_version, sync_state, metadata_json, starred
                FROM conversations
                WHERE deleted_at IS NULL
                  AND (?1 IS NULL OR started_at >= ?1)
                  AND (?2 IS NULL OR started_at < ?2)
                  AND (?3 IS NULL OR starred = ?3)
                ORDER BY updated_at DESC
                LIMIT ?4 OFFSET ?5
                "#,
            )
            .context("failed to prepare conversation list query")?;
        let rows = stmt
            .query_map(
                params![
                    start_date,
                    end_date,
                    starred.map(|value| if value { 1 } else { 0 }),
                    limit,
                    offset
                ],
                map_conversation,
            )
            .context("failed to list conversations")?;
        collect_rows(rows)
    }

    pub fn count(&self) -> Result<i64> {
        let conn = self.conn.lock().expect("SQLite connection mutex poisoned");
        conn.query_row(
            "SELECT COUNT(*) FROM conversations WHERE deleted_at IS NULL",
            [],
            |row| row.get(0),
        )
        .context("failed to count conversations")
    }

    pub fn update(&self, id: &str, update: UpdateConversation) -> Result<Option<Conversation>> {
        let Some(mut conversation) = self.get(id)? else {
            return Ok(None);
        };
        if let Some(title) = update.title {
            conversation.title = title;
        }
        if let Some(overview) = update.overview {
            conversation.overview = overview;
        }
        if let Some(status) = update.status {
            conversation.status = status;
        }
        if let Some(ended_at) = update.ended_at {
            conversation.ended_at = ended_at;
        }
        if let Some(metadata) = update.metadata {
            conversation.metadata_json = json_or_empty_object(Some(metadata))?;
        }
        if let Some(starred) = update.starred {
            conversation.starred = starred;
        }
        conversation.updated_at = Utc::now();

        let conn = self.conn.lock().expect("SQLite connection mutex poisoned");
        conn.execute(
            r#"
            UPDATE conversations
            SET title = ?2, overview = ?3, status = ?4, ended_at = ?5, updated_at = ?6,
                metadata_json = ?7, starred = ?8, sync_version = sync_version + 1
            WHERE id = ?1 AND deleted_at IS NULL
            "#,
            params![
                conversation.id,
                conversation.title,
                conversation.overview,
                conversation.status,
                conversation.ended_at,
                conversation.updated_at,
                conversation.metadata_json,
                conversation.starred
            ],
        )
        .context("failed to update conversation")?;

        drop(conn);
        self.get(id)
    }

    pub fn soft_delete(&self, id: &str) -> Result<bool> {
        let now = Utc::now();
        let conn = self.conn.lock().expect("SQLite connection mutex poisoned");
        let changed = conn
            .execute(
                "UPDATE conversations SET deleted_at = ?2, updated_at = ?2 WHERE id = ?1 AND deleted_at IS NULL",
                params![id, now],
            )
            .context("failed to delete conversation")?;
        Ok(changed > 0)
    }
}

pub struct TranscriptRepository {
    conn: Arc<Mutex<Connection>>,
}

impl TranscriptRepository {
    pub fn append(&self, new: NewTranscriptSegment) -> Result<AppendTranscriptResult> {
        if let Some(existing) =
            self.get_by_conversation_index(&new.conversation_id, new.segment_index)?
        {
            return if transcript_matches_new(&existing, &new)? {
                Ok(AppendTranscriptResult::Existing(existing))
            } else {
                Ok(AppendTranscriptResult::Conflict(existing))
            };
        }

        let now = Utc::now();
        let segment = TranscriptSegment {
            id: new.id,
            conversation_id: new.conversation_id,
            session_id: new.session_id,
            speaker_id: new.speaker_id,
            speaker_label: new.speaker_label,
            text: new.text,
            start_ms: new.start_ms,
            end_ms: new.end_ms,
            segment_index: new.segment_index,
            source: new.source.unwrap_or_else(|| "local".to_string()),
            created_at: now,
            updated_at: now,
            deleted_at: None,
            cloud_id: None,
            sync_version: 0,
            sync_state: "local".to_string(),
            metadata_json: json_or_empty_object(new.metadata)?,
        };

        let conn = self.conn.lock().expect("SQLite connection mutex poisoned");
        conn.execute(
            r#"
            INSERT INTO transcript_segments (
                id, conversation_id, session_id, speaker_id, speaker_label, text, start_ms,
                end_ms, segment_index, source, created_at, updated_at, deleted_at, cloud_id,
                sync_version, sync_state, metadata_json
            )
            VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16, ?17)
            "#,
            params![
                segment.id,
                segment.conversation_id,
                segment.session_id,
                segment.speaker_id,
                segment.speaker_label,
                segment.text,
                segment.start_ms,
                segment.end_ms,
                segment.segment_index,
                segment.source,
                segment.created_at,
                segment.updated_at,
                segment.deleted_at,
                segment.cloud_id,
                segment.sync_version,
                segment.sync_state,
                segment.metadata_json
            ],
        )
        .context("failed to insert transcript segment")?;

        Ok(AppendTranscriptResult::Inserted(segment))
    }

    pub fn list_for_conversation(&self, conversation_id: &str) -> Result<Vec<TranscriptSegment>> {
        let conn = self.conn.lock().expect("SQLite connection mutex poisoned");
        let mut stmt = conn
            .prepare(
                r#"
                SELECT id, conversation_id, session_id, speaker_id, speaker_label, text, start_ms,
                       end_ms, segment_index, source, created_at, updated_at, deleted_at, cloud_id,
                       sync_version, sync_state, metadata_json
                FROM transcript_segments
                WHERE conversation_id = ?1 AND deleted_at IS NULL
                ORDER BY segment_index ASC
                "#,
            )
            .context("failed to prepare transcript segment list query")?;

        let rows = stmt
            .query_map(params![conversation_id], map_transcript_segment)
            .context("failed to list transcript segments")?;

        collect_rows(rows)
    }

    pub fn get_by_conversation_index(
        &self,
        conversation_id: &str,
        segment_index: i64,
    ) -> Result<Option<TranscriptSegment>> {
        let conn = self.conn.lock().expect("SQLite connection mutex poisoned");
        conn.query_row(
            r#"
            SELECT id, conversation_id, session_id, speaker_id, speaker_label, text, start_ms,
                   end_ms, segment_index, source, created_at, updated_at, deleted_at, cloud_id,
                   sync_version, sync_state, metadata_json
            FROM transcript_segments
            WHERE conversation_id = ?1 AND segment_index = ?2 AND deleted_at IS NULL
            "#,
            params![conversation_id, segment_index],
            map_transcript_segment,
        )
        .optional()
        .context("failed to fetch transcript segment by index")
    }

    pub fn next_segment_index(&self, conversation_id: &str) -> Result<i64> {
        let conn = self.conn.lock().expect("SQLite connection mutex poisoned");
        conn.query_row(
            "SELECT COALESCE(MAX(segment_index) + 1, 0) FROM transcript_segments WHERE conversation_id = ?1",
            params![conversation_id],
            |row| row.get(0),
        )
        .context("failed to fetch next segment index")
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AppendTranscriptResult {
    Inserted(TranscriptSegment),
    Existing(TranscriptSegment),
    Conflict(TranscriptSegment),
}

fn transcript_matches_new(
    existing: &TranscriptSegment,
    new: &NewTranscriptSegment,
) -> Result<bool> {
    let source = new.source.as_deref().unwrap_or("local");
    let metadata_json = json_or_empty_object(new.metadata.clone())?;
    Ok(existing.id == new.id
        && existing.conversation_id == new.conversation_id
        && existing.session_id == new.session_id
        && existing.speaker_id == new.speaker_id
        && existing.speaker_label == new.speaker_label
        && existing.text == new.text
        && existing.start_ms == new.start_ms
        && existing.end_ms == new.end_ms
        && existing.segment_index == new.segment_index
        && existing.source == source
        && existing.metadata_json == metadata_json)
}

pub struct ProcessingJobRepository {
    conn: Arc<Mutex<Connection>>,
}

impl ProcessingJobRepository {
    pub fn enqueue(&self, new: NewProcessingJob) -> Result<ProcessingJob> {
        let now = Utc::now();
        let job = ProcessingJob {
            id: new.id,
            kind: new.kind,
            status: ProcessingJobStatus::Queued,
            target_conversation_id: new.target_conversation_id,
            retry_count: 0,
            max_retries: new.max_retries.unwrap_or(3),
            last_error: None,
            payload_json: json_or_empty_object(new.payload)?,
            result_json: "{}".to_string(),
            queued_at: now,
            started_at: None,
            completed_at: None,
            failed_at: None,
            created_at: now,
            updated_at: now,
            deleted_at: None,
            cloud_id: None,
            sync_version: 0,
            sync_state: "local".to_string(),
        };

        let conn = self.conn.lock().expect("SQLite connection mutex poisoned");
        conn.execute(
            r#"
            INSERT INTO processing_jobs (
                id, kind, status, target_conversation_id, retry_count, max_retries, last_error,
                payload_json, result_json, queued_at, started_at, completed_at, failed_at,
                created_at, updated_at, deleted_at, cloud_id, sync_version, sync_state
            )
            VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16, ?17, ?18, ?19)
            "#,
            params![
                job.id,
                job.kind,
                job.status.as_str(),
                job.target_conversation_id,
                job.retry_count,
                job.max_retries,
                job.last_error,
                job.payload_json,
                job.result_json,
                job.queued_at,
                job.started_at,
                job.completed_at,
                job.failed_at,
                job.created_at,
                job.updated_at,
                job.deleted_at,
                job.cloud_id,
                job.sync_version,
                job.sync_state
            ],
        )
        .context("failed to enqueue processing job")?;

        Ok(job)
    }

    pub fn get(&self, id: &str) -> Result<Option<ProcessingJob>> {
        let conn = self.conn.lock().expect("SQLite connection mutex poisoned");
        conn.query_row(
            r#"
            SELECT id, kind, status, target_conversation_id, retry_count, max_retries, last_error,
                   payload_json, result_json, queued_at, started_at, completed_at, failed_at,
                   created_at, updated_at, deleted_at, cloud_id, sync_version, sync_state
            FROM processing_jobs
            WHERE id = ?1 AND deleted_at IS NULL
            "#,
            params![id],
            map_processing_job,
        )
        .optional()
        .context("failed to fetch processing job")
    }

    pub fn reusable_for_conversation(
        &self,
        kind: &str,
        conversation_id: &str,
    ) -> Result<Option<ProcessingJob>> {
        let conn = self.conn.lock().expect("SQLite connection mutex poisoned");
        let mut stmt = conn
            .prepare(
                r#"
                SELECT id, kind, status, target_conversation_id, retry_count, max_retries, last_error,
                       payload_json, result_json, queued_at, started_at, completed_at, failed_at,
                       created_at, updated_at, deleted_at, cloud_id, sync_version, sync_state
                FROM processing_jobs
                WHERE kind = ?1
                  AND target_conversation_id = ?2
                  AND deleted_at IS NULL
                  AND (
                    status IN ('queued', 'running')
                    OR (
                      status = 'completed'
                      AND julianday(completed_at) >= COALESCE(
                        (
                          SELECT MAX(julianday(updated_at))
                          FROM transcript_segments
                          WHERE conversation_id = ?2 AND deleted_at IS NULL
                        ),
                        julianday(completed_at)
                      )
                    )
                    OR (
                      status = 'failed'
                      AND retry_count >= max_retries
                      AND julianday(failed_at) >= COALESCE(
                        (
                          SELECT MAX(julianday(updated_at))
                          FROM transcript_segments
                          WHERE conversation_id = ?2 AND deleted_at IS NULL
                        ),
                        julianday(failed_at)
                      )
                    )
                  )
                ORDER BY
                  CASE status
                    WHEN 'running' THEN 0
                    WHEN 'queued' THEN 1
                    WHEN 'failed' THEN 2
                    ELSE 2
                  END,
                  updated_at DESC
                LIMIT 1
                "#,
            )
            .context("failed to prepare reusable processing job query")?;

        stmt.query_row(params![kind, conversation_id], map_processing_job)
            .optional()
            .context("failed to fetch reusable processing job")
    }

    pub fn list(&self) -> Result<Vec<ProcessingJob>> {
        let conn = self.conn.lock().expect("SQLite connection mutex poisoned");
        let mut stmt = conn
            .prepare(
                r#"
                SELECT id, kind, status, target_conversation_id, retry_count, max_retries, last_error,
                       payload_json, result_json, queued_at, started_at, completed_at, failed_at,
                       created_at, updated_at, deleted_at, cloud_id, sync_version, sync_state
                FROM processing_jobs
                WHERE deleted_at IS NULL
                ORDER BY queued_at DESC
                "#,
            )
            .context("failed to prepare processing job list query")?;
        let rows = stmt
            .query_map([], map_processing_job)
            .context("failed to list processing jobs")?;
        collect_rows(rows)
    }

    pub fn claim_next_queued(&self) -> Result<Option<ProcessingJob>> {
        let Some(job) = self.next_queued()? else {
            return Ok(None);
        };
        let now = Utc::now();
        let conn = self.conn.lock().expect("SQLite connection mutex poisoned");
        let changed = conn
            .execute(
                r#"
                UPDATE processing_jobs
                SET status = 'running', started_at = ?2, updated_at = ?2, last_error = NULL
                WHERE id = ?1 AND status = 'queued' AND deleted_at IS NULL
                "#,
                params![job.id, now],
            )
            .context("failed to claim processing job")?;
        drop(conn);

        if changed == 0 {
            Ok(None)
        } else {
            self.get(&job.id)
        }
    }

    pub fn complete(&self, id: &str, result: serde_json::Value) -> Result<Option<ProcessingJob>> {
        let now = Utc::now();
        let result_json =
            serde_json::to_string(&result).context("failed to serialize job result")?;
        let conn = self.conn.lock().expect("SQLite connection mutex poisoned");
        let changed = conn
            .execute(
                r#"
                UPDATE processing_jobs
                SET status = 'completed', result_json = ?2, completed_at = ?3, updated_at = ?3,
                    last_error = NULL, sync_version = sync_version + 1
                WHERE id = ?1 AND deleted_at IS NULL
                "#,
                params![id, result_json, now],
            )
            .context("failed to complete processing job")?;
        drop(conn);

        if changed == 0 {
            Ok(None)
        } else {
            self.get(id)
        }
    }

    pub fn fail_or_requeue(&self, id: &str, error: &str) -> Result<Option<ProcessingJob>> {
        let now = Utc::now();
        let conn = self.conn.lock().expect("SQLite connection mutex poisoned");
        let changed = conn
            .execute(
                r#"
                UPDATE processing_jobs
                SET status = CASE
                        WHEN retry_count + 1 < max_retries THEN 'queued'
                        ELSE 'failed'
                    END,
                    last_error = ?2,
                    failed_at = CASE
                        WHEN retry_count + 1 < max_retries THEN NULL
                        ELSE ?3
                    END,
                    queued_at = CASE
                        WHEN retry_count + 1 < max_retries THEN ?3
                        ELSE queued_at
                    END,
                    started_at = CASE
                        WHEN retry_count + 1 < max_retries THEN NULL
                        ELSE started_at
                    END,
                    updated_at = ?3,
                    retry_count = retry_count + 1,
                    sync_version = sync_version + 1
                WHERE id = ?1 AND deleted_at IS NULL
                "#,
                params![id, error, now],
            )
            .context("failed to fail or requeue processing job")?;
        drop(conn);

        if changed == 0 {
            Ok(None)
        } else {
            self.get(id)
        }
    }

    fn next_queued(&self) -> Result<Option<ProcessingJob>> {
        let conn = self.conn.lock().expect("SQLite connection mutex poisoned");
        conn.query_row(
            r#"
            SELECT id, kind, status, target_conversation_id, retry_count, max_retries, last_error,
                   payload_json, result_json, queued_at, started_at, completed_at, failed_at,
                   created_at, updated_at, deleted_at, cloud_id, sync_version, sync_state
            FROM processing_jobs
            WHERE status = 'queued' AND deleted_at IS NULL
            ORDER BY queued_at ASC
            LIMIT 1
            "#,
            [],
            map_processing_job,
        )
        .optional()
        .context("failed to fetch next queued processing job")
    }
}

pub struct SearchRepository {
    conn: Arc<Mutex<Connection>>,
}

pub struct MemoryRepository {
    conn: Arc<Mutex<Connection>>,
}

impl MemoryRepository {
    pub fn create(&self, new: NewMemory) -> Result<Memory> {
        let now = Utc::now();
        let memory = Memory {
            id: new.id,
            content: new.content,
            category: new.category,
            conversation_id: new.conversation_id,
            created_at: now,
            updated_at: now,
            deleted_at: None,
            cloud_id: None,
            sync_version: 0,
            sync_state: "local".to_string(),
            metadata_json: json_or_empty_object(new.metadata)?,
        };
        let conn = self.conn.lock().expect("SQLite connection mutex poisoned");
        conn.execute(
            r#"
            INSERT INTO memories (
                id, content, category, conversation_id, created_at, updated_at, deleted_at,
                cloud_id, sync_version, sync_state, metadata_json
            )
            VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11)
            "#,
            params![
                memory.id,
                memory.content,
                memory.category,
                memory.conversation_id,
                memory.created_at,
                memory.updated_at,
                memory.deleted_at,
                memory.cloud_id,
                memory.sync_version,
                memory.sync_state,
                memory.metadata_json
            ],
        )
        .context("failed to create memory")?;
        Ok(memory)
    }

    pub fn upsert(&self, new: NewMemory) -> Result<Memory> {
        let now = Utc::now();
        let metadata_json = json_or_empty_object(new.metadata)?;
        let conn = self.conn.lock().expect("SQLite connection mutex poisoned");
        conn.execute(
            r#"
            INSERT INTO memories (
                id, content, category, conversation_id, created_at, updated_at, deleted_at,
                cloud_id, sync_version, sync_state, metadata_json
            )
            VALUES (?1, ?2, ?3, ?4, ?5, ?5, NULL, NULL, 0, 'local', ?6)
            ON CONFLICT(id) DO UPDATE SET
                content = excluded.content,
                category = excluded.category,
                conversation_id = excluded.conversation_id,
                updated_at = excluded.updated_at,
                deleted_at = NULL,
                metadata_json = excluded.metadata_json,
                sync_version = memories.sync_version + 1,
                sync_state = 'local'
            "#,
            params![
                new.id,
                new.content,
                new.category,
                new.conversation_id,
                now,
                metadata_json
            ],
        )
        .context("failed to upsert memory")?;
        drop(conn);
        self.get(&new.id)?
            .ok_or_else(|| anyhow::anyhow!("memory missing after upsert"))
    }

    pub fn soft_delete_local_processing_except(
        &self,
        conversation_id: &str,
        keep_ids: &[String],
    ) -> Result<usize> {
        soft_delete_local_processing_except(&self.conn, "memories", conversation_id, keep_ids)
    }

    pub fn get(&self, id: &str) -> Result<Option<Memory>> {
        let conn = self.conn.lock().expect("SQLite connection mutex poisoned");
        conn.query_row(
            r#"
            SELECT id, content, category, conversation_id, created_at, updated_at, deleted_at,
                   cloud_id, sync_version, sync_state, metadata_json
            FROM memories
            WHERE id = ?1 AND deleted_at IS NULL
            "#,
            params![id],
            map_memory,
        )
        .optional()
        .context("failed to fetch memory")
    }

    pub fn list(&self) -> Result<Vec<Memory>> {
        let conn = self.conn.lock().expect("SQLite connection mutex poisoned");
        let mut stmt = conn
            .prepare(
                r#"
                SELECT id, content, category, conversation_id, created_at, updated_at, deleted_at,
                       cloud_id, sync_version, sync_state, metadata_json
                FROM memories
                WHERE deleted_at IS NULL
                ORDER BY updated_at DESC
                "#,
            )
            .context("failed to prepare memory list query")?;
        let rows = stmt
            .query_map([], map_memory)
            .context("failed to list memories")?;
        collect_rows(rows)
    }

    pub fn update(&self, id: &str, update: UpdateMemory) -> Result<Option<Memory>> {
        let Some(mut memory) = self.get(id)? else {
            return Ok(None);
        };
        if let Some(content) = update.content {
            memory.content = content;
        }
        if let Some(category) = update.category {
            memory.category = category;
        }
        if let Some(conversation_id) = update.conversation_id {
            memory.conversation_id = conversation_id;
        }
        if let Some(metadata) = update.metadata {
            memory.metadata_json = json_or_empty_object(Some(metadata))?;
        }
        memory.updated_at = Utc::now();

        let conn = self.conn.lock().expect("SQLite connection mutex poisoned");
        conn.execute(
            r#"
            UPDATE memories
            SET content = ?2, category = ?3, conversation_id = ?4, updated_at = ?5,
                metadata_json = ?6, sync_version = sync_version + 1
            WHERE id = ?1 AND deleted_at IS NULL
            "#,
            params![
                memory.id,
                memory.content,
                memory.category,
                memory.conversation_id,
                memory.updated_at,
                memory.metadata_json
            ],
        )
        .context("failed to update memory")?;
        drop(conn);
        self.get(id)
    }

    pub fn soft_delete(&self, id: &str) -> Result<bool> {
        soft_delete_by_id(&self.conn, "memories", id, "memory")
    }
}

pub struct ActionItemRepository {
    conn: Arc<Mutex<Connection>>,
}

impl ActionItemRepository {
    pub fn create(&self, new: NewActionItem) -> Result<ActionItem> {
        let now = Utc::now();
        let action_item = ActionItem {
            id: new.id,
            conversation_id: new.conversation_id,
            title: new.title,
            description: new.description.unwrap_or_default(),
            status: new.status.unwrap_or_else(|| "open".to_string()),
            due_at: new.due_at,
            completed_at: None,
            created_at: now,
            updated_at: now,
            deleted_at: None,
            cloud_id: None,
            sync_version: 0,
            sync_state: "local".to_string(),
            metadata_json: json_or_empty_object(new.metadata)?,
        };
        let conn = self.conn.lock().expect("SQLite connection mutex poisoned");
        conn.execute(
            r#"
            INSERT INTO action_items (
                id, conversation_id, title, description, status, due_at, completed_at, created_at,
                updated_at, deleted_at, cloud_id, sync_version, sync_state, metadata_json
            )
            VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14)
            "#,
            params![
                action_item.id,
                action_item.conversation_id,
                action_item.title,
                action_item.description,
                action_item.status,
                action_item.due_at,
                action_item.completed_at,
                action_item.created_at,
                action_item.updated_at,
                action_item.deleted_at,
                action_item.cloud_id,
                action_item.sync_version,
                action_item.sync_state,
                action_item.metadata_json
            ],
        )
        .context("failed to create action item")?;
        Ok(action_item)
    }

    pub fn upsert(&self, new: NewActionItem) -> Result<ActionItem> {
        let now = Utc::now();
        let description = new.description.unwrap_or_default();
        let status = new.status.unwrap_or_else(|| "open".to_string());
        let metadata_json = json_or_empty_object(new.metadata)?;
        let conn = self.conn.lock().expect("SQLite connection mutex poisoned");
        conn.execute(
            r#"
            INSERT INTO action_items (
                id, conversation_id, title, description, status, due_at, completed_at, created_at,
                updated_at, deleted_at, cloud_id, sync_version, sync_state, metadata_json
            )
            VALUES (?1, ?2, ?3, ?4, ?5, ?6, NULL, ?7, ?7, NULL, NULL, 0, 'local', ?8)
            ON CONFLICT(id) DO UPDATE SET
                conversation_id = excluded.conversation_id,
                title = excluded.title,
                description = excluded.description,
                status = excluded.status,
                due_at = excluded.due_at,
                completed_at = CASE
                    WHEN excluded.status = 'completed' THEN COALESCE(action_items.completed_at, excluded.updated_at)
                    ELSE NULL
                END,
                updated_at = excluded.updated_at,
                deleted_at = NULL,
                metadata_json = excluded.metadata_json,
                sync_version = action_items.sync_version + 1,
                sync_state = 'local'
            "#,
            params![
                new.id,
                new.conversation_id,
                new.title,
                description,
                status,
                new.due_at,
                now,
                metadata_json
            ],
        )
        .context("failed to upsert action item")?;
        drop(conn);
        self.get(&new.id)?
            .ok_or_else(|| anyhow::anyhow!("action item missing after upsert"))
    }

    pub fn soft_delete_local_processing_except(
        &self,
        conversation_id: &str,
        keep_ids: &[String],
    ) -> Result<usize> {
        soft_delete_local_processing_except(&self.conn, "action_items", conversation_id, keep_ids)
    }

    pub fn get(&self, id: &str) -> Result<Option<ActionItem>> {
        let conn = self.conn.lock().expect("SQLite connection mutex poisoned");
        conn.query_row(
            r#"
            SELECT id, conversation_id, title, description, status, due_at, completed_at,
                   created_at, updated_at, deleted_at, cloud_id, sync_version, sync_state,
                   metadata_json
            FROM action_items
            WHERE id = ?1 AND deleted_at IS NULL
            "#,
            params![id],
            map_action_item,
        )
        .optional()
        .context("failed to fetch action item")
    }

    pub fn list(&self) -> Result<Vec<ActionItem>> {
        let conn = self.conn.lock().expect("SQLite connection mutex poisoned");
        let mut stmt = conn
            .prepare(
                r#"
                SELECT id, conversation_id, title, description, status, due_at, completed_at,
                       created_at, updated_at, deleted_at, cloud_id, sync_version, sync_state,
                       metadata_json
                FROM action_items
                WHERE deleted_at IS NULL
                ORDER BY updated_at DESC
                "#,
            )
            .context("failed to prepare action item list query")?;
        let rows = stmt
            .query_map([], map_action_item)
            .context("failed to list action items")?;
        collect_rows(rows)
    }

    pub fn update(&self, id: &str, update: UpdateActionItem) -> Result<Option<ActionItem>> {
        let Some(mut action_item) = self.get(id)? else {
            return Ok(None);
        };
        if let Some(title) = update.title {
            action_item.title = title;
        }
        if let Some(description) = update.description {
            action_item.description = description;
        }
        if let Some(status) = update.status {
            action_item.status = status;
            if action_item.status == "completed" && action_item.completed_at.is_none() {
                action_item.completed_at = Some(Utc::now());
            }
        }
        if let Some(due_at) = update.due_at {
            action_item.due_at = due_at;
        }
        if let Some(conversation_id) = update.conversation_id {
            action_item.conversation_id = conversation_id;
        }
        if let Some(metadata) = update.metadata {
            action_item.metadata_json = json_or_empty_object(Some(metadata))?;
        }
        action_item.updated_at = Utc::now();

        let conn = self.conn.lock().expect("SQLite connection mutex poisoned");
        conn.execute(
            r#"
            UPDATE action_items
            SET conversation_id = ?2, title = ?3, description = ?4, status = ?5, due_at = ?6,
                completed_at = ?7, updated_at = ?8, metadata_json = ?9,
                sync_version = sync_version + 1
            WHERE id = ?1 AND deleted_at IS NULL
            "#,
            params![
                action_item.id,
                action_item.conversation_id,
                action_item.title,
                action_item.description,
                action_item.status,
                action_item.due_at,
                action_item.completed_at,
                action_item.updated_at,
                action_item.metadata_json
            ],
        )
        .context("failed to update action item")?;
        drop(conn);
        self.get(id)
    }

    pub fn soft_delete(&self, id: &str) -> Result<bool> {
        soft_delete_by_id(&self.conn, "action_items", id, "action item")
    }
}

pub struct ProfileRepository {
    conn: Arc<Mutex<Connection>>,
}

impl ProfileRepository {
    pub fn get_or_create_default(&self) -> Result<LocalProfile> {
        if let Some(profile) = self.get("local")? {
            return Ok(profile);
        }
        self.upsert(UpdateProfile {
            display_name: Some(String::new()),
            timezone: None,
            locale: None,
            metadata: None,
        })
    }

    pub fn get(&self, id: &str) -> Result<Option<LocalProfile>> {
        let conn = self.conn.lock().expect("SQLite connection mutex poisoned");
        conn.query_row(
            r#"
            SELECT id, display_name, timezone, locale, created_at, updated_at, deleted_at,
                   cloud_id, sync_version, sync_state, metadata_json
            FROM local_profiles
            WHERE id = ?1 AND deleted_at IS NULL
            "#,
            params![id],
            map_local_profile,
        )
        .optional()
        .context("failed to fetch local profile")
    }

    pub fn upsert(&self, update: UpdateProfile) -> Result<LocalProfile> {
        let now = Utc::now();
        let current = self.get("local")?;
        let display_name = update
            .display_name
            .or_else(|| current.as_ref().map(|profile| profile.display_name.clone()))
            .unwrap_or_default();
        let timezone = update.timezone.or_else(|| {
            current
                .as_ref()
                .and_then(|profile| profile.timezone.clone())
        });
        let locale = update
            .locale
            .or_else(|| current.as_ref().and_then(|profile| profile.locale.clone()));
        let metadata_json = match update.metadata {
            Some(metadata) => json_or_empty_object(Some(metadata))?,
            None => current
                .as_ref()
                .map(|profile| profile.metadata_json.clone())
                .unwrap_or_else(|| "{}".to_string()),
        };
        let created_at = current
            .as_ref()
            .map(|profile| profile.created_at)
            .unwrap_or(now);

        let conn = self.conn.lock().expect("SQLite connection mutex poisoned");
        conn.execute(
            r#"
            INSERT INTO local_profiles (
                id, display_name, timezone, locale, created_at, updated_at, deleted_at, cloud_id,
                sync_version, sync_state, metadata_json
            )
            VALUES ('local', ?1, ?2, ?3, ?4, ?5, NULL, NULL, 0, 'local', ?6)
            ON CONFLICT(id) DO UPDATE SET
                display_name = excluded.display_name,
                timezone = excluded.timezone,
                locale = excluded.locale,
                updated_at = excluded.updated_at,
                metadata_json = excluded.metadata_json,
                sync_version = local_profiles.sync_version + 1
            "#,
            params![
                display_name,
                timezone,
                locale,
                created_at,
                now,
                metadata_json
            ],
        )
        .context("failed to upsert local profile")?;
        drop(conn);
        self.get("local")?
            .context("local profile missing after upsert")
    }
}

pub struct SettingsRepository {
    conn: Arc<Mutex<Connection>>,
}

impl SettingsRepository {
    pub fn list(&self) -> Result<Vec<LocalSetting>> {
        let conn = self.conn.lock().expect("SQLite connection mutex poisoned");
        let mut stmt = conn
            .prepare(
                r#"
                SELECT key, value_json, updated_at, deleted_at, cloud_id, sync_version, sync_state
                FROM local_settings
                WHERE deleted_at IS NULL
                ORDER BY key ASC
                "#,
            )
            .context("failed to prepare settings list query")?;
        let rows = stmt
            .query_map([], map_local_setting)
            .context("failed to list settings")?;
        collect_rows(rows)
    }

    pub fn get(&self, key: &str) -> Result<Option<LocalSetting>> {
        let conn = self.conn.lock().expect("SQLite connection mutex poisoned");
        conn.query_row(
            r#"
            SELECT key, value_json, updated_at, deleted_at, cloud_id, sync_version, sync_state
            FROM local_settings
            WHERE key = ?1 AND deleted_at IS NULL
            "#,
            params![key],
            map_local_setting,
        )
        .optional()
        .context("failed to fetch local setting")
    }

    pub fn upsert_many(
        &self,
        values: serde_json::Map<String, serde_json::Value>,
    ) -> Result<Vec<LocalSetting>> {
        let now = Utc::now();
        let conn = self.conn.lock().expect("SQLite connection mutex poisoned");
        for (key, value) in values {
            let value_json =
                serde_json::to_string(&value).context("failed to serialize setting value")?;
            conn.execute(
                r#"
                INSERT INTO local_settings (key, value_json, updated_at, deleted_at, cloud_id, sync_version, sync_state)
                VALUES (?1, ?2, ?3, NULL, NULL, 0, 'local')
                ON CONFLICT(key) DO UPDATE SET
                    value_json = excluded.value_json,
                    updated_at = excluded.updated_at,
                    deleted_at = NULL,
                    sync_version = local_settings.sync_version + 1
                "#,
                params![key, value_json, now],
            )
            .context("failed to upsert local setting")?;
        }
        drop(conn);
        self.list()
    }
}

impl SearchRepository {
    pub fn conversations(&self, query: &str, limit: i64) -> Result<Vec<SearchResult>> {
        let conn = self.conn.lock().expect("SQLite connection mutex poisoned");
        let mut stmt = conn
            .prepare(
                r#"
                SELECT c.id, c.title, c.overview
                FROM conversations c
                JOIN (
                    SELECT DISTINCT conversation_id
                    FROM conversation_search
                    WHERE conversation_search MATCH ?1
                ) matches ON matches.conversation_id = c.id
                WHERE c.deleted_at IS NULL
                ORDER BY c.updated_at DESC
                LIMIT ?2
                "#,
            )
            .context("failed to prepare conversation search query")?;

        let rows = stmt
            .query_map(params![query, limit], |row| {
                Ok(SearchResult {
                    conversation_id: row.get(0)?,
                    title: row.get(1)?,
                    overview: row.get(2)?,
                })
            })
            .context("failed to search conversations")?;

        collect_rows(rows)
    }
}

#[derive(Debug, Clone)]
pub struct NewConversation {
    pub id: String,
    pub session_id: String,
    pub title: String,
    pub overview: String,
    pub started_at: Option<DateTime<Utc>>,
    pub metadata: Option<serde_json::Value>,
}

#[derive(Debug, Clone)]
pub struct NewTranscriptSegment {
    pub id: String,
    pub conversation_id: String,
    pub session_id: String,
    pub speaker_id: Option<String>,
    pub speaker_label: Option<String>,
    pub text: String,
    pub start_ms: i64,
    pub end_ms: i64,
    pub segment_index: i64,
    pub source: Option<String>,
    pub metadata: Option<serde_json::Value>,
}

#[derive(Debug, Clone)]
pub struct NewProcessingJob {
    pub id: String,
    pub kind: String,
    pub target_conversation_id: Option<String>,
    pub max_retries: Option<i64>,
    pub payload: Option<serde_json::Value>,
}

#[derive(Debug, Clone)]
pub struct UpdateConversation {
    pub title: Option<String>,
    pub overview: Option<String>,
    pub status: Option<String>,
    pub ended_at: Option<Option<DateTime<Utc>>>,
    pub metadata: Option<serde_json::Value>,
    pub starred: Option<bool>,
}

#[derive(Debug, Clone)]
pub struct NewMemory {
    pub id: String,
    pub content: String,
    pub category: Option<String>,
    pub conversation_id: Option<String>,
    pub metadata: Option<serde_json::Value>,
}

#[derive(Debug, Clone)]
pub struct UpdateMemory {
    pub content: Option<String>,
    pub category: Option<Option<String>>,
    pub conversation_id: Option<Option<String>>,
    pub metadata: Option<serde_json::Value>,
}

#[derive(Debug, Clone)]
pub struct NewActionItem {
    pub id: String,
    pub conversation_id: Option<String>,
    pub title: String,
    pub description: Option<String>,
    pub status: Option<String>,
    pub due_at: Option<DateTime<Utc>>,
    pub metadata: Option<serde_json::Value>,
}

#[derive(Debug, Clone)]
pub struct UpdateActionItem {
    pub conversation_id: Option<Option<String>>,
    pub title: Option<String>,
    pub description: Option<String>,
    pub status: Option<String>,
    pub due_at: Option<Option<DateTime<Utc>>>,
    pub metadata: Option<serde_json::Value>,
}

#[derive(Debug, Clone)]
pub struct UpdateProfile {
    pub display_name: Option<String>,
    pub timezone: Option<String>,
    pub locale: Option<String>,
    pub metadata: Option<serde_json::Value>,
}

pub fn deterministic_id(prefix: &str, parts: &[&str]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(prefix.as_bytes());
    for part in parts {
        hasher.update([0]);
        hasher.update(part.as_bytes());
    }
    let digest = hasher.finalize();
    format!("{prefix}_{digest:x}")
        .chars()
        .take(prefix.len() + 1 + 32)
        .collect()
}

fn configure_connection(conn: &Connection) -> Result<()> {
    conn.pragma_update(None, "foreign_keys", "ON")
        .context("failed to enable SQLite foreign keys")?;
    conn.pragma_update(None, "journal_mode", "WAL")
        .context("failed to enable SQLite WAL journal mode")?;
    conn.pragma_update(None, "busy_timeout", 5000)
        .context("failed to set SQLite busy timeout")?;
    Ok(())
}

fn run_migrations(conn: &Connection) -> Result<()> {
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )",
        [],
    )
    .context("failed to create schema_migrations table")?;

    for migration in MIGRATIONS {
        let applied = conn
            .query_row(
                "SELECT 1 FROM schema_migrations WHERE version = ?1",
                params![migration.version],
                |_| Ok(()),
            )
            .optional()
            .context("failed to check migration state")?
            .is_some();

        if applied {
            continue;
        }

        let tx = conn
            .unchecked_transaction()
            .context("failed to start migration transaction")?;
        tx.execute_batch(migration.sql)
            .with_context(|| format!("failed to apply migration {}", migration.name))?;
        tx.execute(
            "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?1, ?2, ?3)",
            params![migration.version, migration.name, Utc::now()],
        )
        .context("failed to record migration")?;
        tx.commit().context("failed to commit migration")?;
    }

    Ok(())
}

fn json_or_empty_object(value: Option<serde_json::Value>) -> Result<String> {
    serde_json::to_string(&value.unwrap_or_else(|| serde_json::json!({})))
        .context("failed to serialize JSON metadata")
}

fn collect_rows<T>(
    rows: rusqlite::MappedRows<'_, impl FnMut(&rusqlite::Row<'_>) -> rusqlite::Result<T>>,
) -> Result<Vec<T>> {
    rows.collect::<rusqlite::Result<Vec<_>>>()
        .context("failed to collect SQLite rows")
}

fn map_conversation(row: &rusqlite::Row<'_>) -> rusqlite::Result<Conversation> {
    Ok(Conversation {
        id: row.get(0)?,
        session_id: row.get(1)?,
        title: row.get(2)?,
        overview: row.get(3)?,
        status: row.get(4)?,
        started_at: row.get(5)?,
        ended_at: row.get(6)?,
        created_at: row.get(7)?,
        updated_at: row.get(8)?,
        deleted_at: row.get(9)?,
        cloud_id: row.get(10)?,
        sync_version: row.get(11)?,
        sync_state: row.get(12)?,
        metadata_json: row.get(13)?,
        starred: row.get(14)?,
    })
}

fn map_transcript_segment(row: &rusqlite::Row<'_>) -> rusqlite::Result<TranscriptSegment> {
    Ok(TranscriptSegment {
        id: row.get(0)?,
        conversation_id: row.get(1)?,
        session_id: row.get(2)?,
        speaker_id: row.get(3)?,
        speaker_label: row.get(4)?,
        text: row.get(5)?,
        start_ms: row.get(6)?,
        end_ms: row.get(7)?,
        segment_index: row.get(8)?,
        source: row.get(9)?,
        created_at: row.get(10)?,
        updated_at: row.get(11)?,
        deleted_at: row.get(12)?,
        cloud_id: row.get(13)?,
        sync_version: row.get(14)?,
        sync_state: row.get(15)?,
        metadata_json: row.get(16)?,
    })
}

fn map_processing_job(row: &rusqlite::Row<'_>) -> rusqlite::Result<ProcessingJob> {
    let status: String = row.get(2)?;
    Ok(ProcessingJob {
        id: row.get(0)?,
        kind: row.get(1)?,
        status: ProcessingJobStatus::from_db(&status),
        target_conversation_id: row.get(3)?,
        retry_count: row.get(4)?,
        max_retries: row.get(5)?,
        last_error: row.get(6)?,
        payload_json: row.get(7)?,
        result_json: row.get(8)?,
        queued_at: row.get(9)?,
        started_at: row.get(10)?,
        completed_at: row.get(11)?,
        failed_at: row.get(12)?,
        created_at: row.get(13)?,
        updated_at: row.get(14)?,
        deleted_at: row.get(15)?,
        cloud_id: row.get(16)?,
        sync_version: row.get(17)?,
        sync_state: row.get(18)?,
    })
}

fn map_memory(row: &rusqlite::Row<'_>) -> rusqlite::Result<Memory> {
    Ok(Memory {
        id: row.get(0)?,
        content: row.get(1)?,
        category: row.get(2)?,
        conversation_id: row.get(3)?,
        created_at: row.get(4)?,
        updated_at: row.get(5)?,
        deleted_at: row.get(6)?,
        cloud_id: row.get(7)?,
        sync_version: row.get(8)?,
        sync_state: row.get(9)?,
        metadata_json: row.get(10)?,
    })
}

fn map_action_item(row: &rusqlite::Row<'_>) -> rusqlite::Result<ActionItem> {
    Ok(ActionItem {
        id: row.get(0)?,
        conversation_id: row.get(1)?,
        title: row.get(2)?,
        description: row.get(3)?,
        status: row.get(4)?,
        due_at: row.get(5)?,
        completed_at: row.get(6)?,
        created_at: row.get(7)?,
        updated_at: row.get(8)?,
        deleted_at: row.get(9)?,
        cloud_id: row.get(10)?,
        sync_version: row.get(11)?,
        sync_state: row.get(12)?,
        metadata_json: row.get(13)?,
    })
}

fn map_local_profile(row: &rusqlite::Row<'_>) -> rusqlite::Result<LocalProfile> {
    Ok(LocalProfile {
        id: row.get(0)?,
        display_name: row.get(1)?,
        timezone: row.get(2)?,
        locale: row.get(3)?,
        created_at: row.get(4)?,
        updated_at: row.get(5)?,
        deleted_at: row.get(6)?,
        cloud_id: row.get(7)?,
        sync_version: row.get(8)?,
        sync_state: row.get(9)?,
        metadata_json: row.get(10)?,
    })
}

fn map_local_setting(row: &rusqlite::Row<'_>) -> rusqlite::Result<LocalSetting> {
    Ok(LocalSetting {
        key: row.get(0)?,
        value_json: row.get(1)?,
        updated_at: row.get(2)?,
        deleted_at: row.get(3)?,
        cloud_id: row.get(4)?,
        sync_version: row.get(5)?,
        sync_state: row.get(6)?,
    })
}

fn soft_delete_by_id(
    conn: &Arc<Mutex<Connection>>,
    table: &str,
    id: &str,
    entity_name: &str,
) -> Result<bool> {
    let now = Utc::now();
    let conn = conn.lock().expect("SQLite connection mutex poisoned");
    let changed = conn
        .execute(
            &format!(
                "UPDATE {table} SET deleted_at = ?2, updated_at = ?2 WHERE id = ?1 AND deleted_at IS NULL"
            ),
            params![id, now],
        )
        .with_context(|| format!("failed to delete {entity_name}"))?;
    Ok(changed > 0)
}

fn soft_delete_local_processing_except(
    conn: &Arc<Mutex<Connection>>,
    table: &str,
    conversation_id: &str,
    keep_ids: &[String],
) -> Result<usize> {
    let now = Utc::now();
    let conn = conn.lock().expect("SQLite connection mutex poisoned");
    let keep_ids_json =
        serde_json::to_string(keep_ids).context("failed to serialize local processing ids")?;
    let changed = conn
        .execute(
            &format!(
                r#"
                UPDATE {table}
                SET deleted_at = ?3, updated_at = ?3, sync_version = sync_version + 1
                WHERE conversation_id = ?1
                  AND deleted_at IS NULL
                  AND json_extract(metadata_json, '$.source') = 'local_processing'
                  AND id NOT IN (SELECT value FROM json_each(?2))
                "#
            ),
            params![conversation_id, keep_ids_json, now],
        )
        .with_context(|| format!("failed to delete stale local processing rows from {table}"))?;
    Ok(changed)
}

impl ProcessingJobStatus {
    fn as_str(&self) -> &'static str {
        match self {
            Self::Queued => "queued",
            Self::Running => "running",
            Self::Completed => "completed",
            Self::Failed => "failed",
        }
    }

    fn from_db(value: &str) -> Self {
        match value {
            "running" => Self::Running,
            "completed" => Self::Completed,
            "failed" => Self::Failed,
            _ => Self::Queued,
        }
    }
}

#[cfg(test)]
mod tests {
    use tempfile::tempdir;

    use super::*;

    #[test]
    fn migrations_create_expected_tables_and_pragmas() -> Result<()> {
        let store = Store::open_in_memory()?;
        let conn = store.conn.lock().expect("SQLite connection mutex poisoned");

        let foreign_keys: i64 = conn.query_row("PRAGMA foreign_keys", [], |row| row.get(0))?;
        assert_eq!(foreign_keys, 1);

        for table in [
            "conversations",
            "transcript_segments",
            "memories",
            "action_items",
            "local_settings",
            "local_profiles",
            "processing_jobs",
            "sync_outbox",
            "local_files",
            "conversation_search",
        ] {
            let exists: i64 = conn.query_row(
                "SELECT COUNT(*) FROM sqlite_master WHERE name = ?1",
                params![table],
                |row| row.get(0),
            )?;
            assert_eq!(exists, 1, "missing table {table}");
        }

        Ok(())
    }

    #[test]
    fn conversation_and_segments_persist_after_reopen() -> Result<()> {
        let temp = tempdir()?;
        let db_path = temp.path().join("local.sqlite");
        let conversation_id = deterministic_id("conv", &["session-a"]);

        {
            let store = Store::open(&db_path)?;
            store.conversations().create(NewConversation {
                id: conversation_id.clone(),
                session_id: "session-a".to_string(),
                title: "Planning sync".to_string(),
                overview: "MVP storage discussion".to_string(),
                started_at: None,
                metadata: None,
            })?;
            store.transcripts().append(NewTranscriptSegment {
                id: deterministic_id("seg", &[&conversation_id, "0"]),
                conversation_id: conversation_id.clone(),
                session_id: "session-a".to_string(),
                speaker_id: Some("speaker-1".to_string()),
                speaker_label: Some("Alice".to_string()),
                text: "We need local persistence.".to_string(),
                start_ms: 0,
                end_ms: 1500,
                segment_index: 0,
                source: None,
                metadata: None,
            })?;
        }

        let reopened = Store::open(&db_path)?;
        let conversation = reopened.conversations().get(&conversation_id)?;
        let segments = reopened
            .transcripts()
            .list_for_conversation(&conversation_id)?;

        assert_eq!(
            conversation.expect("conversation should persist").title,
            "Planning sync"
        );
        assert_eq!(segments.len(), 1);
        assert_eq!(segments[0].text, "We need local persistence.");

        Ok(())
    }

    #[test]
    fn duplicate_transcript_append_is_existing_or_conflict() -> Result<()> {
        let store = Store::open_in_memory()?;
        let conversation_id = deterministic_id("conv", &["session-duplicate-segment"]);

        store.conversations().create(NewConversation {
            id: conversation_id.clone(),
            session_id: "session-duplicate-segment".to_string(),
            title: String::new(),
            overview: String::new(),
            started_at: None,
            metadata: None,
        })?;

        let new_segment = NewTranscriptSegment {
            id: deterministic_id("seg", &[&conversation_id, "0"]),
            conversation_id: conversation_id.clone(),
            session_id: "session-duplicate-segment".to_string(),
            speaker_id: Some("speaker-1".to_string()),
            speaker_label: Some("Alice".to_string()),
            text: "Retry-safe transcript append.".to_string(),
            start_ms: 0,
            end_ms: 1200,
            segment_index: 0,
            source: None,
            metadata: Some(serde_json::json!({"source": "test"})),
        };

        assert!(matches!(
            store.transcripts().append(new_segment.clone())?,
            AppendTranscriptResult::Inserted(_)
        ));
        assert!(matches!(
            store.transcripts().append(new_segment)?,
            AppendTranscriptResult::Existing(_)
        ));

        let conflict = store.transcripts().append(NewTranscriptSegment {
            id: deterministic_id("seg", &[&conversation_id, "0"]),
            conversation_id,
            session_id: "session-duplicate-segment".to_string(),
            speaker_id: Some("speaker-1".to_string()),
            speaker_label: Some("Alice".to_string()),
            text: "Different content at the same segment index.".to_string(),
            start_ms: 0,
            end_ms: 1200,
            segment_index: 0,
            source: None,
            metadata: Some(serde_json::json!({"source": "test"})),
        })?;
        assert!(matches!(conflict, AppendTranscriptResult::Conflict(_)));

        Ok(())
    }

    #[test]
    fn conversation_starred_updates_persist() -> Result<()> {
        let store = Store::open_in_memory()?;
        let conversation_id = deterministic_id("conv", &["session-starred"]);

        store.conversations().create(NewConversation {
            id: conversation_id.clone(),
            session_id: "session-starred".to_string(),
            title: "Starred conversation".to_string(),
            overview: String::new(),
            started_at: None,
            metadata: None,
        })?;

        let updated = store
            .conversations()
            .update(
                &conversation_id,
                UpdateConversation {
                    title: None,
                    overview: None,
                    status: None,
                    ended_at: None,
                    metadata: None,
                    starred: Some(true),
                },
            )?
            .expect("conversation should update");

        assert!(updated.starred);
        assert!(
            store
                .conversations()
                .get(&conversation_id)?
                .expect("conversation should persist")
                .starred
        );

        Ok(())
    }

    #[test]
    fn fts_search_matches_conversation_and_transcript_text() -> Result<()> {
        let store = Store::open_in_memory()?;
        let conversation_id = deterministic_id("conv", &["session-search"]);

        store.conversations().create(NewConversation {
            id: conversation_id.clone(),
            session_id: "session-search".to_string(),
            title: "Weekly design review".to_string(),
            overview: "Discuss local backend schema".to_string(),
            started_at: None,
            metadata: None,
        })?;
        store.transcripts().append(NewTranscriptSegment {
            id: deterministic_id("seg", &[&conversation_id, "0"]),
            conversation_id: conversation_id.clone(),
            session_id: "session-search".to_string(),
            speaker_id: None,
            speaker_label: None,
            text: "The transcript mentions vector clocks and durable outbox sync.".to_string(),
            start_ms: 0,
            end_ms: 3000,
            segment_index: 0,
            source: None,
            metadata: None,
        })?;

        let title_results = store.search().conversations("design", 10)?;
        assert_eq!(title_results.len(), 1);
        assert_eq!(title_results[0].conversation_id, conversation_id);

        let transcript_results = store.search().conversations("durable", 10)?;
        assert_eq!(transcript_results.len(), 1);
        assert_eq!(transcript_results[0].title, "Weekly design review");

        Ok(())
    }

    #[test]
    fn processing_jobs_start_queued_with_retry_metadata() -> Result<()> {
        let store = Store::open_in_memory()?;
        let job = store.processing_jobs().enqueue(NewProcessingJob {
            id: deterministic_id("job", &["summarize", "conversation-1"]),
            kind: "summarize_conversation".to_string(),
            target_conversation_id: None,
            max_retries: Some(5),
            payload: Some(serde_json::json!({"conversation_id": "conversation-1"})),
        })?;

        assert_eq!(job.status, ProcessingJobStatus::Queued);
        assert_eq!(job.retry_count, 0);
        assert_eq!(job.max_retries, 5);
        assert!(job.last_error.is_none());

        Ok(())
    }

    #[test]
    fn processing_job_failure_requeues_until_max_retries() -> Result<()> {
        let store = Store::open_in_memory()?;
        store.conversations().create(NewConversation {
            id: "conversation-1".to_string(),
            session_id: "session-retry".to_string(),
            title: String::new(),
            overview: String::new(),
            started_at: None,
            metadata: None,
        })?;
        let repository = store.processing_jobs();
        let enqueued = repository.enqueue(NewProcessingJob {
            id: deterministic_id("job", &["retry", "conversation-1"]),
            kind: "finalize_transcript".to_string(),
            target_conversation_id: Some("conversation-1".to_string()),
            max_retries: Some(2),
            payload: Some(serde_json::json!({"conversation_id": "conversation-1"})),
        })?;

        let claimed = repository
            .claim_next_queued()?
            .expect("queued job should be claimed");
        assert_eq!(claimed.id, enqueued.id);
        assert_eq!(claimed.status, ProcessingJobStatus::Running);

        let retryable = repository
            .fail_or_requeue(&claimed.id, "provider timeout")?
            .expect("job should still exist");
        assert_eq!(retryable.status, ProcessingJobStatus::Queued);
        assert_eq!(retryable.retry_count, 1);
        assert_eq!(retryable.last_error.as_deref(), Some("provider timeout"));
        assert!(retryable.failed_at.is_none());
        assert!(retryable.started_at.is_none());

        let reclaimed = repository
            .claim_next_queued()?
            .expect("retryable job should be claimable again");
        assert_eq!(reclaimed.id, enqueued.id);
        assert_eq!(reclaimed.status, ProcessingJobStatus::Running);
        assert_eq!(reclaimed.retry_count, 1);
        assert!(reclaimed.last_error.is_none());

        let exhausted = repository
            .fail_or_requeue(&reclaimed.id, "provider still unavailable")?
            .expect("job should still exist");
        assert_eq!(exhausted.status, ProcessingJobStatus::Failed);
        assert_eq!(exhausted.retry_count, 2);
        assert_eq!(
            exhausted.last_error.as_deref(),
            Some("provider still unavailable")
        );
        assert!(exhausted.failed_at.is_some());

        Ok(())
    }

    #[test]
    fn exhausted_failed_finalize_job_is_reusable_for_duplicate_finalize() -> Result<()> {
        let store = Store::open_in_memory()?;
        let conversation_id = deterministic_id("conv", &["session-failed-finalize"]);
        store.conversations().create(NewConversation {
            id: conversation_id.clone(),
            session_id: "session-failed-finalize".to_string(),
            title: String::new(),
            overview: String::new(),
            started_at: None,
            metadata: None,
        })?;
        store.processing_jobs().enqueue(NewProcessingJob {
            id: deterministic_id("job", &["failed-finalize", &conversation_id]),
            kind: "finalize_transcript".to_string(),
            target_conversation_id: Some(conversation_id.clone()),
            max_retries: Some(1),
            payload: Some(serde_json::json!({"conversation_id": conversation_id})),
        })?;

        let claimed = store
            .processing_jobs()
            .claim_next_queued()?
            .expect("queued job should be claimed");
        let failed = store
            .processing_jobs()
            .fail_or_requeue(&claimed.id, "exhausted")?
            .expect("job should still exist");
        assert_eq!(failed.status, ProcessingJobStatus::Failed);

        let reusable = store
            .processing_jobs()
            .reusable_for_conversation(
                "finalize_transcript",
                failed.target_conversation_id.as_ref().unwrap(),
            )?
            .expect("failed exhausted job should be reusable");
        assert_eq!(reusable.id, failed.id);
        assert_eq!(reusable.status, ProcessingJobStatus::Failed);

        Ok(())
    }
}
