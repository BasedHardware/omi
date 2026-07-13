/// Shared LLM utilities — multi-provider with per-use-case routing.
///
/// # Provider priority (auto mode)
/// Primary (chat/agent):    Anthropic → Groq → OpenAI
/// Background (extraction): OpenAI → Anthropic → Groq
/// This ensures interactive chat is never blocked by background summarisation
/// jobs hammering the same rate-limited endpoint simultaneously.

use std::sync::OnceLock;

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use tokio::sync::Semaphore;


use crate::config::AppConfig;

// ── Per-provider concurrency semaphores (prevent rate-limit pile-ups) ────────

static GROQ_SEM:      OnceLock<Semaphore> = OnceLock::new();
static ANTHROPIC_SEM: OnceLock<Semaphore> = OnceLock::new();
static OPENAI_SEM:    OnceLock<Semaphore> = OnceLock::new();

fn groq_sem()      -> &'static Semaphore { GROQ_SEM.get_or_init(|| Semaphore::new(2)) }
fn anthropic_sem() -> &'static Semaphore { ANTHROPIC_SEM.get_or_init(|| Semaphore::new(3)) }
fn openai_sem()    -> &'static Semaphore { OPENAI_SEM.get_or_init(|| Semaphore::new(4)) }

// ── Use-case enum ─────────────────────────────────────────────────────────────

/// Which class of workload is making the LLM call.
/// Used to route to the correct provider so background jobs don't starve the UI.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LlmUseCase {
    /// User-facing interactive call (chat, agent, floating bar). Latency-sensitive.
    Chat,
    /// Background processing (extraction, summarisation, OCR). Can tolerate a bit more latency.
    Background,
}

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

// Anthropic Messages API response
#[derive(Deserialize)]
struct AnthropicResponse {
    content: Vec<AnthropicBlock>,
}

#[derive(Deserialize)]
struct AnthropicBlock {
    #[serde(rename = "type")]
    block_type: String,
    text: Option<String>,
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

// ── Resolved provider context ─────────────────────────────────────────────────

#[derive(Debug, Clone)]
enum Provider {
    OpenAI { key: String, url: String, model: String },
    Groq   { key: String, model: String },
    Anthropic { key: String, model: String },
}

impl Provider {
    fn label(&self) -> &'static str {
        match self {
            Self::OpenAI { .. }    => "openai",
            Self::Groq { .. }      => "groq",
            Self::Anthropic { .. } => "anthropic",
        }
    }

    fn is_configured(&self) -> bool {
        match self {
            Self::OpenAI { key, url, .. }    => !key.is_empty() && !url.is_empty(),
            Self::Groq { key, .. }           => !key.is_empty(),
            Self::Anthropic { key, .. }      => !key.is_empty(),
        }
    }
}

/// Build a Provider from a named string + config.
fn provider_from_name(name: &str, cfg: &AppConfig, use_case: LlmUseCase) -> Option<Provider> {
    match name {
        "groq" => {
            let key = if use_case == LlmUseCase::Background && !cfg.groq_background_api_key.is_empty() {
                cfg.groq_background_api_key.clone()
            } else {
                cfg.groq_api_key.clone()
            };
            if !key.is_empty() {
                Some(Provider::Groq {
                    key,
                    model: "llama-3.3-70b-versatile".into(),
                })
            } else {
                None
            }
        }
        "anthropic" if !cfg.anthropic_api_key.is_empty() => Some(Provider::Anthropic {
            key: cfg.anthropic_api_key.clone(),
            model: cfg.anthropic_model.clone(),
        }),
        "openai" if !cfg.openai_api_key.is_empty() => {
            let base = cfg.openai_base_url.trim_end_matches('/');
            Some(Provider::OpenAI {
                key: cfg.openai_api_key.clone(),
                url: format!("{base}/chat/completions"),
                model: cfg.openai_model.clone(),
            })
        }
        _ => None,
    }
}

