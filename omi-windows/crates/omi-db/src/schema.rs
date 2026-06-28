use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

/// A recorded conversation session.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Conversation {
    pub id: String,
    pub title: Option<String>,
    pub started_at: DateTime<Utc>,
    pub ended_at: Option<DateTime<Utc>>,
    pub duration_secs: f64,
    pub status: String, // "recording", "completed", "processing"
    pub summary: Option<String>,
}

/// A transcription segment within a conversation.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Segment {
    pub id: String,
    pub conversation_id: String,
    pub speaker: i32,
    pub text: String,
    pub start_time: f64,
    pub end_time: f64,
    pub is_final: bool,
    pub created_at: DateTime<Utc>,
}

/// An extracted memory from conversations.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Memory {
    pub id: String,
    pub conversation_id: Option<String>,
    pub content: String,
    pub category: Option<String>,
    pub created_at: DateTime<Utc>,
}

/// A captured screenshot with OCR text.
#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct Screenshot {
    pub id: String,
    pub captured_at: chrono::DateTime<chrono::Utc>,
    pub app_name: Option<String>,
    pub window_title: Option<String>,
    pub ocr_text: Option<String>,
    pub thumbnail_path: Option<String>,
}

/// An action item / task extracted from conversations.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ActionItem {
    pub id: String,
    pub conversation_id: Option<String>,
    pub content: String,
    pub completed: bool,
    pub created_at: DateTime<Utc>,
}

/// A clipboard entry captured by the clipboard watcher.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ClipboardEntry {
    pub id: String,
    pub content: String,
    pub content_type: String,
    pub source_app: Option<String>,
    pub captured_at: DateTime<Utc>,
}

/// An indexed file from the filesystem.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct IndexedFile {
    pub id: String,
    pub file_path: String,
    pub file_name: String,
    pub extension: Option<String>,
    pub size_bytes: i64,
    pub modified_at: DateTime<Utc>,
    pub indexed_at: DateTime<Utc>,
}

/// A daily recap summary.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct DailyRecap {
    pub id: String,
    pub date: String,
    pub summary: String,
    pub stats_json: Option<String>,
    pub created_at: DateTime<Utc>,
}

/// A user goal with progress tracking.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Goal {
    pub id: String,
    pub content: String,
    pub status: String,
    pub progress_pct: i32,
    pub created_at: DateTime<Utc>,
    pub completed_at: Option<DateTime<Utc>>,
}
