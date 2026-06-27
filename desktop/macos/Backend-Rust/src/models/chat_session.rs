// Chat Session models - for multi-session chat functionality
// Path: users/{uid}/chat_sessions/{session_id}

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

// =========================================================================
// REQUEST TYPES
// =========================================================================

// =========================================================================
// RESPONSE TYPES
// =========================================================================

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
