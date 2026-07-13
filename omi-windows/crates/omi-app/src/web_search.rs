use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};

use crate::config::AppConfig;

const TAVILY_SEARCH_URL: &str = "https://api.tavily.com/search";

#[derive(Debug, Clone, Serialize)]
struct TavilyRequest {
    api_key: String,
    query: String,
    max_results: u8,
    include_answer: bool,
    search_depth: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct TavilyResponse {
    pub answer: Option<String>,
    pub results: Vec<TavilyResult>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct TavilyResult {
    pub title: String,
    pub url: String,
    pub content: String,
    pub score: f64,
}

pub async fn needs_web_search(query: &str, cfg: &AppConfig) -> bool {
    let (api_key, url, model) = crate::llm::resolve_llm_endpoint(cfg);
    if api_key.is_empty() {
        return false;
    }

    let messages = vec![
        crate::llm::LlmMessage {
            role: "system".into(),
            content: "You are a routing classifier. Given a user message, decide whether answering it \
                      requires a live web search (real-time info, current events, prices, weather, \
                      recent news, sports scores, product lookups, anything your training data may \
                      not cover). Respond with EXACTLY one word: YES or NO. Nothing else.".into(),
        },
        crate::llm::LlmMessage {
            role: "user".into(),
            content: query.to_string(),
        },
    ];

    match crate::llm::complete(&api_key, &url, &model, messages, Some(3)).await {
        Ok(answer) => {
            let decision = answer.trim().to_uppercase();
            let needs = decision.starts_with("YES");
            tracing::info!("[WEBSEARCH] LLM classifier: {query:.60} → {decision} (search={needs})");
            needs
        }
        Err(e) => {
            tracing::warn!("[WEBSEARCH] Classifier LLM call failed: {e:#}, skipping search");
            false
        }
    }
}

pub async fn search(query: &str, cfg: &AppConfig) -> Result<TavilyResponse> {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(10))
        .build()
        .context("Failed to build HTTP client")?;

    let body = TavilyRequest {
        api_key: cfg.tavily_api_key.clone(),
        query: query.to_string(),
        max_results: 5,
        include_answer: true,
        search_depth: "basic".into(),
    };

    tracing::info!("[WEBSEARCH] Tavily query: {}", &query[..query.len().min(80)]);

    let resp = client
        .post(TAVILY_SEARCH_URL)
        .json(&body)
        .send()
        .await
        .context("Tavily request failed")?;

    if !resp.status().is_success() {
        let status = resp.status();
        let body = resp.text().await.unwrap_or_default();
        anyhow::bail!("Tavily error {status}: {}", &body[..body.len().min(200)]);
    }

    let result: TavilyResponse = resp.json().await.context("Failed to parse Tavily response")?;
    tracing::info!(
        "[WEBSEARCH] Got {} results, answer={}",
        result.results.len(),
        result.answer.is_some()
    );
    Ok(result)
}

pub fn format_search_context(response: &TavilyResponse) -> String {
    let mut ctx = String::from("## Web Search Results\n\n");

    if let Some(ref answer) = response.answer {
        ctx.push_str(&format!("**Summary:** {answer}\n\n"));
    }

    for (i, r) in response.results.iter().take(5).enumerate() {
        let snippet = if r.content.len() > 300 {
            format!("{}…", &r.content[..300])
        } else {
            r.content.clone()
        };
        ctx.push_str(&format!("{}. **{}**\n   {}\n   {}\n\n", i + 1, r.title, snippet, r.url));
    }

    ctx
}