/// Collect every configured provider in priority order for the given use-case.
fn all_providers_for(cfg: &AppConfig, use_case: LlmUseCase) -> Vec<Provider> {
    // If user selected a specific provider, try that first
    let pref = match use_case {
        LlmUseCase::Chat       => cfg.primary_provider.as_str(),
        LlmUseCase::Background => cfg.background_provider.as_str(),
    };

    let mut out: Vec<Provider> = Vec::new();

    // Named preference (if not "auto")
    if pref != "auto" {
        if let Some(p) = provider_from_name(pref, cfg, use_case) {
            if p.is_configured() { out.push(p); }
        }
    }

    // Auto priority lists — different order per use-case to avoid starving the UI
    let fallback_order: &[&str] = match use_case {
        // Interactive: prefer fast/cheap providers (Groq as final fallback)
        LlmUseCase::Chat => &["groq", "openai", "anthropic"],
        // Background: prefer higher-quota/cheaper providers first
        LlmUseCase::Background => &["groq", "openai", "anthropic"],
    };

    for name in fallback_order {
        if let Some(p) = provider_from_name(name, cfg, use_case) {
            if p.is_configured() && !out.iter().any(|x| x.label() == p.label()) {
                out.push(p);
            }
        }
    }

    out
}

/// Convenience wrapper: resolve single (key, url, model) for legacy callers.
/// Prefers the Chat use-case ordering.
pub fn resolve_llm_endpoint(cfg: &AppConfig) -> (String, String, String) {
    match all_providers_for(cfg, LlmUseCase::Chat).into_iter().next() {
        Some(Provider::OpenAI    { key, url, model }) => (key, url, model),
        Some(Provider::Groq      { key, model })      => (
            key,
            "https://api.groq.com/openai/v1/chat/completions".into(),
            model,
        ),
        Some(Provider::Anthropic { key, model })      => (key, "anthropic".into(), model),
        None => (String::new(), String::new(), String::new()),
    }
}

// ── Core completion calls ─────────────────────────────────────────────────────

/// Streaming entry point — emits tokens via `on_token` as they arrive (SSE).
/// Falls back to a single non-streaming call for Anthropic.
/// Returns the full accumulated response text.
pub async fn complete_streaming<F>(
    cfg: &AppConfig,
    use_case: LlmUseCase,
    messages: Vec<LlmMessage>,
    max_tokens: Option<u32>,
    on_token: F,
) -> Result<String>
where
    F: Fn(String) + Send,
{
    let providers = all_providers_for(cfg, use_case);
    if providers.is_empty() {
        anyhow::bail!("No LLM provider configured. Add a key in Settings → API Keys.");
    }

    let mut last_err = anyhow::anyhow!("No providers attempted");
    for provider in &providers {
        let result = match provider {
            Provider::Anthropic { key, model } => {
                // Anthropic doesn't use the same SSE format; call non-streaming and emit once
                let _permit = anthropic_sem().acquire().await.ok();
                match call_anthropic(key, model, &messages, max_tokens).await {
                    Ok(text) => { on_token(text.clone()); Ok(text) }
                    Err(e) => Err(e),
                }
            }
            Provider::Groq { key, model } => {
                let _permit = groq_sem().acquire().await.ok();
                call_openai_streaming(
                    key,
                    "https://api.groq.com/openai/v1/chat/completions",
                    model, &messages, max_tokens, &on_token,
                ).await
            }
            Provider::OpenAI { key, url, model } => {
                let _permit = openai_sem().acquire().await.ok();
                call_openai_streaming(key, url, model, &messages, max_tokens, &on_token).await
            }
        };
        match result {
            Ok(text) => return Ok(text),
            Err(e) => {
                tracing::warn!("[LLM stream] Provider {} failed: {e} — trying next", provider.label());
                last_err = e;
            }
        }
    }
    Err(last_err)
}

