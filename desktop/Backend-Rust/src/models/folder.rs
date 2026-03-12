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

/// Request to create a new folder
#[derive(Debug, Deserialize)]
pub struct CreateFolderRequest {
    pub name: String,
    #[serde(default)]
    pub description: Option<String>,
    #[serde(default)]
    pub color: Option<String>,
}

/// Request to update a folder
#[derive(Debug, Deserialize)]
pub struct UpdateFolderRequest {
    pub name: Option<String>,
    pub description: Option<String>,
    pub color: Option<String>,
    pub order: Option<i32>,
}

/// Query params for delete folder
#[derive(Debug, Deserialize)]
pub struct DeleteFolderQuery {
    pub move_to_folder_id: Option<String>,
}

/// Request to move a conversation to a folder
#[derive(Debug, Deserialize)]
pub struct MoveToFolderRequest {
    pub folder_id: Option<String>,
}

/// Request to bulk move conversations
#[derive(Debug, Deserialize)]
pub struct BulkMoveRequest {
    pub conversation_ids: Vec<String>,
}

/// Response for bulk move
#[derive(Debug, Serialize)]
pub struct BulkMoveResponse {
    pub moved_count: i32,
}

/// Request to reorder folders
#[derive(Debug, Deserialize)]
pub struct ReorderFoldersRequest {
    pub folder_ids: Vec<String>,
}
