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
    #[serde(default)]
    pub device_name: Option<String>,
    #[serde(default)]
    pub client_device_id: Option<String>,
    pub embedding: Option<Vec<f64>>,
}

impl ScreenActivityRow {
    /// SQLite IDs are per-installation, so canonical device identity is part of
    /// the cross-device storage key. Legacy rows preserve their historical key.
    pub fn storage_id(&self) -> String {
        self.client_device_id.as_ref().map_or_else(
            || self.id.to_string(),
            |device_id| format!("{}-{}", device_id, self.id),
        )
    }
}

#[cfg(test)]
mod tests {
    use super::ScreenActivityRow;

    #[test]
    fn accepts_optional_capture_provenance_without_breaking_legacy_rows() {
        let current: ScreenActivityRow = serde_json::from_value(serde_json::json!({
            "id": 42,
            "timestamp": "2026-07-20T12:00:00Z",
            "appName": "Safari",
            "windowTitle": "Omi",
            "ocrText": "screen context",
            "deviceName": "David's Mac Studio",
            "clientDeviceId": "macos_abc12345",
            "embedding": [0.5]
        }))
        .expect("current screen activity row should deserialize");
        assert_eq!(current.device_name.as_deref(), Some("David's Mac Studio"));
        assert_eq!(current.client_device_id.as_deref(), Some("macos_abc12345"));
        assert_eq!(current.storage_id(), "macos_abc12345-42");

        let legacy: ScreenActivityRow = serde_json::from_value(serde_json::json!({
            "id": 43,
            "timestamp": "2026-07-20T12:00:00Z",
            "embedding": null
        }))
        .expect("legacy screen activity row should deserialize");
        assert!(legacy.device_name.is_none());
        assert!(legacy.client_device_id.is_none());
        assert_eq!(legacy.storage_id(), "43");
    }

    #[test]
    fn storage_ids_are_device_scoped_for_matching_local_ids() {
        let row = |client_device_id: &str| ScreenActivityRow {
            id: 1,
            timestamp: "2026-07-20T12:00:00Z".to_owned(),
            app_name: "Safari".to_owned(),
            window_title: "Omi".to_owned(),
            ocr_text: "screen context".to_owned(),
            device_name: None,
            client_device_id: Some(client_device_id.to_owned()),
            embedding: None,
        };

        assert_ne!(row("macos_a").storage_id(), row("macos_b").storage_id());
    }
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