/// SSE streaming call to any OpenAI-compatible endpoint.
async fn call_openai_streaming<F>(
    api_key: &str,
    url: &str,
    model: &str,
    messages: &[LlmMessage],
    max_tokens: Option<u32>,
    on_token: &F,
) -> Result<String>
where
    F: Fn(String),
{
    use futures_util::StreamExt;

    let req = LlmRequest {
        model: model.to_string(),
        messages: messages.to_vec(),
        stream: true,
        temperature: Some(0.3),
        max_tokens,
    };

    let mut builder = reqwest::Client::new().post(url).json(&req);
    builder = builder.header("Authorization", format!("Bearer {api_key}"));

    let resp = builder.send().await.context("Streaming LLM request failed")?;
    let status = resp.status();
    if !status.is_success() {
        let body = resp.text().await.unwrap_or_default();
        anyhow::bail!("LLM streaming error {status}: {}", &body[..body.len().min(300)]);
    }

    let mut stream = resp.bytes_stream();
    let mut full_text = String::new();
    let mut buf = String::new();

    while let Some(chunk) = stream.next().await {
        let bytes = chunk.context("SSE read error")?;
        buf.push_str(&String::from_utf8_lossy(&bytes));

        // Process all complete lines in the buffer
        while let Some(pos) = buf.find('\n') {
            let line = buf[..pos].trim().to_string();
            buf = buf[pos + 1..].to_string();

            if let Some(data) = line.strip_prefix("data: ") {
                if data == "[DONE]" { break; }
                if let Ok(v) = serde_json::from_str::<serde_json::Value>(data) {
                    if let Some(content) = v
                        .get("choices").and_then(|c| c.get(0))
                        .and_then(|c| c.get("delta"))
                        .and_then(|d| d.get("content"))
                        .and_then(|c| c.as_str())
                    {
                        if !content.is_empty() {
                            full_text.push_str(content);
                            on_token(content.to_string());
                        }
                    }
                }
            }
        }
    }

    Ok(full_text)
}

/// High-level entry point: pick best available provider for `use_case`,
/// retry once on 429/5xx, fall back to the next provider on failure.
pub async fn complete_for(
    cfg: &AppConfig,
    use_case: LlmUseCase,
    messages: Vec<LlmMessage>,
    max_tokens: Option<u32>,
) -> Result<String> {
    let providers = all_providers_for(cfg, use_case);
    if providers.is_empty() {
        anyhow::bail!("No LLM provider configured. Add a key in Settings → API Keys.");
    }

    let mut last_err = anyhow::anyhow!("No providers attempted");
    for provider in &providers {
        match call_provider(provider, messages.clone(), max_tokens).await {
            Ok(text) => return Ok(text),
            Err(e) => {
                tracing::warn!("[LLM] Provider {} failed: {e} — trying next", provider.label());
                last_err = e;
            }
        }
    }
    Err(last_err)
}

async fn call_provider(
    provider: &Provider,
    messages: Vec<LlmMessage>,
    max_tokens: Option<u32>,
) -> Result<String> {
    const MAX_RETRIES: u32 = 2;
    let mut backoff_ms = 400u64;

    for attempt in 0..MAX_RETRIES {
        let result = match provider {
            Provider::Anthropic { key, model } => {
                let _permit = anthropic_sem().acquire().await.ok();
                call_anthropic(key, model, &messages, max_tokens).await
            }
            Provider::Groq { key, model } => {
                let _permit = groq_sem().acquire().await.ok();
                call_openai_compat(
                    key,
                    "https://api.groq.com/openai/v1/chat/completions",
                    model,
                    &messages,
                    max_tokens,
                ).await
            }
            Provider::OpenAI { key, url, model } => {
                let _permit = openai_sem().acquire().await.ok();
                call_openai_compat(key, url, model, &messages, max_tokens).await
            }
        };

        match result {
            Ok(text) => return Ok(text),
            Err(ref e) if is_retryable(e) && attempt < MAX_RETRIES - 1 => {
                tracing::warn!("[LLM] Retryable error (attempt {attempt}): {e} — waiting {backoff_ms}ms");
                tokio::time::sleep(tokio::time::Duration::from_millis(backoff_ms)).await;
                backoff_ms *= 3;
            }
            Err(e) => return Err(e),
        }
    }
    unreachable!()
}

fn is_retryable(e: &anyhow::Error) -> bool {
    let msg = e.to_string();
    msg.contains("429") || msg.contains("503") || msg.contains("529") || msg.contains("overloaded")
}

