// Action Item models - standalone action items stored in Firestore
// Path: users/{uid}/action_items/{item_id}

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

/// Action item stored in Firestore subcollection
/// Different from conversation.ActionItem which is embedded in conversation structured data
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ActionItemDB {
    /// Document ID
    pub id: String,
    /// The action item description
    pub description: String,
    /// Whether the action item has been completed
    #[serde(default)]
    pub completed: bool,
    /// When the action item was created
    pub created_at: DateTime<Utc>,
    /// When the action item was last updated
    pub updated_at: Option<DateTime<Utc>>,
    /// When the action item is due
    pub due_at: Option<DateTime<Utc>>,
    /// When the action item was completed
    pub completed_at: Option<DateTime<Utc>>,
    /// The conversation this action item was extracted from
    pub conversation_id: Option<String>,
    /// Source of the action item: "screenshot", "transcription:omi", "transcription:desktop", "manual"
    #[serde(default)]
    pub source: Option<String>,
    /// Priority: "high", "medium", "low"
    #[serde(default)]
    pub priority: Option<String>,
    /// JSON metadata: {"source_app": "Safari", "confidence": 0.85}
    #[serde(default)]
    pub metadata: Option<String>,
    /// Soft-delete: true if this task has been deleted
    #[serde(default)]
    pub deleted: Option<bool>,
    /// Who deleted: "user", "ai_dedup"
    #[serde(default)]
    pub deleted_by: Option<String>,
    /// When the task was soft-deleted
    #[serde(default)]
    pub deleted_at: Option<DateTime<Utc>>,
    /// AI reason for deletion (dedup explanation)
    #[serde(default)]
    pub deleted_reason: Option<String>,
    /// ID of the task that was kept instead of this one
    #[serde(default)]
    pub kept_task_id: Option<String>,
    /// Category: "work", "personal", "health", "finance", "education", "shopping", "social", "travel", "home", "other"
    #[serde(default)]
    pub category: Option<String>,
    /// ID of the goal this task is linked to
    #[serde(default)]
    pub goal_id: Option<String>,
    /// Relevance score for prioritization (lower = more relevant)
    #[serde(default)]
    pub relevance_score: Option<i32>,
    /// Sort order within category (lower = higher position)
    #[serde(default)]
    pub sort_order: Option<i32>,
    /// Indent level (0-3)
    #[serde(default)]
    pub indent_level: Option<i32>,
    /// Whether this task was promoted from staged_tasks
    #[serde(default)]
    pub from_staged: Option<bool>,
    /// Recurrence rule: "daily", "weekdays", "weekly", "biweekly", "monthly"
    #[serde(default)]
    pub recurrence_rule: Option<String>,
    /// ID of original parent task in recurrence chain
    #[serde(default)]
    pub recurrence_parent_id: Option<String>,
}

/// Request body for updating an action item
#[derive(Debug, Clone, Deserialize)]
pub struct UpdateActionItemRequest {
    /// New completed status
    pub completed: Option<bool>,
    /// New description
    pub description: Option<String>,
    /// New due date
    pub due_at: Option<DateTime<Utc>>,
    /// New priority: "high", "medium", "low"
    pub priority: Option<String>,
    /// New category: "work", "personal", "health", etc.
    pub category: Option<String>,
    /// Link to a goal
    pub goal_id: Option<String>,
    /// Relevance score for prioritization
    pub relevance_score: Option<i32>,
    /// Sort order within category
    pub sort_order: Option<i32>,
    /// Indent level (0-3)
    pub indent_level: Option<i32>,
    /// Recurrence rule: "daily", "weekdays", "weekly", "biweekly", "monthly" (empty string = clear)
    pub recurrence_rule: Option<String>,
}

/// Response for action item status operations
#[derive(Debug, Clone, Serialize)]
pub struct ActionItemStatusResponse {
    pub status: String,
}

/// Response wrapper for paginated action items list
#[derive(Debug, Clone, Serialize)]
pub struct ActionItemsListResponse {
    pub items: Vec<ActionItemDB>,
    pub has_more: bool,
}

/// Request body for batch creating action items
#[derive(Debug, Clone, Deserialize)]
pub struct BatchCreateActionItemsRequest {
    pub items: Vec<CreateActionItemRequest>,
}

/// Request body for creating a new action item
#[derive(Debug, Clone, Deserialize)]
pub struct CreateActionItemRequest {
    /// The action item description (required)
    pub description: String,
    /// When the action item is due (optional)
    pub due_at: Option<DateTime<Utc>>,
    /// Source of the action item: "screenshot", "transcription:omi", "transcription:desktop", "manual"
    pub source: Option<String>,
    /// Priority: "high", "medium", "low"
    pub priority: Option<String>,
    /// JSON metadata string: {"source_app": "Safari", "confidence": 0.85}
    pub metadata: Option<String>,
    /// Category: "work", "personal", "health", "finance", etc.
    pub category: Option<String>,
    /// Relevance score for prioritization
    pub relevance_score: Option<i32>,
    /// Recurrence rule: "daily", "weekdays", "weekly", "biweekly", "monthly"
    pub recurrence_rule: Option<String>,
    /// ID of original parent task in recurrence chain
    pub recurrence_parent_id: Option<String>,
}

/// Request body for sharing tasks
#[derive(Debug, Clone, Deserialize)]
pub struct ShareTasksRequest {
    pub task_ids: Vec<String>,
}

/// Response for sharing tasks
#[derive(Debug, Clone, Serialize)]
pub struct ShareTasksResponse {
    pub url: String,
    pub token: String,
}

/// Info about a single shared task (privacy-safe subset)
#[derive(Debug, Clone, Serialize)]
pub struct SharedTaskInfo {
    pub description: String,
    pub due_at: Option<DateTime<Utc>>,
}

/// Response for getting shared tasks
#[derive(Debug, Clone, Serialize)]
pub struct SharedTasksResponse {
    pub sender_name: String,
    pub tasks: Vec<SharedTaskInfo>,
    pub count: usize,
}

/// Request body for accepting shared tasks
#[derive(Debug, Clone, Deserialize)]
pub struct AcceptTasksRequest {
    pub token: String,
}

/// Response for accepting shared tasks
#[derive(Debug, Clone, Serialize)]
pub struct AcceptTasksResponse {
    pub created: Vec<String>,
    pub count: usize,
}

/// Response for staged task promotion
#[derive(Debug, Clone, Serialize)]
pub struct PromoteResponse {
    pub promoted: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub promoted_task: Option<ActionItemDB>,
}

/// Request body for batch updating relevance scores
#[derive(Debug, Clone, Deserialize)]
pub struct BatchUpdateScoresRequest {
    pub scores: Vec<ScoreUpdate>,
}

/// Individual score update within a batch
#[derive(Debug, Clone, Deserialize)]
pub struct ScoreUpdate {
    pub id: String,
    pub relevance_score: i32,
}

/// Request body for batch updating sort orders and indent levels
#[derive(Debug, Clone, Deserialize)]
pub struct BatchUpdateSortOrdersRequest {
    pub items: Vec<SortOrderUpdate>,
}

/// Individual sort order update within a batch
#[derive(Debug, Clone, Deserialize)]
pub struct SortOrderUpdate {
    pub id: String,
    pub sort_order: i32,
    pub indent_level: i32,
}
