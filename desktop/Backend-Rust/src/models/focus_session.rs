// Focus Session models - focus tracking sessions stored in Firestore
// Path: users/{uid}/focus_sessions/{session_id}

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

/// Focus status - whether user is focused or distracted
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "lowercase")]
pub enum FocusStatus {
    Focused,
    Distracted,
}

impl std::fmt::Display for FocusStatus {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            FocusStatus::Focused => write!(f, "focused"),
            FocusStatus::Distracted => write!(f, "distracted"),
        }
    }
}

/// Focus session stored in Firestore subcollection
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FocusSessionDB {
    /// Document ID
    pub id: String,
    /// Focus status: focused or distracted
    pub status: FocusStatus,
    /// The app or website visible
    pub app_or_site: String,
    /// Brief description of what's on screen
    pub description: String,
    /// Optional coaching message
    #[serde(skip_serializing_if = "Option::is_none")]
    pub message: Option<String>,
    /// When the session was created
    pub created_at: DateTime<Utc>,
    /// Duration in seconds (if known)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub duration_seconds: Option<i64>,
}

/// Request body for creating a new focus session
#[derive(Debug, Clone, Deserialize)]
pub struct CreateFocusSessionRequest {
    /// Focus status: "focused" or "distracted"
    pub status: FocusStatus,
    /// The app or website visible
    pub app_or_site: String,
    /// Brief description of what's on screen
    pub description: String,
    /// Optional coaching message
    #[serde(skip_serializing_if = "Option::is_none")]
    pub message: Option<String>,
}

/// Query params for getting focus sessions
#[derive(Debug, Clone, Deserialize)]
pub struct GetFocusSessionsQuery {
    /// Maximum number of sessions to return
    #[serde(default = "default_limit")]
    pub limit: usize,
    /// Offset for pagination
    #[serde(default)]
    pub offset: usize,
    /// Filter by date (YYYY-MM-DD format)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub date: Option<String>,
}

fn default_limit() -> usize {
    100
}

/// Response for focus session status operations
#[derive(Debug, Clone, Serialize)]
pub struct FocusSessionStatusResponse {
    pub status: String,
}

/// Entry for a distraction app/site with time spent
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DistractionEntry {
    /// App or website name
    pub app_or_site: String,
    /// Total time spent in seconds
    pub total_seconds: i64,
    /// Number of times visited
    pub count: i64,
}

/// Focus statistics for a given day
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FocusStats {
    /// Date in YYYY-MM-DD format
    pub date: String,
    /// Total focused minutes
    pub focused_minutes: i64,
    /// Total distracted minutes
    pub distracted_minutes: i64,
    /// Number of sessions
    pub session_count: i64,
    /// Number of focused sessions
    pub focused_count: i64,
    /// Number of distracted sessions
    pub distracted_count: i64,
    /// Top distraction apps/sites
    pub top_distractions: Vec<DistractionEntry>,
}

/// Query params for getting focus stats
#[derive(Debug, Clone, Deserialize)]
pub struct GetFocusStatsQuery {
    /// Date to get stats for (YYYY-MM-DD format), defaults to today
    #[serde(skip_serializing_if = "Option::is_none")]
    pub date: Option<String>,
}
