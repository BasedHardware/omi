/// Shared LLM utilities: chat completions + post-conversation processing.

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};

use crate::config::AppConfig;

// ── Request / response types ─────────────────────────────────────────────────

#[derive(Serialize)]
pub struct LlmRequest {
    pub model: String,
    pub messages: Vec<LlmMessage>,
    pub stream: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub temperature: Option<f32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub max_tokens: Option<u32>,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct LlmMessage {
    pub role: String,
    pub content: String,
}

#[derive(Deserialize)]
struct LlmResponse {
    choices: Vec<LlmChoice>,
}

#[derive(Deserialize)]
struct LlmChoice {
    message: LlmResponseMsg,
}

#[derive(Deserialize)]
struct LlmResponseMsg {
    content: String,
}

// ── Endpoint resolution ──────────────────────────────────────────────────────

/// Resolve (api_key, url, model) from AppConfig, falling back to env vars.
pub fn resolve_llm_endpoint(cfg: &AppConfig) -> (String, String, String) {
    let azure_key = std::env::var("AZURE_API_KEY").unwrap_or_default();
    let azure_base = std::env::var("AZURE_BASE_URL").unwrap_or_default();
    let azure_model = std::env::var("AZURE_MODEL").unwrap_or_else(|_| "gpt-4o-mini".into());

    if !cfg.groq_api_key.is_empty() {
        return (
            cfg.groq_api_key.clone(),
            "https://api.groq.com/openai/v1/chat/completions".into(),
            "llama-3.3-70b-versatile".into(),
        );
    }
    if !azure_key.is_empty() && !azure_base.is_empty() {
        return (azure_key, azure_base, azure_model);
    }
    if !cfg.openai_api_key.is_empty() {
        let base = cfg.openai_base_url.trim_end_matches('/').to_string();
        return (
            cfg.openai_api_key.clone(),
            format!("{base}/chat/completions"),
            cfg.openai_model.clone(),
        );
    }
    (String::new(), String::new(), String::new())
}

// ── Core completion call ─────────────────────────────────────────────────────

/// Call the LLM and return the assistant response text.
pub async fn complete(
    api_key: &str,
    url: &str,
    model: &str,
    messages: Vec<LlmMessage>,
    max_tokens: Option<u32>,
) -> Result<String> {
    let is_azure = url.contains("azure.com");

    let req = LlmRequest {
        model: model.to_string(),
        messages,
        stream: false,
        temperature: Some(0.3),
        max_tokens,
    };

    let mut builder = reqwest::Client::new().post(url).json(&req);
    if is_azure {
        builder = builder
            .header("api-key", api_key)
            .header("Content-Type", "application/json");
    } else {
        builder = builder.header("Authorization", format!("Bearer {api_key}"));
    }

    let resp = builder.send().await.context("LLM request failed")?;
    let status = resp.status();
    let body = resp.text().await.unwrap_or_default();

    if !status.is_success() {
        anyhow::bail!("LLM error {status}: {}", &body[..body.len().min(300)]);
    }

    let parsed: LlmResponse = serde_json::from_str(&body)
        .with_context(|| format!("Failed to parse LLM response: {}", &body[..body.len().min(300)]))?;

    parsed
        .choices
        .into_iter()
        .next()
        .map(|c| c.message.content)
        .context("LLM returned no choices")
}

// ── Post-conversation processing ─────────────────────────────────────────────

/// Summarize a completed conversation and extract memories.
/// Updates the DB with title, summary, and inserts memory bullets.
pub async fn process_conversation(
    db: &omi_db::Database,
    conversation_id: &str,
    cfg: &AppConfig,
) {
    let transcript = match db.get_transcript_text(conversation_id) {
        Ok(t) => t,
        Err(e) => {
            tracing::error!("[LLM] Failed to get transcript for {conversation_id}: {e}");
            return;
        }
    };

    if transcript.trim().is_empty() {
        tracing::warn!("[LLM] Transcript empty for {conversation_id}, skipping summarization");
        return;
    }

    let (api_key, url, model) = resolve_llm_endpoint(cfg);
    if api_key.is_empty() {
        tracing::warn!("[LLM] No LLM API key configured, skipping summarization");
        return;
    }

    tracing::info!("[LLM] Summarizing conversation {conversation_id} ({} chars)", transcript.len());

    // ── 1. Generate title + summary ───────────────────────────────────────────
    let summary_prompt = format!(
        "You are processing a voice conversation transcript. Given the transcript below, \
        respond with EXACTLY this JSON format and nothing else:\n\
        {{\"title\": \"<5-8 word title>\", \"summary\": \"<2-4 sentence summary>\"}}\n\n\
        Transcript:\n{transcript}"
    );

    let summary_result = complete(
        &api_key, &url, &model,
        vec![LlmMessage { role: "user".into(), content: summary_prompt }],
        Some(300),
    ).await;

    let (title, summary) = match summary_result {
        Ok(text) => {
            // Try to parse JSON, fallback to raw text as summary
            if let Ok(v) = serde_json::from_str::<serde_json::Value>(&text) {
                (
                    v["title"].as_str().unwrap_or("Conversation").to_string(),
                    v["summary"].as_str().unwrap_or(&text).to_string(),
                )
            } else {
                // Model returned plain text instead of JSON
                ("Conversation".to_string(), text)
            }
        }
        Err(e) => {
            tracing::error!("[LLM] Summary failed: {e}");
            ("Conversation".to_string(), String::new())
        }
    };

    if let Err(e) = db.update_summary(conversation_id, &title, &summary) {
        tracing::error!("[LLM] Failed to save summary: {e}");
    } else {
        tracing::info!("[LLM] Saved summary for {conversation_id}: \"{title}\"");
    }

    // ── 2. Extract memory bullets ─────────────────────────────────────────────
    let memory_prompt = format!(
        "Extract important facts, preferences, decisions, or commitments from this conversation \
        that are worth remembering long-term. Return a JSON array of objects with \"content\" \
        and \"category\" (one of: fact, preference, decision, task, other). \
        Return an empty array [] if nothing is worth remembering.\n\n\
        Transcript:\n{transcript}"
    );

    let memory_result = complete(
        &api_key, &url, &model,
        vec![LlmMessage { role: "user".into(), content: memory_prompt }],
        Some(500),
    ).await;

    match memory_result {
        Ok(text) => {
            if let Ok(items) = serde_json::from_str::<Vec<serde_json::Value>>(&text) {
                for item in &items {
                    let content = item["content"].as_str().unwrap_or("").trim();
                    let category = item["category"].as_str();
                    if !content.is_empty() {
                        if let Err(e) = db.insert_memory(Some(conversation_id), content, category) {
                            tracing::error!("[LLM] Failed to insert memory: {e}");
                        }
                    }
                }
                tracing::info!("[LLM] Extracted {} memories for {conversation_id}", items.len());
            } else {
                tracing::warn!("[LLM] Could not parse memory JSON: {}", &text[..text.len().min(200)]);
            }
        }
        Err(e) => tracing::error!("[LLM] Memory extraction failed: {e}"),
    }
}
