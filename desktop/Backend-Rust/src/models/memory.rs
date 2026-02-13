// Memory models - Copied from Python backend (models.py, database.py)

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

use super::category::MemoryCategory;

// =========================================================================
// REQUEST TYPES
// =========================================================================

/// Request to create a new memory (manual or extracted)
#[derive(Debug, Clone, Deserialize)]
pub struct CreateMemoryRequest {
    pub content: String,
    #[serde(default = "default_visibility")]
    pub visibility: String,
    /// Optional category (defaults to manual for manual creation)
    pub category: Option<MemoryCategory>,
    /// AI confidence score (0.0 - 1.0)
    pub confidence: Option<f64>,
    /// App where the memory was extracted from
    pub source_app: Option<String>,
    /// Summary of the context when memory was generated
    pub context_summary: Option<String>,
    /// Tags for filtering (e.g., ["tips", "productivity"])
    #[serde(default)]
    pub tags: Vec<String>,
    /// Reasoning behind the memory/tip (from advice system)
    pub reasoning: Option<String>,
    /// Description of user's activity when memory was generated
    pub current_activity: Option<String>,
    /// Source type (e.g., "screenshot", "desktop", "omi")
    pub source: Option<String>,
    /// Window title when memory was extracted
    pub window_title: Option<String>,
}

/// Request to edit a memory's content
#[derive(Debug, Clone, Deserialize)]
pub struct EditMemoryRequest {
    pub value: String,
}

/// Request to update a memory's visibility
#[derive(Debug, Clone, Deserialize)]
pub struct UpdateVisibilityRequest {
    pub value: String,
}

/// Request to review/approve a memory
#[derive(Debug, Clone, Deserialize)]
pub struct ReviewMemoryRequest {
    pub value: bool,
}

/// Request to update memory read/dismissed status
#[derive(Debug, Clone, Deserialize)]
pub struct UpdateMemoryReadRequest {
    /// Mark as read
    pub is_read: Option<bool>,
    /// Mark as dismissed/archived
    pub is_dismissed: Option<bool>,
}

/// Query parameters for getting memories
#[derive(Debug, Clone, Deserialize)]
pub struct GetMemoriesQuery {
    #[serde(default = "default_limit")]
    pub limit: usize,
    #[serde(default)]
    pub offset: usize,
    /// Filter by category
    pub category: Option<String>,
    /// Filter by tags (comma-separated list, e.g., "tips,productivity")
    pub tags: Option<String>,
    /// Include dismissed memories (default: false)
    #[serde(default)]
    pub include_dismissed: bool,
}

fn default_limit() -> usize {
    5000  // Match Python backend behavior for first page
}

// =========================================================================
// RESPONSE TYPES
// =========================================================================

/// Response for successful memory creation
#[derive(Debug, Clone, Serialize)]
pub struct CreateMemoryResponse {
    pub id: String,
    pub message: String,
}

/// Simple status response
#[derive(Debug, Clone, Serialize)]
pub struct MemoryStatusResponse {
    pub status: String,
}

/// A memory extracted from conversation - long-term knowledge about the user
/// Copied from Python Memory model
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Memory {
    /// The memory content (max 15 words)
    pub content: String,

    /// The category of the memory
    #[serde(default)]
    pub category: MemoryCategory,

    /// Tags for filtering (e.g., ["tips", "productivity"])
    #[serde(default)]
    pub tags: Vec<String>,
}

/// Memory as stored in Firestore
/// Copied from Python MemoryDB model
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryDB {
    pub id: String,
    pub uid: String,
    pub content: String,
    pub category: MemoryCategory,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    pub conversation_id: Option<String>,
    #[serde(default)]
    pub reviewed: bool,
    pub user_review: Option<bool>,
    #[serde(default = "default_visibility_field")]
    pub visibility: String,
    #[serde(default)]
    pub manually_added: bool,
    /// Scoring string for sorting: "{manual_boost}_{category_boost}_{timestamp}"
    pub scoring: Option<String>,
    /// Source device (enriched from linked conversation, not stored in Firestore)
    #[serde(skip_deserializing)]
    pub source: Option<String>,
    /// Input device name (microphone) - enriched from linked conversation for desktop source
    #[serde(skip_deserializing)]
    pub input_device_name: Option<String>,
    /// AI confidence score (0.0 - 1.0) - for extracted memories
    #[serde(default)]
    pub confidence: Option<f64>,
    /// App where the memory was extracted from
    pub source_app: Option<String>,
    /// Summary of the context when memory was generated
    pub context_summary: Option<String>,
    /// Whether the user has read this memory
    #[serde(default)]
    pub is_read: bool,
    /// Whether the memory has been dismissed/archived
    #[serde(default)]
    pub is_dismissed: bool,
    /// Tags for filtering (e.g., ["tips", "productivity"])
    #[serde(default)]
    pub tags: Vec<String>,
    /// Reasoning behind the memory/tip (from advice system)
    pub reasoning: Option<String>,
    /// Description of user's activity when memory was generated
    pub current_activity: Option<String>,
    /// Window title when memory was extracted
    pub window_title: Option<String>,
}

fn default_visibility() -> String {
    "private".to_string()
}

fn default_visibility_field() -> String {
    "private".to_string()
}

impl MemoryDB {
    /// Calculate memory scoring for sorting
    /// Format: "{manual_boost}_{category_boost}_{timestamp}"
    /// Higher scores appear first when sorted descending
    /// Copied from Python _calculate_memory_score
    pub fn calculate_scoring(
        category: &MemoryCategory,
        created_at: &DateTime<Utc>,
        manually_added: bool,
    ) -> String {
        let manual_boost = if manually_added { 1 } else { 0 };

        let category_boost = match category {
            MemoryCategory::Interesting => 1,
            MemoryCategory::System => 0,
            MemoryCategory::Manual => 1,
            // Legacy categories - treat as system
            MemoryCategory::Core | MemoryCategory::Hobbies |
            MemoryCategory::Lifestyle | MemoryCategory::Interests => 0,
        };
        let cat_boost = 999 - category_boost;

        let timestamp = created_at.timestamp();

        format!("{:02}_{:03}_{:010}", manual_boost, cat_boost, timestamp)
    }
}
