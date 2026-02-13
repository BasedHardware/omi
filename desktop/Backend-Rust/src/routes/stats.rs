// Stats routes - PostHog analytics queries

use axum::{
    extract::State,
    http::StatusCode,
    routing::get,
    Json, Router,
};
use serde::{Deserialize, Serialize};

use crate::auth::AuthUser;
use crate::AppState;

#[derive(Serialize)]
struct ChatMessageCountResponse {
    count: u64,
}

#[derive(Serialize)]
struct HogQLQuery {
    query: HogQLQueryInner,
}

#[derive(Serialize)]
struct HogQLQueryInner {
    kind: String,
    query: String,
}

#[derive(Deserialize)]
struct HogQLResponse {
    results: Option<Vec<Vec<serde_json::Value>>>,
}

/// GET /v1/users/stats/chat-messages - Get count of chat messages from PostHog
async fn get_chat_message_count(
    State(state): State<AppState>,
    user: AuthUser,
) -> Result<Json<ChatMessageCountResponse>, (StatusCode, String)> {
    let api_key = match &state.config.posthog_api_key {
        Some(key) => key.clone(),
        None => {
            tracing::warn!("PostHog API key not configured");
            return Ok(Json(ChatMessageCountResponse { count: 0 }));
        }
    };

    let project_id = &state.config.posthog_project_id;
    let url = format!(
        "https://us.posthog.com/api/projects/{}/query/",
        project_id
    );

    let hogql = format!(
        "SELECT count() as cnt FROM events WHERE event = 'Chat Message Sent' AND distinct_id = '{}'",
        user.uid.replace('\'', "''")
    );

    let body = HogQLQuery {
        query: HogQLQueryInner {
            kind: "HogQLQuery".to_string(),
            query: hogql,
        },
    };

    let client = reqwest::Client::new();
    let response = client
        .post(&url)
        .header("Authorization", format!("Bearer {}", api_key))
        .json(&body)
        .send()
        .await
        .map_err(|e| {
            tracing::error!("PostHog request failed: {}", e);
            (StatusCode::INTERNAL_SERVER_ERROR, format!("PostHog request failed: {}", e))
        })?;

    if !response.status().is_success() {
        let status = response.status();
        let text = response.text().await.unwrap_or_default();
        tracing::error!("PostHog returned {}: {}", status, text);
        return Ok(Json(ChatMessageCountResponse { count: 0 }));
    }

    let hogql_response: HogQLResponse = response.json().await.map_err(|e| {
        tracing::error!("Failed to parse PostHog response: {}", e);
        (StatusCode::INTERNAL_SERVER_ERROR, format!("Failed to parse PostHog response: {}", e))
    })?;

    let count = hogql_response
        .results
        .and_then(|rows| rows.first().cloned())
        .and_then(|row| row.first().cloned())
        .and_then(|val| val.as_u64())
        .unwrap_or(0);

    Ok(Json(ChatMessageCountResponse { count }))
}

pub fn stats_routes() -> Router<AppState> {
    Router::new()
        .route("/v1/users/stats/chat-messages", get(get_chat_message_count))
}
