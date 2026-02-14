// Conversation models - Copied from Python backend (models.py)

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

use super::category::Category;

/// A segment of transcribed speech
/// Copied from Python TranscriptSegment
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TranscriptSegment {
    pub text: String,
    #[serde(default = "default_speaker")]
    pub speaker: String,
    #[serde(default)]
    pub speaker_id: i32,
    #[serde(default)]
    pub is_user: bool,
    #[serde(default)]
    pub person_id: Option<String>,
    #[serde(default)]
    pub start: f64,
    #[serde(default)]
    pub end: f64,
}

fn default_speaker() -> String {
    "SPEAKER_00".to_string()
}

impl TranscriptSegment {
    /// Convert segments to transcript text for LLM processing
    /// Copied from Python segments_to_transcript_text
    pub fn to_transcript_text(segments: &[TranscriptSegment]) -> String {
        segments
            .iter()
            .map(|segment| {
                let speaker_name = if segment.is_user {
                    "User".to_string()
                } else {
                    format!("Speaker {}", segment.speaker_id)
                };
                format!("{}: {}", speaker_name, segment.text)
            })
            .collect::<Vec<_>>()
            .join("\n\n")
    }
}

/// An action item extracted from conversation
/// Copied from Python ActionItem
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ActionItem {
    /// The action item to be completed
    pub description: String,
    #[serde(default)]
    pub completed: bool,
    /// When the action item is due (ISO 8601 UTC)
    pub due_at: Option<DateTime<Utc>>,
}

/// An event extracted from conversation
/// Copied from Python Event
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Event {
    /// The title of the event
    pub title: String,
    /// A brief description of the event
    #[serde(default)]
    pub description: String,
    /// The start date and time of the event (UTC)
    pub start: DateTime<Utc>,
    /// The duration of the event in minutes
    #[serde(default = "default_duration")]
    pub duration: i32,
}

fn default_duration() -> i32 {
    30
}

/// Structured data extracted from conversation by LLM
/// Copied from Python Structured
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Structured {
    /// A title/name for this conversation
    #[serde(default)]
    pub title: String,
    /// A brief overview of the conversation
    #[serde(default)]
    pub overview: String,
    /// An emoji to represent the conversation
    #[serde(default = "default_emoji")]
    pub emoji: String,
    /// A category for this conversation
    #[serde(default)]
    pub category: Category,
    /// Action items from the conversation
    #[serde(default)]
    pub action_items: Vec<ActionItem>,
    /// Events extracted from the conversation
    #[serde(default)]
    pub events: Vec<Event>,
}

fn default_emoji() -> String {
    "🧠".to_string()
}

/// Conversation status
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ConversationStatus {
    InProgress,
    Processing,
    Merging,
    Completed,
    Failed,
}

impl Default for ConversationStatus {
    fn default() -> Self {
        ConversationStatus::Completed
    }
}

/// Conversation source (what device/app created it)
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ConversationSource {
    Desktop,
    Phone,
    Omi,
    Friend,
    Workflow,
    Openglass,
    Screenpipe,
    Sdcard,
    Fieldy,
    Bee,
    Xor,
    Frame,
    FriendCom,
    AppleWatch,
    Limitless,
    Plaud,
    // Added for Python compatibility
    ExternalIntegration,
    Onboarding,
    #[serde(other)]
    Unknown,
}

impl Default for ConversationSource {
    fn default() -> Self {
        ConversationSource::Desktop
    }
}

/// App processing result stored with a conversation
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct AppResult {
    pub app_id: Option<String>,
    pub content: String,
}

/// Geolocation data for a conversation
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Geolocation {
    pub google_place_id: Option<String>,
    pub latitude: f64,
    pub longitude: f64,
    pub address: Option<String>,
    pub location_type: Option<String>,
}

/// Photo attached to a conversation
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConversationPhoto {
    pub id: Option<String>,
    pub base64: String,
    pub description: Option<String>,
    pub created_at: DateTime<Utc>,
    #[serde(default)]
    pub discarded: bool,
}

/// Full conversation document as stored in Firestore
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Conversation {
    pub id: String,
    pub created_at: DateTime<Utc>,
    pub started_at: DateTime<Utc>,
    pub finished_at: DateTime<Utc>,
    #[serde(default)]
    pub source: ConversationSource,
    #[serde(default)]
    pub language: String,
    #[serde(default)]
    pub status: ConversationStatus,
    #[serde(default)]
    pub discarded: bool,
    #[serde(default)]
    pub deleted: bool,
    #[serde(default)]
    pub starred: bool,
    #[serde(default)]
    pub is_locked: bool,
    #[serde(default)]
    pub folder_id: Option<String>,
    pub structured: Structured,
    #[serde(default)]
    pub transcript_segments: Vec<TranscriptSegment>,
    #[serde(default)]
    pub apps_results: Vec<AppResult>,
    /// Geolocation data (from Python backend)
    #[serde(default)]
    pub geolocation: Option<Geolocation>,
    /// Photos attached to conversation (from Python backend)
    #[serde(default)]
    pub photos: Vec<ConversationPhoto>,
    /// Name of input device (microphone) used for recording
    #[serde(default)]
    pub input_device_name: Option<String>,
}
