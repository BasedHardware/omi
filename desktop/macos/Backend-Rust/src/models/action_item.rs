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

