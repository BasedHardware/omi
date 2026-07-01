use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use tracing::{info, warn};

use crate::config::AppConfig;

const MCP_BASE: &str = "http://127.0.0.1:8001";

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KnowledgeResource {
    pub id: String,
    pub name: String,
    pub file_type: Option<String>,
    pub created_at: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KnowledgeSearchResult {
    pub content: String,
    pub source: Option<String>,
    pub score: Option<f64>,
}

pub async fn upload_document(file_path: &str, cfg: &AppConfig) -> Result<String> {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(120))
        .build()?;

    let file_bytes = tokio::fs::read(file_path)
        .await
        .context("Failed to read file")?;

    let file_name = std::path::Path::new(file_path)
        .file_name()
        .map(|n| n.to_string_lossy().to_string())
        .unwrap_or_else(|| "document".to_string());

    let part = reqwest::multipart::Part::bytes(file_bytes)
        .file_name(file_name.clone())
        .mime_str("application/octet-stream")?;

    let form = reqwest::multipart::Form::new().part("file", part);

    let mut req = client
        .post(format!("{MCP_BASE}/api/knowledge/upload"))
        .multipart(form);

    if !cfg.firebase_id_token.is_empty() {
        req = req.header(
            "Authorization",
            format!("Bearer {}", cfg.firebase_id_token),
        );
    }

    let resp = req.send().await.context("Upload request failed")?;

    if resp.status().is_success() {
        info!("[KB] Uploaded document: {file_name}");
        Ok(file_name)
    } else {
        let status = resp.status();
        let body = resp.text().await.unwrap_or_default();
        anyhow::bail!("Upload failed: HTTP {status} — {body}")
    }
}

pub async fn search_knowledge(query: &str, cfg: &AppConfig) -> Result<Vec<KnowledgeSearchResult>> {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(30))
        .build()?;

    let body = serde_json::json!({
        "query": query,
        "limit": 5
    });

    let mut req = client
        .post(format!("{MCP_BASE}/api/knowledge/search"))
        .json(&body);

    if !cfg.firebase_id_token.is_empty() {
        req = req.header(
            "Authorization",
            format!("Bearer {}", cfg.firebase_id_token),
        );
    }

    let resp = req.send().await.context("Knowledge search failed")?;

    if resp.status().is_success() {
        let json: serde_json::Value = resp.json().await?;
        let results = json
            .get("results")
            .and_then(|r| r.as_array())
            .map(|arr| {
                arr.iter()
                    .filter_map(|item| {
                        Some(KnowledgeSearchResult {
                            content: item.get("content")?.as_str()?.to_string(),
                            source: item
                                .get("source")
                                .and_then(|s| s.as_str())
                                .map(|s| s.to_string()),
                            score: item.get("score").and_then(|s| s.as_f64()),
                        })
                    })
                    .collect()
            })
            .unwrap_or_default();
        Ok(results)
    } else {
        warn!(
            "[KB] Search failed: HTTP {}",
            resp.status()
        );
        Ok(Vec::new())
    }
}

pub async fn list_resources(cfg: &AppConfig) -> Result<Vec<KnowledgeResource>> {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(15))
        .build()?;

    let mut req = client.get(format!("{MCP_BASE}/api/knowledge/resources"));

    if !cfg.firebase_id_token.is_empty() {
        req = req.header(
            "Authorization",
            format!("Bearer {}", cfg.firebase_id_token),
        );
    }

    let resp = req.send().await.context("List resources failed")?;

    if resp.status().is_success() {
        let json: serde_json::Value = resp.json().await?;
        let resources = json
            .get("resources")
            .and_then(|r| r.as_array())
            .map(|arr| {
                arr.iter()
                    .filter_map(|item| {
                        Some(KnowledgeResource {
                            id: item.get("id")?.as_str()?.to_string(),
                            name: item.get("name")?.as_str()?.to_string(),
                            file_type: item
                                .get("file_type")
                                .and_then(|s| s.as_str())
                                .map(|s| s.to_string()),
                            created_at: item
                                .get("created_at")
                                .and_then(|s| s.as_str())
                                .map(|s| s.to_string()),
                        })
                    })
                    .collect()
            })
            .unwrap_or_default();
        Ok(resources)
    } else {
        Ok(Vec::new())
    }
}

pub async fn get_document_chunks(resource_id: &str, cfg: &AppConfig) -> Result<Vec<String>> {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(30))
        .build()?;

    let mut req = client.get(format!("{MCP_BASE}/api/knowledge/resources/{resource_id}/chunks"));

    if !cfg.firebase_id_token.is_empty() {
        req = req.header(
            "Authorization",
            format!("Bearer {}", cfg.firebase_id_token),
        );
    }

    let resp = req.send().await.context("Get chunks failed")?;

    if resp.status().is_success() {
        let json: serde_json::Value = resp.json().await?;
        let chunks = json
            .get("chunks")
            .and_then(|c| c.as_array())
            .map(|arr| {
                arr.iter()
                    .filter_map(|c| c.get("content").and_then(|t| t.as_str()).map(|s| s.to_string()))
                    .collect()
            })
            .unwrap_or_default();
        Ok(chunks)
    } else {
        Ok(Vec::new())
    }
}

pub fn is_knowledge_query(query: &str) -> bool {
    let q = query.to_lowercase();
    let keywords = [
        "search my files",
        "search my documents",
        "what does the doc",
        "find in my files",
        "look up in my docs",
        "knowledge base",
        "in my uploaded",
        "search knowledge",
    ];
    keywords.iter().any(|kw| q.contains(kw))
}
