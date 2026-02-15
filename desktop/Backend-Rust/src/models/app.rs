// App models - For OMI Apps/Plugins system
// Based on Python backend models/app.py

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

/// App capability types
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum AppCapability {
    Chat,
    Memories,
    Persona,
    ExternalIntegration,
    ProactiveNotification,
}

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

/// App category definition
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppCategory {
    pub id: String,
    pub title: String,
}

/// App capability definition
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppCapabilityDef {
    pub id: String,
    pub title: String,
    pub description: String,
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

/// User's enabled app record
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UserEnabledApp {
    pub app_id: String,
    pub enabled_at: DateTime<Utc>,
}

// ============================================================================
// Request/Response types
// ============================================================================

/// Request to enable/disable an app
#[derive(Debug, Deserialize)]
pub struct ToggleAppRequest {
    pub app_id: String,
}

/// Response for enable/disable
#[derive(Debug, Serialize)]
pub struct ToggleAppResponse {
    pub success: bool,
    pub message: String,
}

/// Request to submit a review
#[derive(Debug, Deserialize)]
pub struct SubmitReviewRequest {
    pub app_id: String,
    pub score: i32,
    pub review: String,
}

/// Query parameters for listing apps
#[derive(Debug, Deserialize)]
pub struct ListAppsQuery {
    #[serde(default)]
    pub capability: Option<String>,
    #[serde(default)]
    pub category: Option<String>,
    #[serde(default = "default_limit")]
    pub limit: usize,
    #[serde(default)]
    pub offset: usize,
}

fn default_limit() -> usize {
    50
}

/// Query parameters for searching apps
#[derive(Debug, Deserialize)]
pub struct SearchAppsQuery {
    pub query: Option<String>,
    pub category: Option<String>,
    pub capability: Option<String>,
    pub rating: Option<i32>,
    #[serde(default)]
    pub my_apps: bool,
    #[serde(default)]
    pub installed_apps: bool,
    #[serde(default = "default_limit")]
    pub limit: usize,
    #[serde(default)]
    pub offset: usize,
}

/// Static app categories (matching Python backend / production API)
pub fn get_app_categories() -> Vec<AppCategory> {
    vec![
        AppCategory { id: "conversation-analysis".to_string(), title: "Conversation Analysis".to_string() },
        AppCategory { id: "personality-emulation".to_string(), title: "Personality Clone".to_string() },
        AppCategory { id: "health-and-wellness".to_string(), title: "Health".to_string() },
        AppCategory { id: "education-and-learning".to_string(), title: "Education".to_string() },
        AppCategory { id: "communication-improvement".to_string(), title: "Communication".to_string() },
        AppCategory { id: "emotional-and-mental-support".to_string(), title: "Emotional Support".to_string() },
        AppCategory { id: "productivity-and-organization".to_string(), title: "Productivity".to_string() },
        AppCategory { id: "entertainment-and-fun".to_string(), title: "Entertainment".to_string() },
        AppCategory { id: "financial".to_string(), title: "Financial".to_string() },
        AppCategory { id: "travel-and-exploration".to_string(), title: "Travel".to_string() },
        AppCategory { id: "safety-and-security".to_string(), title: "Safety".to_string() },
        AppCategory { id: "shopping-and-commerce".to_string(), title: "Shopping".to_string() },
        AppCategory { id: "social-and-relationships".to_string(), title: "Social".to_string() },
        AppCategory { id: "news-and-information".to_string(), title: "News".to_string() },
        AppCategory { id: "utilities-and-tools".to_string(), title: "Utilities".to_string() },
        AppCategory { id: "other".to_string(), title: "Other".to_string() },
    ]
}

/// Static app capabilities
pub fn get_app_capabilities() -> Vec<AppCapabilityDef> {
    vec![
        AppCapabilityDef {
            id: "chat".to_string(),
            title: "Chat".to_string(),
            description: "Interactive chat assistant with custom personality".to_string(),
        },
        AppCapabilityDef {
            id: "memories".to_string(),
            title: "Memories".to_string(),
            description: "Analyze and summarize conversations".to_string(),
        },
        AppCapabilityDef {
            id: "persona".to_string(),
            title: "Persona".to_string(),
            description: "AI personality clone for conversations".to_string(),
        },
        AppCapabilityDef {
            id: "external_integration".to_string(),
            title: "External Integration".to_string(),
            description: "Webhook-based integrations triggered by events".to_string(),
        },
        AppCapabilityDef {
            id: "proactive_notification".to_string(),
            title: "Proactive Notification".to_string(),
            description: "Send notifications to users proactively".to_string(),
        },
    ]
}

/// Get capabilities list for v2/apps grouping (matching Python backend order)
pub fn get_v2_capabilities() -> Vec<CapabilityInfo> {
    vec![
        CapabilityInfo { id: "popular".to_string(), title: "Featured".to_string() },
        CapabilityInfo { id: "external_integration".to_string(), title: "Integrations".to_string() },
        CapabilityInfo { id: "chat".to_string(), title: "Chat Assistants".to_string() },
        CapabilityInfo { id: "memories".to_string(), title: "Summary Apps".to_string() },
        CapabilityInfo { id: "proactive_notification".to_string(), title: "Realtime Notifications".to_string() },
    ]
}

// ============================================================================
// V2 Apps Response Types
// ============================================================================

/// Capability info for v2/apps response
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CapabilityInfo {
    pub id: String,
    pub title: String,
}

/// Pagination metadata for v2/apps response
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PaginationMeta {
    pub total: usize,
    pub count: usize,
    pub offset: usize,
    pub limit: usize,
}

/// A single group in the v2/apps response
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppGroup {
    pub capability: CapabilityInfo,
    pub data: Vec<AppSummary>,
    pub pagination: PaginationMeta,
}

/// Response metadata for v2/apps
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AppsV2Meta {
    pub capabilities: Vec<CapabilityInfo>,
    pub group_count: usize,
    pub limit: usize,
    pub offset: usize,
}

/// Full v2/apps grouped response
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppsV2Response {
    pub groups: Vec<AppGroup>,
    pub meta: AppsV2Meta,
}

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
