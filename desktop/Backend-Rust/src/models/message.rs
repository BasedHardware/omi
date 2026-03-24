// Chat Message models - For chat persistence
// Matches Python backend schema: users/{uid}/messages/{id}

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

// =========================================================================
// REQUEST TYPES
// =========================================================================

/// Request to save a chat message
#[derive(Debug, Clone, Deserialize)]
pub struct SaveMessageRequest {
    /// Message text content
    pub text: String,
    /// Sender: "human" or "ai"
    pub sender: String,
    /// Optional app ID for app-specific chats
    #[serde(default)]
    pub app_id: Option<String>,
    /// Optional session ID for grouping messages
    #[serde(default)]
    pub session_id: Option<String>,
    /// Optional JSON metadata (e.g. tool calls, screenshot context)
    #[serde(default)]
    pub metadata: Option<String>,
}

/// Query params for getting messages
#[derive(Debug, Clone, Deserialize)]
pub struct GetMessagesQuery {
    /// Filter by app ID (null = main Omi chat)
    #[serde(default)]
    pub app_id: Option<String>,
    /// Filter by session ID
    #[serde(default)]
    pub session_id: Option<String>,
    /// Maximum number of messages to return
    #[serde(default = "default_limit")]
    pub limit: usize,
    /// Offset for pagination
    #[serde(default)]
    pub offset: usize,
}

/// Query params for deleting messages
#[derive(Debug, Clone, Deserialize)]
pub struct DeleteMessagesQuery {
    /// Filter by app ID (null = delete main Omi chat)
    #[serde(default)]
    pub app_id: Option<String>,
}

/// Request to rate a message
#[derive(Debug, Clone, Deserialize)]
pub struct RateMessageRequest {
    /// Rating: 1 (thumbs up), -1 (thumbs down), null (clear rating)
    pub rating: Option<i32>,
}

fn default_limit() -> usize {
    100
}

// =========================================================================
// RESPONSE TYPES
// =========================================================================

/// Response for successful message save
#[derive(Debug, Clone, Serialize)]
pub struct SaveMessageResponse {
    pub id: String,
    pub created_at: DateTime<Utc>,
}

/// Simple status response
#[derive(Debug, Clone, Serialize)]
pub struct MessageStatusResponse {
    pub status: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub deleted_count: Option<usize>,
}

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
