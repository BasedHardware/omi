use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

/// A recorded conversation session.
#[derive(Debug, Clone, Serialize, Deserialize)]
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
#[derive(Debug, Clone, Serialize, Deserialize)]
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
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Memory {
    pub id: String,
    pub conversation_id: Option<String>,
    pub content: String,
    pub category: Option<String>,
    pub created_at: DateTime<Utc>,
}

/// An action item / task extracted from conversations.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ActionItem {
    pub id: String,
    pub conversation_id: Option<String>,
    pub content: String,
    pub completed: bool,
    pub created_at: DateTime<Utc>,
}
