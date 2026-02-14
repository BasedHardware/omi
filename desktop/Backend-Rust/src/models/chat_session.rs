// Chat Session models - for multi-session chat functionality
// Path: users/{uid}/chat_sessions/{session_id}

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

// =========================================================================
// REQUEST TYPES
// =========================================================================

/// Request to create a new chat session
#[derive(Debug, Clone, Deserialize)]
pub struct CreateChatSessionRequest {
    /// Optional title (will be auto-generated from first message if not provided)
    #[serde(default)]
    pub title: Option<String>,
    /// Optional app ID for app-specific sessions
    #[serde(default)]
    pub app_id: Option<String>,
}

/// Request to update a chat session
#[derive(Debug, Clone, Deserialize)]
pub struct UpdateChatSessionRequest {
    /// New title for the session
    #[serde(default)]
    pub title: Option<String>,
    /// Star/unstar the session
    #[serde(default)]
    pub starred: Option<bool>,
}

/// Query params for getting chat sessions
#[derive(Debug, Clone, Deserialize)]
pub struct GetChatSessionsQuery {
    /// Filter by app ID (null = main Omi chat sessions)
    #[serde(default)]
    pub app_id: Option<String>,
    /// Maximum number of sessions to return
    #[serde(default = "default_limit")]
    pub limit: usize,
    /// Offset for pagination
    #[serde(default)]
    pub offset: usize,
    /// Filter by starred status
    #[serde(default)]
    pub starred: Option<bool>,
}

fn default_limit() -> usize {
    50
}

// =========================================================================
// RESPONSE TYPES
// =========================================================================

/// Simple status response
#[derive(Debug, Clone, Serialize)]
pub struct ChatSessionStatusResponse {
    pub status: String,
}

// =========================================================================
// DATABASE MODEL
// =========================================================================

/// Chat session as stored in Firestore
/// Path: users/{uid}/chat_sessions/{id}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChatSessionDB {
    /// Unique session ID
    pub id: String,
    /// Session title (auto-generated or user-edited)
    pub title: String,
    /// Preview text (first message preview)
    #[serde(default)]
    pub preview: Option<String>,
    /// When the session was created
    pub created_at: DateTime<Utc>,
    /// When the session was last updated (new message)
    pub updated_at: DateTime<Utc>,
    /// App ID for app-specific sessions (null = main Omi chat)
    #[serde(default)]
    pub app_id: Option<String>,
    /// Number of messages in this session
    #[serde(default)]
    pub message_count: i32,
    /// Whether this session is starred
    #[serde(default)]
    pub starred: bool,
}

impl ChatSessionDB {
    /// Create a new chat session
    pub fn new(title: Option<String>, app_id: Option<String>) -> Self {
        let now = Utc::now();
        Self {
            id: uuid::Uuid::new_v4().to_string(),
            title: title.unwrap_or_else(|| "New Chat".to_string()),
            preview: None,
            created_at: now,
            updated_at: now,
            app_id,
            message_count: 0,
            starred: false,
        }
    }
}
