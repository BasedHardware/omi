use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ScreenActivityRow {
    pub id: i64,
    pub timestamp: String,
    #[serde(default)]
    pub app_name: String,
    #[serde(default)]
    pub window_title: String,
    #[serde(default)]
    pub ocr_text: String,
    pub embedding: Option<Vec<f64>>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ScreenActivitySyncRequest {
    pub rows: Vec<ScreenActivityRow>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ScreenActivitySyncResponse {
    pub synced: usize,
    pub last_id: i64,
}
