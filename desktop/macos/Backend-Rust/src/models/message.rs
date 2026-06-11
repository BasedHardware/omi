// Chat Message models - For chat persistence
// Matches Python backend schema: users/{uid}/messages/{id}

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

/// Chat message as stored in Firestore
/// Path: users/{uid}/messages/{id}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MessageDB {
    /// Unique message ID
    pub id: String,
    /// Message text content
    pub text: String,
    /// When the message was created
    pub created_at: DateTime<Utc>,
    /// Sender: "human" or "ai"
    pub sender: String,
    /// App ID for app-specific chats (null = main Omi chat)
    #[serde(default)]
    pub app_id: Option<String>,
    /// Session ID for grouping related messages
    #[serde(default)]
    pub session_id: Option<String>,
    /// User rating: 1 (thumbs up), -1 (thumbs down), null (no rating)
    #[serde(default)]
    pub rating: Option<i32>,
    /// Whether this message was reported as inappropriate
    #[serde(default)]
    pub reported: bool,
    /// Optional JSON metadata (tool calls, screenshot context, etc.)
    #[serde(default)]
    pub metadata: Option<String>,
}

impl MessageDB {
    /// Create a new message
    pub fn new(
        text: String,
        sender: String,
        app_id: Option<String>,
        session_id: Option<String>,
    ) -> Self {
        Self {
            id: uuid::Uuid::new_v4().to_string(),
            text,
            created_at: Utc::now(),
            sender,
            app_id,
            session_id,
            rating: None,
            reported: false,
            metadata: None,
        }
    }
}