/// Legacy single-provider call (used by callers that already resolved the endpoint).
pub async fn complete(
    api_key: &str,
    url: &str,
    model: &str,
    messages: Vec<LlmMessage>,
    max_tokens: Option<u32>,
) -> Result<String> {
    if url == "anthropic" {
        return call_anthropic(api_key, model, &messages, max_tokens).await;
    }
    call_openai_compat(api_key, url, model, &messages, max_tokens).await
}

async fn call_openai_compat(
    api_key: &str,
    url: &str,
    model: &str,
    messages: &[LlmMessage],
    max_tokens: Option<u32>,
) -> Result<String> {
    let req = LlmRequest {
        model: model.to_string(),
        messages: messages.to_vec(),
        stream: false,
        temperature: Some(0.3),
        max_tokens,
    };

    let mut builder = reqwest::Client::new().post(url).json(&req);
    builder = builder.header("Authorization", format!("Bearer {api_key}"));

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

/// Call Anthropic Messages API.
/// The first message with role="system" is extracted as the system prompt.
async fn call_anthropic(
    api_key: &str,
    model: &str,
    messages: &[LlmMessage],
    max_tokens: Option<u32>,
) -> Result<String> {
    // Separate system prompt from conversation messages
    let system: Option<String> = messages.iter()
        .find(|m| m.role == "system")
        .map(|m| m.content.clone());

    let conv_messages: Vec<serde_json::Value> = messages.iter()
        .filter(|m| m.role != "system")
        .map(|m| serde_json::json!({ "role": m.role, "content": m.content }))
        .collect();

    // Anthropic requires at least one message
    if conv_messages.is_empty() {
        anyhow::bail!("Anthropic requires at least one non-system message");
    }

    let mut body = serde_json::json!({
        "model": model,
        "max_tokens": max_tokens.unwrap_or(1024),
        "messages": conv_messages,
    });
    if let Some(sys) = system {
        body["system"] = serde_json::Value::String(sys);
    }

    let resp = reqwest::Client::new()
        .post("https://api.anthropic.com/v1/messages")
        .header("x-api-key", api_key)
        .header("anthropic-version", "2023-06-01")
        .header("content-type", "application/json")
        .json(&body)
        .send()
        .await
        .context("Anthropic request failed")?;

    let status = resp.status();
    let text = resp.text().await.unwrap_or_default();

    if !status.is_success() {
        anyhow::bail!("Anthropic error {status}: {}", &text[..text.len().min(400)]);
    }

    let parsed: AnthropicResponse = serde_json::from_str(&text)
        .with_context(|| format!("Failed to parse Anthropic response: {}", &text[..text.len().min(300)]))?;

    parsed.content.into_iter()
        .find(|b| b.block_type == "text")
        .and_then(|b| b.text)
        .context("Anthropic returned no text block")
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

    if all_providers_for(cfg, LlmUseCase::Background).is_empty() {
        tracing::warn!("[LLM] No LLM provider configured, skipping summarization");
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

    let summary_result = complete_for(
        cfg,
        LlmUseCase::Background,
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

    let action_result = complete_for(
        cfg,
        LlmUseCase::Background,
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

    let memory_result = complete_for(
        cfg,
        LlmUseCase::Background,
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
                        let backend_url = cfg.backend_url.clone();
                        let token = cfg.firebase_id_token.clone();
                        let c_content = content.to_string();
                        let c_category = category.unwrap_or("interesting").to_string();
                        tokio::spawn(async move {
                            crate::sync::upload_memory(backend_url, token, c_content, c_category).await;
                        });
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

    if all_providers_for(cfg, LlmUseCase::Background).is_empty() {
        tracing::warn!("[LLM] No LLM provider configured, skipping OCR summarization");
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

    let resp = complete_for(
        cfg,
        LlmUseCase::Background,
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

    if all_providers_for(cfg, LlmUseCase::Background).is_empty() {
        tracing::warn!("[LLM] No LLM provider configured, skipping screenshot extraction");
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

    let resp = complete_for(
        cfg,
        LlmUseCase::Background,
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

    let resp = complete_for(
        cfg,
        LlmUseCase::Background,
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