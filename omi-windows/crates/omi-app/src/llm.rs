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

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
pub struct ScreenshotMemoryExtraction {
    pub content: String,
    pub category: Option<String>,
}

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
pub struct ScreenshotExtraction {
    pub summary: String,
    #[serde(default)]
    pub memories: Vec<ScreenshotMemoryExtraction>,
    #[serde(default)]
    pub action_items: Vec<String>,
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

// ── 2. Extract action items (dedup against open tasks) ───────────────────
    let existing_tasks = db.list_open_action_items_for_dedup(100).unwrap_or_default();
    let tasks_ctx = if existing_tasks.is_empty() {
        String::new()
    } else {
        format!("\n\nAlready-captured open tasks — DO NOT duplicate any of these:\n{existing_tasks}")
    };

    let action_prompt = format!(
        "Extract action items from this conversation transcript.\n\
        \n\
        RULES — follow every one strictly:\n\
        1. Only extract tasks the USER explicitly committed to or was clearly assigned.\n\
        2. Each task must start with a strong action verb (Send, Review, Schedule, Build, Fix…).\n\
        3. Be specific: include names, deadlines, URLs, or key details when mentioned.\n\
        4. DO NOT duplicate tasks already in the list below.\n\
        5. DO NOT extract vague intentions (\"follow up\", \"look into\", \"think about\").\n\
        6. DO NOT extract things that are already done or were completed during the conversation.\n\
        7. Return a JSON array of strings. Return [] if nothing qualifies.\
        {tasks_ctx}\n\n\
        Transcript:\n{transcript}"
    );

    let action_result = complete(
        &api_key, &url, &model,
        vec![LlmMessage { role: "user".into(), content: action_prompt }],
        Some(600),
    ).await;

    match action_result {
        Ok(text) => {
            let json_str = strip_code_fences(text.trim());
            if let Ok(items) = serde_json::from_str::<Vec<String>>(json_str) {
                let (mut inserted, mut skipped) = (0usize, 0usize);
                for item in &items {
                    let content = item.trim();
                    if content.is_empty() { continue; }
                    // DB-level Jaccard similarity — skip if ≥55% token overlap with any open task
                    if db.has_similar_action_item(content, 0.55).unwrap_or(false) {
                        tracing::debug!("[LLM] Skipping duplicate task: {content}");
                        skipped += 1;
                        continue;
                    }
                    if let Err(e) = db.insert_action_item(Some(conversation_id), content) {
                        tracing::error!("[LLM] Failed to insert action item: {e}");
                    } else {
                        inserted += 1;
                    }
                }
                tracing::info!("[LLM] Tasks for {conversation_id}: {inserted} new, {skipped} duplicate");
            } else {
                tracing::warn!("[LLM] Could not parse action items JSON: {}", &text[..text.len().min(300)]);
            }
        }
        Err(e) => tracing::error!("[LLM] Action item extraction failed: {e}"),
    }

    // ── 3. Extract memory bullets (dedup against existing memories) ───────────
    let existing_mems = db.list_memories_for_dedup(150).unwrap_or_default();
    let mems_ctx = if existing_mems.is_empty() {
        String::new()
    } else {
        format!("\n\nAlready-stored memories — DO NOT duplicate, restate, or rephrase any of these:\n{existing_mems}")
    };

    let memory_prompt = format!(
        "Extract long-term memories from this conversation transcript.\n\
        \n\
        A memory is worth storing ONLY if ALL of the following are true:\n\
        • Specific — contains a concrete name, number, date, product, place, or fact\n\
        • Durable — still relevant and useful at least 4 weeks from now\n\
        • Personal — reveals a user preference, decision, commitment, or relationship\n\
        • New — not already captured in the existing memories list below\n\
        \n\
        DO NOT store:\n\
        - Generic observations (\"user is working on X\")\n\
        - Transient info (today's weather, current prices, the meeting just held)\n\
        - Anything vague, obvious, or generic\n\
        - Near-duplicates of existing memories (even if worded differently)\n\
        - Summaries of the conversation itself\n\
        \n\
        For category use exactly one of: fact | preference | decision | commitment | relationship | technical\n\
        Return a JSON array: [{{\"content\": \"<precise single sentence>\", \"category\": \"<category>\"}}]\n\
        Return [] if nothing qualifies. Be ruthlessly selective — 0-2 memories per conversation is normal.\
        {mems_ctx}\n\n\
        Transcript:\n{transcript}"
    );

