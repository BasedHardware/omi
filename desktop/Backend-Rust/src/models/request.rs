// API Request/Response models - Copied from Python backend (models.py)

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

use super::TranscriptSegment;

/// Request to create a conversation from transcript segments
/// Copied from Python CreateConversationRequest
#[derive(Debug, Clone, Deserialize)]
pub struct CreateConversationRequest {
    pub transcript_segments: Vec<TranscriptSegment>,
    pub started_at: DateTime<Utc>,
    pub finished_at: DateTime<Utc>,
    #[serde(default = "default_language")]
    pub language: String,
    #[serde(default = "default_timezone")]
    pub timezone: String,
    /// Name of the input device (microphone) used for recording
    pub input_device_name: Option<String>,
}

fn default_language() -> String {
    "en".to_string()
}

fn default_timezone() -> String {
    "UTC".to_string()
}

/// Response after creating a conversation
/// Copied from Python CreateConversationResponse
#[derive(Debug, Clone, Serialize)]
pub struct CreateConversationResponse {
    pub id: String,
    pub status: String,
    pub discarded: bool,
}
