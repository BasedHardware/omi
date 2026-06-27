// Advice models - proactive advice stored in Firestore
// Path: users/{uid}/advice/{advice_id}

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

/// Advice category enum matching the Swift AdviceCategory
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "lowercase")]
pub enum AdviceCategory {
    Productivity,
    Health,
    Communication,
    Learning,
    Other,
}

impl Default for AdviceCategory {
    fn default() -> Self {
        AdviceCategory::Other
    }
}

/// Advice stored in Firestore subcollection
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AdviceDB {
    /// Document ID
    pub id: String,
    /// The advice text content
    pub content: String,
    /// Category of the advice
    #[serde(default)]
    pub category: AdviceCategory,
    /// Reasoning behind the advice
    pub reasoning: Option<String>,
    /// App where the context was observed
    pub source_app: Option<String>,
    /// Confidence score (0.0 - 1.0)
    #[serde(default)]
    pub confidence: f64,
    /// Summary of the context when advice was generated
    pub context_summary: Option<String>,
    /// Description of user's activity when advice was generated
    pub current_activity: Option<String>,
    /// When the advice was created
    pub created_at: DateTime<Utc>,
    /// When the advice was last updated
    pub updated_at: Option<DateTime<Utc>>,
    /// Whether the user has read this advice
    #[serde(default)]
    pub is_read: bool,
    /// Whether the advice has been dismissed/archived
    #[serde(default)]
    pub is_dismissed: bool,
}
