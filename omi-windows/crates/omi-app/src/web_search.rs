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

pub fn should_search(query: &str) -> bool {
    let q = query.to_lowercase();
    let indicators = [
        "search", "look up", "find", "what is", "what are", "who is", "who are",
        "when did", "when was", "when is", "where is", "where are", "how to",
        "how do", "how does", "how much", "how many", "latest", "recent",
        "current", "today", "news", "weather", "price", "stock", "score",
        "update", "status", "release", "version", "compare", "vs",
        "best", "top", "review", "recommend", "definition", "meaning",
        "explain", "tell me about", "search the web", "google",
    ];
    indicators.iter().any(|kw| q.contains(kw))
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
