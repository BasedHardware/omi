use reqwest::Client;
use serde_json::json;
use tracing::{info, warn};

use crate::config::AppConfig;

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

pub async fn upload_conversation(
    backend_url: &str,
    token: &str,
    title: &str,
    summary: &str,
    duration_secs: f64,
    source: &str,
) -> Result<(), anyhow::Error> {
    if backend_url.is_empty() || token.is_empty() {
        return Ok(());
    }

    let payload = json!({
        "title": title,
        "summary": summary,
        "duration": duration_secs,
        "source": source,
        "language": "en",
    });

    let url = format!("{}/v2/conversations", backend_url.trim_end_matches('/'));
    let client = Client::new();
    let res = client
        .post(&url)
        .header("Authorization", format!("Bearer {token}"))
        .json(&payload)
        .send()
        .await?;

    if res.status().is_success() {
        info!("[SYNC] Uploaded conversation: {title}");
    } else {
        warn!("[SYNC] Failed to upload conversation: {}", res.status());
    }
    Ok(())
}

pub async fn upload_action_item(
    backend_url: &str,
    token: &str,
    content: &str,
    completed: bool,
) -> Result<(), anyhow::Error> {
    if backend_url.is_empty() || token.is_empty() {
        return Ok(());
    }

    let payload = json!({
        "content": content,
        "completed": completed,
        "source": "desktop",
    });

    let url = format!("{}/v1/action-items", backend_url.trim_end_matches('/'));
    let client = Client::new();
    let res = client
        .post(&url)
        .header("Authorization", format!("Bearer {token}"))
        .json(&payload)
        .send()
        .await?;

    if res.status().is_success() {
        info!("[SYNC] Uploaded action item");
    } else {
        warn!("[SYNC] Failed to upload action item: {}", res.status());
    }
    Ok(())
}

pub async fn download_memories(
    backend_url: &str,
    token: &str,
) -> Result<Vec<RemoteMemory>, anyhow::Error> {
    if backend_url.is_empty() || token.is_empty() {
        return Ok(Vec::new());
    }

    let url = format!("{}/v3/memories?limit=50", backend_url.trim_end_matches('/'));
    let client = Client::new();
    let res = client
        .get(&url)
        .header("Authorization", format!("Bearer {token}"))
        .send()
        .await?;

    if !res.status().is_success() {
        warn!("[SYNC] Failed to download memories: {}", res.status());
        return Ok(Vec::new());
    }

    let body = res.text().await?;
    let memories: Vec<RemoteMemory> = serde_json::from_str(&body).unwrap_or_default();
    info!("[SYNC] Downloaded {} remote memories", memories.len());
    Ok(memories)
}

pub async fn download_conversations(
    backend_url: &str,
    token: &str,
) -> Result<Vec<RemoteConversation>, anyhow::Error> {
    if backend_url.is_empty() || token.is_empty() {
        return Ok(Vec::new());
    }

    let url = format!("{}/v2/conversations?limit=50", backend_url.trim_end_matches('/'));
    let client = Client::new();
    let res = client
        .get(&url)
        .header("Authorization", format!("Bearer {token}"))
        .send()
        .await?;

    if !res.status().is_success() {
        warn!("[SYNC] Failed to download conversations: {}", res.status());
        return Ok(Vec::new());
    }

    let body = res.text().await?;
    let convos: Vec<RemoteConversation> = serde_json::from_str(&body).unwrap_or_default();
    info!("[SYNC] Downloaded {} remote conversations", convos.len());
    Ok(convos)
}

/// Full bidirectional sync: upload local → download remote → merge
pub async fn full_sync(
    db: &omi_db::Database,
    cfg: &AppConfig,
) -> Result<SyncResult, anyhow::Error> {
    let backend_url = &cfg.python_backend_url;
    let token = &cfg.firebase_id_token;
    let mut result = SyncResult::default();

    // Upload local memories
    if let Ok(memories) = db.list_memories(100) {
        for mem in &memories {
            upload_memory(
                backend_url.clone(),
                token.clone(),
                mem.content.clone(),
                mem.category.clone().unwrap_or_else(|| "general".into()),
            )
            .await;
            result.uploaded_memories += 1;
        }
    }

    // Upload local conversations
    if let Ok(convos) = db.list_conversations(50) {
        for convo in &convos {
            if convo.status == "completed" {
                let _ = upload_conversation(
                    backend_url,
                    token,
                    convo.title.as_deref().unwrap_or("Untitled"),
                    convo.summary.as_deref().unwrap_or(""),
                    convo.duration_secs,
                    "desktop",
                )
                .await;
                result.uploaded_conversations += 1;
            }
        }
    }

    // Upload local action items
    if let Ok(items) = db.list_action_items(100) {
        for item in &items {
            let _ = upload_action_item(backend_url, token, &item.content, item.completed).await;
            result.uploaded_tasks += 1;
        }
    }

    // Download remote memories and merge into local DB
    if let Ok(remote_mems) = download_memories(backend_url, token).await {
        for rm in &remote_mems {
            let exists = db
                .list_memories(500)
                .map(|mems| mems.iter().any(|m| m.content == rm.content))
                .unwrap_or(false);
            if !exists {
                let _ = db.insert_memory(None, &rm.content, rm.category.as_deref());
                result.downloaded_memories += 1;
            }
        }
    }

    info!(
        "[SYNC] Complete: uploaded {}/{}/{} (mem/conv/task), downloaded {} memories",
        result.uploaded_memories,
        result.uploaded_conversations,
        result.uploaded_tasks,
        result.downloaded_memories,
    );

    Ok(result)
}

#[derive(Debug, Default)]
pub struct SyncResult {
    pub uploaded_memories: usize,
    pub uploaded_conversations: usize,
    pub uploaded_tasks: usize,
    pub downloaded_memories: usize,
}

#[derive(Debug, serde::Deserialize)]
pub struct RemoteMemory {
    #[serde(default)]
    pub id: String,
    #[serde(default)]
    pub content: String,
    #[serde(default)]
    pub category: Option<String>,
}

#[derive(Debug, serde::Deserialize)]
pub struct RemoteConversation {
    #[serde(default)]
    pub id: String,
    #[serde(default)]
    pub title: Option<String>,
    #[serde(default)]
    pub summary: Option<String>,
    #[serde(default)]
    pub source: Option<String>,
}