    let memory_result = complete(
        &api_key, &url, &model,
        vec![LlmMessage { role: "user".into(), content: memory_prompt }],
        Some(700),
    ).await;

    match memory_result {
        Ok(text) => {
            let json_str = strip_code_fences(text.trim());
            if let Ok(items) = serde_json::from_str::<Vec<serde_json::Value>>(json_str) {
                let (mut inserted, mut skipped) = (0usize, 0usize);
                for item in &items {
                    let content = item["content"].as_str().unwrap_or("").trim();
                    let category = item["category"].as_str();
                    if content.is_empty() { continue; }
                    // DB-level similarity check — skip if ≥45% token overlap
                    if db.find_similar_memories(content, 0.45).map(|v| !v.is_empty()).unwrap_or(false) {
                        tracing::debug!("[LLM] Skipping near-duplicate memory: {content}");
                        skipped += 1;
                        continue;
                    }
                    if let Err(e) = db.insert_memory(Some(conversation_id), content, category) {
                        tracing::error!("[LLM] Failed to insert memory: {e}");
                    } else {
                        inserted += 1;
                    }
                }
                tracing::info!("[LLM] Memories for {conversation_id}: {inserted} new, {skipped} duplicate");
            } else {
                tracing::warn!("[LLM] Could not parse memory JSON: {}", &text[..text.len().min(300)]);
            }
        }
        Err(e) => tracing::error!("[LLM] Memory extraction failed: {e}"),
    }
}

/// Strip markdown code fences from LLM output so JSON parsing is robust.
fn strip_code_fences(s: &str) -> &str {
    let s = s.trim_start_matches("```json").trim_start_matches("```");
    let s = s.trim_end_matches("```");
    s.trim()
}

/// Summarize a list of recent screen OCR excerpts into a short, focused text.
/// Each item is a tuple of (timestamp_rfc3339, window_title, ocr_text).
pub async fn summarize_ocr_snippets(
    cfg: &AppConfig,
    items: Vec<(String, String, String)>,
) -> Result<String> {
    if items.is_empty() {
        return Ok(String::new());
    }

    let (api_key, url, model) = resolve_llm_endpoint(cfg);
    if api_key.is_empty() {
        tracing::warn!("[LLM] No LLM API key configured, skipping OCR summarization");
        return Ok(String::new());
    }

    // Build a compact prompt containing the recent OCR snippets.
    let mut joined = String::new();
    let per_item_max = cfg.ocr_summary_max_chars.min(5000).max(64);
    for (ts, title, ocr) in &items {
        let ocr_short = if ocr.len() > per_item_max { format!("{}...", &ocr[..per_item_max]) } else { ocr.clone() };
        joined.push_str(&format!("{} | {}: {}\n", ts, title, ocr_short));
    }

    let prompt = format!(
        "Summarize the following recent screen text extracts into up to 4 concise bullet points, \nfocus on important information and any actionable items. If nothing notable, return an empty string.\n\n{}",
        joined
    );

    let resp = complete(
        &api_key,
        &url,
        &model,
        vec![LlmMessage { role: "user".into(), content: prompt }],
        Some(200),
    )
    .await;

    match resp {
        Ok(s) => Ok(s.trim().to_string()),
        Err(e) => {
            tracing::error!("[LLM] OCR summarization failed: {e}");
            Ok(String::new())
        }
    }
}

