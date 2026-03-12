// Goal models - user goals stored in Firestore
// Path: users/{uid}/goals/{goal_id}

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

/// Type of goal measurement
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "lowercase")]
pub enum GoalType {
    /// Boolean goal (done/not done)
    Boolean,
    /// Scale goal (e.g., 1-10)
    Scale,
    /// Numeric goal (e.g., steps, hours)
    Numeric,
}

impl Default for GoalType {
    fn default() -> Self {
        GoalType::Boolean
    }
}

/// Goal stored in Firestore subcollection
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GoalDB {
    /// Document ID
    pub id: String,
    /// Goal title
    pub title: String,
    /// Detailed description of the goal (why it matters, what achieving it looks like)
    #[serde(default)]
    pub description: Option<String>,
    /// Type of goal measurement
    #[serde(default)]
    pub goal_type: GoalType,
    /// Target value to achieve (for numeric/scale goals)
    #[serde(default)]
    pub target_value: f64,
    /// Current progress value
    #[serde(default)]
    pub current_value: f64,
    /// Minimum value for scale (default 0)
    #[serde(default)]
    pub min_value: f64,
    /// Maximum value for scale (default 100)
    #[serde(default = "default_max_value")]
    pub max_value: f64,
    /// Unit of measurement (e.g., "hours", "steps", "pages")
    pub unit: Option<String>,
    /// Whether the goal is active
    #[serde(default = "default_true")]
    pub is_active: bool,
    /// When the goal was created
    pub created_at: DateTime<Utc>,
    /// When the goal was last updated
    pub updated_at: DateTime<Utc>,
    /// When the goal was completed (None if not completed)
    #[serde(default)]
    pub completed_at: Option<DateTime<Utc>>,
    /// Source of the goal: "user" for manually created, "ai" for auto-generated
    #[serde(default)]
    pub source: Option<String>,
}

fn default_max_value() -> f64 {
    100.0
}

fn default_true() -> bool {
    true
}

/// Request body for creating a new goal
#[derive(Debug, Clone, Deserialize)]
pub struct CreateGoalRequest {
    /// Goal title (required)
    pub title: String,
    /// Detailed description (optional)
    pub description: Option<String>,
    /// Type of goal measurement (optional, defaults to boolean)
    #[serde(default)]
    pub goal_type: GoalType,
    /// Target value to achieve (optional, defaults to 1.0 for boolean)
    pub target_value: Option<f64>,
    /// Current progress value (optional, defaults to 0)
    pub current_value: Option<f64>,
    /// Minimum value for scale (optional, defaults to 0)
    pub min_value: Option<f64>,
    /// Maximum value for scale (optional, defaults to 100)
    pub max_value: Option<f64>,
    /// Unit of measurement (optional)
    pub unit: Option<String>,
    /// Source: "user" for manually created, "ai" for auto-generated
    pub source: Option<String>,
}

/// Request body for updating an existing goal
#[derive(Debug, Clone, Deserialize)]
pub struct UpdateGoalRequest {
    /// New title (optional)
    pub title: Option<String>,
    /// New description (optional)
    pub description: Option<String>,
    /// New target value (optional)
    pub target_value: Option<f64>,
    /// New current value (optional)
    pub current_value: Option<f64>,
    /// New min value (optional)
    pub min_value: Option<f64>,
    /// New max value (optional)
    pub max_value: Option<f64>,
    /// New unit (optional)
    pub unit: Option<String>,
    /// New active status (optional)
    pub is_active: Option<bool>,
    /// When the goal was completed (optional)
    pub completed_at: Option<String>,
}

/// Query parameters for updating goal progress
#[derive(Debug, Clone, Deserialize)]
pub struct UpdateGoalProgressQuery {
    /// New current value
    pub current_value: f64,
}

/// Response for goal status operations
#[derive(Debug, Clone, Serialize)]
pub struct GoalStatusResponse {
    pub status: String,
}

/// Single score calculation (used for daily, weekly, overall)
#[derive(Debug, Clone, Serialize)]
pub struct ScoreData {
    /// Score as percentage (0-100)
    pub score: f64,
    /// Number of completed tasks
    pub completed_tasks: i32,
    /// Total number of tasks in scope
    pub total_tasks: i32,
}

/// Combined score response with all three score types
#[derive(Debug, Clone, Serialize)]
pub struct ScoreResponse {
    /// Tasks due today
    pub daily: ScoreData,
    /// Tasks from last 7 days (created or completed)
    pub weekly: ScoreData,
    /// All tasks ever
    pub overall: ScoreData,
    /// Which tab to show by default (highest score, or "overall" if tie)
    pub default_tab: String,
    /// Date of the calculation
    pub date: String,
}

/// Legacy daily score for backwards compatibility
#[derive(Debug, Clone, Serialize)]
pub struct DailyScore {
    /// Score as percentage (0-100)
    pub score: f64,
    /// Number of completed tasks
    pub completed_tasks: i32,
    /// Total number of tasks due today
    pub total_tasks: i32,
    /// Date of the score calculation
    pub date: String,
}

/// Query parameters for daily score
#[derive(Debug, Clone, Deserialize)]
pub struct DailyScoreQuery {
    /// Optional date in YYYY-MM-DD format (defaults to today)
    pub date: Option<String>,
}

/// A single progress history entry for a goal
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GoalHistoryEntry {
    /// Date in YYYY-MM-DD format
    pub date: String,
    /// The progress value recorded
    pub value: f64,
    /// When the entry was recorded
    pub recorded_at: DateTime<Utc>,
}

/// Query parameters for goal history
#[derive(Debug, Clone, Deserialize)]
pub struct GoalHistoryQuery {
    /// Number of days of history to return (default 30)
    #[serde(default = "default_history_days")]
    pub days: u32,
}

fn default_history_days() -> u32 {
    30
}

/// Response wrapper for goal history
#[derive(Debug, Clone, Serialize)]
pub struct GoalHistoryResponse {
    pub history: Vec<GoalHistoryEntry>,
}

/// Response wrapper for goals list
#[derive(Debug, Clone, Serialize)]
pub struct GoalsListResponse {
    pub goals: Vec<GoalDB>,
}
