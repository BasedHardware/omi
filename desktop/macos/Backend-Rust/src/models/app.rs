// App models - For OMI Apps/Plugins system
// Based on Python backend models/app.py

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

/// Trigger events for external integrations
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum TriggerEvent {
    MemoryCreation,
    TranscriptProcessed,
    AudioBytes,
}

/// Actions that apps can perform
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ActionType {
    CreateConversation,
    CreateFacts,
    ReadMemories,
    ReadConversations,
    ReadTasks,
}

/// Notification scopes for proactive notifications
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum NotificationScope {
    UserName,
    UserFacts,
    UserContext,
    UserChat,
}

/// External integration configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExternalIntegration {
    /// When the app is triggered
    pub triggers_on: TriggerEvent,
    /// URL to call when triggered
    pub webhook_url: String,
    /// URL to verify setup completion
    pub setup_completed_url: Option<String>,
    /// Actions the app can perform
    #[serde(default)]
    pub actions: Vec<ActionType>,
}

/// Proactive notification configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProactiveNotification {
    /// Data scopes the app can access
    #[serde(default)]
    pub scopes: Vec<NotificationScope>,
}

/// Chat tool that an app exposes
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChatTool {
    pub name: String,
    pub description: String,
    pub endpoint: String,
    #[serde(default = "default_method")]
    pub method: String,
    #[serde(default)]
    pub parameters: Vec<ChatToolParameter>,
    #[serde(default)]
    pub auth_required: bool,
    pub status_message: Option<String>,
}

fn default_method() -> String {
    "POST".to_string()
}

/// Parameter for a chat tool
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChatToolParameter {
    pub name: String,
    #[serde(rename = "type")]
    pub param_type: String,
    pub description: String,
    #[serde(default)]
    pub required: bool,
}

/// Full App model
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct App {
    pub id: String,
    pub name: String,
    pub description: String,
    /// Icon URL
    pub image: String,
    pub category: String,
    pub author: String,
    pub email: Option<String>,

    /// App capabilities
    #[serde(default)]
    pub capabilities: Vec<String>,

    /// Owner user ID
    pub uid: Option<String>,
    /// Whether the app is approved for public listing
    #[serde(default)]
    pub approved: bool,
    /// Whether the app is private (only visible to owner)
    #[serde(default)]
    pub private: bool,
    /// App status: "under-review", "approved", "rejected"
    #[serde(default = "default_status")]
    pub status: String,

    // Prompts for AI behavior
    pub chat_prompt: Option<String>,
    pub memory_prompt: Option<String>,
    pub persona_prompt: Option<String>,

    // External integration config
    pub external_integration: Option<ExternalIntegration>,

    // Proactive notification config
    pub proactive_notification: Option<ProactiveNotification>,

    // Chat tools
    #[serde(default)]
    pub chat_tools: Vec<ChatTool>,

    // Stats
    #[serde(default)]
    pub installs: i32,
    pub rating_avg: Option<f64>,
    #[serde(default)]
    pub rating_count: i32,

    // Monetization
    #[serde(default)]
    pub is_paid: bool,
    pub price: Option<f64>,
    pub payment_plan: Option<String>,

    // Persona-specific fields
    pub username: Option<String>,
    pub twitter: Option<String>,

    pub created_at: Option<DateTime<Utc>>,

    // Runtime field (not stored in DB)
    #[serde(default)]
    pub enabled: bool,
}

fn default_status() -> String {
    "under-review".to_string()
}

impl App {
    /// Check if app works with chat
    pub fn works_with_chat(&self) -> bool {
        self.capabilities.contains(&"chat".to_string())
            || self.capabilities.contains(&"persona".to_string())
    }

    /// Check if app works with memories/conversations
    pub fn works_with_memories(&self) -> bool {
        self.capabilities.contains(&"memories".to_string())
    }

    /// Check if app has external integration
    pub fn works_externally(&self) -> bool {
        self.capabilities.contains(&"external_integration".to_string())
    }

    /// Check if app can send proactive notifications
    pub fn has_proactive_notifications(&self) -> bool {
        self.capabilities.contains(&"proactive_notification".to_string())
    }
}

/// Lightweight app model for list views (excludes large fields)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppSummary {
    pub id: String,
    pub name: String,
    pub description: String,
    pub image: String,
    pub category: String,
    pub author: String,
    #[serde(default)]
    pub capabilities: Vec<String>,
    #[serde(default)]
    pub approved: bool,
    #[serde(default)]
    pub private: bool,
    #[serde(default)]
    pub installs: i32,
    pub rating_avg: Option<f64>,
    #[serde(default)]
    pub rating_count: i32,
    #[serde(default)]
    pub is_paid: bool,
    pub price: Option<f64>,
    #[serde(default)]
    pub enabled: bool,
    /// True if app has external_integration with non-empty auth_steps
    /// Used for categorizing apps into Integrations vs Notifications sections
    #[serde(default, skip_serializing)]
    pub has_auth_steps: bool,
}

impl From<App> for AppSummary {
    fn from(app: App) -> Self {
        Self {
            id: app.id,
            name: app.name,
            description: app.description,
            image: app.image,
            category: app.category,
            author: app.author,
            capabilities: app.capabilities,
            approved: app.approved,
            private: app.private,
            installs: app.installs,
            rating_avg: app.rating_avg,
            rating_count: app.rating_count,
            is_paid: app.is_paid,
            price: app.price,
            enabled: app.enabled,
            has_auth_steps: false, // Would need to be set from external_integration if available
        }
    }
}

/// App review
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppReview {
    /// User ID who wrote the review
    pub uid: String,
    /// Rating score (1-5)
    pub score: i32,
    /// Review text
    pub review: String,
    /// Developer response
    pub response: Option<String>,
    /// When the review was submitted
    pub rated_at: DateTime<Utc>,
    /// When the review was last edited
    pub edited_at: Option<DateTime<Utc>>,
}

// ============================================================================
// V2 Apps Response Types
// ============================================================================

/// Query parameters for v2/apps
#[derive(Debug, Deserialize)]
#[allow(dead_code)]
pub struct AppsV2Query {
    #[serde(default)]
    pub capability: Option<String>,
    #[serde(default = "default_offset")]
    pub offset: usize,
    #[serde(default = "default_v2_limit")]
    pub limit: usize,
    #[serde(default)]
    pub include_reviews: bool,
}

fn default_offset() -> usize {
    0
}

fn default_v2_limit() -> usize {
    20
}
