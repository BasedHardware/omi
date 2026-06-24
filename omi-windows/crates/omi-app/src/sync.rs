use reqwest::Client;
use serde_json::json;
use tracing::{info, warn};

pub async fn upload_memory(backend_url: String, token: String, content: String, category: String) {
    if backend_url.is_empty() || token.is_empty() {
        return;
    }

    let payload = json!({
        "content": content,
        "category": category,
        "visibility": "private",
        "tags": []
    });

    let url = format!("{}/v3/memories", backend_url.trim_end_matches('/'));
    
    let client = Client::new();
    match client
        .post(&url)
        .header("Authorization", format!("Bearer {}", token))
        .json(&payload)
        .send()
        .await
    {
        Ok(res) => {
            if res.status().is_success() {
                info!("[SYNC] Uploaded memory successfully.");
            } else {
                warn!("[SYNC] Failed to upload memory: {}", res.status());
            }
        }
        Err(e) => {
            warn!("[SYNC] Error uploading memory: {}", e);
        }
    }
}
