// Folder models

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

/// Folder for organizing conversations
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Folder {
    pub id: String,
    pub name: String,
    #[serde(default)]
    pub description: Option<String>,
    #[serde(default = "default_color")]
    pub color: String,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    #[serde(default)]
    pub order: i32,
    #[serde(default)]
    pub is_default: bool,
    #[serde(default)]
    pub is_system: bool,
    #[serde(default)]
    pub category_mapping: Option<String>,
    #[serde(default)]
    pub conversation_count: i32,
}

fn default_color() -> String {
    "#6B7280".to_string()
}

