// Crisp chat routes - Check for unread operator messages
// Used by the desktop app to show notifications for "Help from Founder"

use axum::{
    extract::{Query, State},
    http::StatusCode,
    routing::get,
    Json, Router,
};
use base64::{engine::general_purpose::STANDARD as BASE64, Engine};
use serde::{Deserialize, Serialize};

use crate::auth::AuthUser;
use crate::AppState;

/// Query parameters for unread check
#[derive(Deserialize)]
struct UnreadQuery {
    /// Only return messages after this timestamp (seconds since epoch)
    #[serde(default)]
    since: Option<u64>,
}

/// A single operator message
#[derive(Serialize)]
struct OperatorMessage {
    text: String,
    timestamp: u64,
    from: String,
}

/// Response for unread messages endpoint
#[derive(Serialize)]
struct UnreadResponse {
    unread_count: usize,
    messages: Vec<OperatorMessage>,
}

/// Crisp API conversation list item
#[derive(Deserialize)]
struct CrispConversation {
    session_id: String,
    meta: Option<CrispConversationMeta>,
}

#[derive(Deserialize)]
struct CrispConversationMeta {
    email: Option<String>,
}

/// Crisp API conversation list response
#[derive(Deserialize)]
struct CrispConversationsResponse {
    data: Option<Vec<CrispConversation>>,
}

/// Crisp API message
#[derive(Deserialize)]
struct CrispMessage {
    content: Option<serde_json::Value>,
    from: Option<String>,
    timestamp: Option<u64>,
    #[serde(rename = "type")]
    msg_type: Option<String>,
}

/// Crisp API messages response
#[derive(Deserialize)]
struct CrispMessagesResponse {
    data: Option<Vec<CrispMessage>>,
}

/// GET /v1/crisp/unread - Check for unread operator messages
///
/// Finds the user's Crisp conversation by email, then returns
/// operator messages newer than the `since` timestamp.
async fn get_unread_messages(
    State(state): State<AppState>,
    user: AuthUser,
    Query(query): Query<UnreadQuery>,
) -> Result<Json<UnreadResponse>, StatusCode> {
    let config = &state.config;

    let identifier = config.crisp_plugin_identifier.as_ref().ok_or_else(|| {
        tracing::warn!("Crisp plugin identifier not configured");
        StatusCode::SERVICE_UNAVAILABLE
    })?;
    let key = config.crisp_plugin_key.as_ref().ok_or_else(|| {
        tracing::warn!("Crisp plugin key not configured");
        StatusCode::SERVICE_UNAVAILABLE
    })?;
    let website_id = config.crisp_website_id.as_ref().ok_or_else(|| {
        tracing::warn!("Crisp website ID not configured");
        StatusCode::SERVICE_UNAVAILABLE
    })?;

    // Look up user email from Firestore
    let email = match state.firestore.get_user_email(&user.uid).await {
        Ok(Some(e)) => e,
        Ok(None) => {
            tracing::debug!("No email found for user {}", user.uid);
            return Ok(Json(UnreadResponse { unread_count: 0, messages: vec![] }));
        }
        Err(e) => {
            tracing::warn!("Failed to get user email: {}", e);
            return Ok(Json(UnreadResponse { unread_count: 0, messages: vec![] }));
        }
    };

    // Build auth header for Crisp API
    let auth = BASE64.encode(format!("{}:{}", identifier, key));
    let client = reqwest::Client::new();

    // Search conversations by email
    let conversations_url = format!(
        "https://api.crisp.chat/v1/website/{}/conversations/1?search_query={}&search_type=segment",
        website_id,
        urlencoding::encode(&email)
    );

    let conv_response = client
        .get(&conversations_url)
        .header("Authorization", format!("Basic {}", auth))
        .header("X-Crisp-Tier", "plugin")
        .send()
        .await
        .map_err(|e| {
            tracing::warn!("Crisp API conversations request failed: {}", e);
            StatusCode::BAD_GATEWAY
        })?;

    if !conv_response.status().is_success() {
        let status = conv_response.status();
        let body = conv_response.text().await.unwrap_or_default();
        tracing::warn!("Crisp API conversations returned {}: {}", status, body);
        return Ok(Json(UnreadResponse { unread_count: 0, messages: vec![] }));
    }

    let conversations: CrispConversationsResponse = conv_response.json().await.map_err(|e| {
        tracing::warn!("Failed to parse Crisp conversations: {}", e);
        StatusCode::BAD_GATEWAY
    })?;

    // Find the conversation matching this email
    let session_id = conversations
        .data
        .as_ref()
        .and_then(|convs| {
            convs.iter().find(|c| {
                c.meta
                    .as_ref()
                    .and_then(|m| m.email.as_ref())
                    .map(|e| e.eq_ignore_ascii_case(&email))
                    .unwrap_or(false)
            })
        })
        .map(|c| c.session_id.clone());

    let session_id = match session_id {
        Some(id) => id,
        None => {
            tracing::debug!("No Crisp conversation found for email {}", email);
            return Ok(Json(UnreadResponse { unread_count: 0, messages: vec![] }));
        }
    };

    // Fetch messages for this conversation
    let messages_url = format!(
        "https://api.crisp.chat/v1/website/{}/conversation/{}/messages",
        website_id, session_id
    );

    let msg_response = client
        .get(&messages_url)
        .header("Authorization", format!("Basic {}", auth))
        .header("X-Crisp-Tier", "plugin")
        .send()
        .await
        .map_err(|e| {
            tracing::warn!("Crisp API messages request failed: {}", e);
            StatusCode::BAD_GATEWAY
        })?;

    if !msg_response.status().is_success() {
        let status = msg_response.status();
        let body = msg_response.text().await.unwrap_or_default();
        tracing::warn!("Crisp API messages returned {}: {}", status, body);
        return Ok(Json(UnreadResponse { unread_count: 0, messages: vec![] }));
    }

    let messages: CrispMessagesResponse = msg_response.json().await.map_err(|e| {
        tracing::warn!("Failed to parse Crisp messages: {}", e);
        StatusCode::BAD_GATEWAY
    })?;

    let since = query.since.unwrap_or(0);

    // Filter to operator text messages after `since`
    let operator_messages: Vec<OperatorMessage> = messages
        .data
        .unwrap_or_default()
        .into_iter()
        .filter(|m| {
            m.from.as_deref() == Some("operator")
                && m.msg_type.as_deref() == Some("text")
                && m.timestamp.unwrap_or(0) > since
        })
        .filter_map(|m| {
            let text = match &m.content {
                Some(serde_json::Value::String(s)) => s.clone(),
                Some(v) => v.to_string(),
                None => return None,
            };
            Some(OperatorMessage {
                text,
                timestamp: m.timestamp.unwrap_or(0),
                from: "operator".to_string(),
            })
        })
        .collect();

    tracing::debug!(
        "Crisp unread for {}: {} operator messages since {}",
        email,
        operator_messages.len(),
        since
    );

    Ok(Json(UnreadResponse {
        unread_count: operator_messages.len(),
        messages: operator_messages,
    }))
}

pub fn crisp_routes() -> Router<AppState> {
    Router::new().route("/v1/crisp/unread", get(get_unread_messages))
}