/// Extract a summary plus optional memories and action items from a screenshot.
pub async fn extract_screenshot_artifacts(
    cfg: &AppConfig,
    window_title: Option<&str>,
    ocr_text: Option<&str>,
) -> Result<ScreenshotExtraction> {
    let ocr_text = match ocr_text.map(str::trim) {
        Some(text) if !text.is_empty() => text,
        _ => return Ok(ScreenshotExtraction::default()),
    };

    let (api_key, url, model) = resolve_llm_endpoint(cfg);
    if api_key.is_empty() {
        tracing::warn!("[LLM] No LLM API key configured, skipping screenshot extraction");
        return Ok(ScreenshotExtraction::default());
    }

    let max_chars = cfg.ocr_summary_max_chars.min(5000).max(64);
    let ocr_short = if ocr_text.len() > max_chars { format!("{}...", &ocr_text[..max_chars]) } else { ocr_text.to_string() };
    let title = window_title.unwrap_or("Unknown window");

    let prompt = format!(
        "Analyze this screenshot OCR and return EXACTLY one JSON object with this schema:\n\
        {{\"summary\": \"<1-3 sentence summary>\", \"memories\": [{{\"content\": \"<important fact or preference>\", \"category\": \"fact|preference|decision|task|other\"}}], \"action_items\": [\"<clear actionable task>\"]}}\n\n\
        Rules:\n\
        - Return valid JSON only. No markdown, no prose.\n\
        - Keep summary short and grounded in the screenshot.\n\
        - Only include memories or action items that are explicitly supported by the screenshot.\n\
        - Use empty arrays when nothing should be saved.\n\n\
        Window title: {title}\n\
        OCR text:\n{ocr_short}"
    );

    let resp = complete(
        &api_key,
        &url,
        &model,
        vec![LlmMessage { role: "user".into(), content: prompt }],
        Some(250),
    )
    .await;

    match resp {
        Ok(text) => {
            let parsed = serde_json::from_str::<ScreenshotExtraction>(&text)
                .or_else(|_| serde_json::from_value::<ScreenshotExtraction>(serde_json::json!({
                    "summary": text.trim(),
                    "memories": [],
                    "action_items": [],
                })));

            match parsed {
                Ok(result) => Ok(result),
                Err(e) => {
                    tracing::warn!("[LLM] Screenshot extraction parse failed: {e}");
                    Ok(ScreenshotExtraction::default())
                }
            }
        }
        Err(e) => {
            tracing::error!("[LLM] Screenshot extraction failed: {e}");
            Ok(ScreenshotExtraction::default())
        }
    }
}
/// Run an LLM-assisted deduplication pass over all stored memories.
/// Loads up to 200 memories, asks the model which IDs are near-duplicates,
/// keeps the more specific one, deletes the rest.  Returns count of deleted.
pub async fn deduplicate_memories(
    db: &omi_db::Database,
    cfg: &AppConfig,
) -> Result<usize> {
    let mems = db.list_memories(200)?;
    if mems.len() < 2 {
        return Ok(0);
    }

    let (api_key, url, model) = resolve_llm_endpoint(cfg);
    if api_key.is_empty() {
        anyhow::bail!("No LLM API key configured");
    }

    let numbered: String = mems.iter().enumerate()
        .map(|(i, m)| format!("{}. [{}] {}", i + 1, m.category.as_deref().unwrap_or("general"), m.content))
        .collect::<Vec<_>>()
        .join("\n");

    let prompt = format!(
        "Below is a numbered list of stored memories. Identify groups of near-duplicate or \
        redundant memories (same fact stated differently, one being a subset of another, etc.).\n\
        For each group, keep the MOST SPECIFIC / DETAILED one and mark the others for deletion.\n\
        Return a JSON array of 1-based indices to DELETE. Return [] if nothing should be removed.\n\
        Only remove true duplicates — do not remove memories that are related but distinct.\n\n\
        Memories:\n{numbered}"
    );

    let resp = complete(
        &api_key, &url, &model,
        vec![LlmMessage { role: "user".into(), content: prompt }],
        Some(400),
    ).await?;

    let json_str = strip_code_fences(resp.trim());
    let indices: Vec<usize> = serde_json::from_str(json_str)
        .unwrap_or_default();

    let mut deleted = 0usize;
    for idx in &indices {
        let i = idx.saturating_sub(1);
        if let Some(m) = mems.get(i) {
            if db.delete_memory(&m.id).is_ok() {
                deleted += 1;
                tracing::info!("[LLM] Dedup deleted memory: {}", &m.content[..m.content.len().min(80)]);
            }
        }
    }
    Ok(deleted)
}