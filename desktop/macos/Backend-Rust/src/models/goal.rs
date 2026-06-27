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

