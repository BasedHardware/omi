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
use std::collections::HashMap;
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::sync::RwLock;

use crate::auth::AuthUser;
use crate::AppState;

/// In-memory cache: email (lowercase) → (session_id, cached_at)
/// Session IDs are stable, so we cache for 1 hour to avoid re-scanning
/// conversation lists on every poll.
pub type SessionCache = Arc<RwLock<HashMap<String, (String, Instant)>>>;

const SESSION_CACHE_TTL_SECS: u64 = 3600; // 1 hour

/// Hard cap on distinct cached emails. Without eviction the map grew by one
/// entry per distinct authenticated email forever (unbounded memory). This is
/// a safety backstop above the expiry sweep, not a working-set limit.
const SESSION_CACHE_MAX_ENTRIES: usize = 50_000;

pub fn new_session_cache() -> SessionCache {
    Arc::new(RwLock::new(HashMap::new()))
}

/// Remove entries older than `ttl` relative to `now`, then, if still above
/// `max_entries`, drop the oldest until at the cap. Pure over the map with an
/// injected `now` so the bound is testable without wall-clock.
fn prune_sessions(
    map: &mut HashMap<String, (String, Instant)>,
    now: Instant,
    ttl: Duration,
    max_entries: usize,
) {
    map.retain(|_, (_, cached_at)| now.saturating_duration_since(*cached_at) < ttl);
    if map.len() <= max_entries {
        return;
    }
    let mut by_age: Vec<(String, Instant)> =
        map.iter().map(|(k, (_, at))| (k.clone(), *at)).collect();
    // Oldest first.
    by_age.sort_by_key(|(_, at)| *at);
    let excess = map.len() - max_entries;
    for (key, _) in by_age.into_iter().take(excess) {
        map.remove(&key);
    }
}

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

/// Look up cached session_id for an email, returning None if expired or absent.
async fn get_cached_session(cache: &SessionCache, email: &str) -> Option<String> {
    let map = cache.read().await;
    if let Some((session_id, cached_at)) = map.get(email) {
        if cached_at.elapsed().as_secs() < SESSION_CACHE_TTL_SECS {
            return Some(session_id.clone());
        }
    }
    None
}

/// Store a session_id in the cache, pruning expired and over-cap entries so
/// the map cannot grow without bound across distinct authenticated emails.
async fn set_cached_session(cache: &SessionCache, email: String, session_id: String) {
    let now = Instant::now();
    let mut map = cache.write().await;
    map.insert(email, (session_id, now));
    prune_sessions(
        &mut map,
        now,
        Duration::from_secs(SESSION_CACHE_TTL_SECS),
        SESSION_CACHE_MAX_ENTRIES,
    );
}

/// Find session_id by searching conversation pages (expensive — up to 5 API calls).
async fn find_session_by_email(
    client: &reqwest::Client,
    auth: &str,
    website_id: &str,
    email: &str,
) -> Result<Option<String>, StatusCode> {
    for page in 1..=5 {
        let conversations_url = format!(
            "https://api.crisp.chat/v1/website/{}/conversations/{}",
            website_id, page
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
            tracing::warn!(
                "Crisp API conversations page {} returned {}: {}",
                page,
                status,
                body
            );
            break;
        }

        let conversations: CrispConversationsResponse =
            conv_response.json().await.map_err(|e| {
                tracing::warn!("Failed to parse Crisp conversations: {}", e);
                StatusCode::BAD_GATEWAY
            })?;

        let convs = conversations.data.unwrap_or_default();
        if convs.is_empty() {
            break;
        }

        if let Some(found) = convs.iter().find(|c| {
            c.meta
                .as_ref()
                .and_then(|m| m.email.as_ref())
                .map(|e| e.eq_ignore_ascii_case(email))
                .unwrap_or(false)
        }) {
            return Ok(Some(found.session_id.clone()));
        }
    }
    Ok(None)
}

/// GET /v1/crisp/unread - Check for unread operator messages
///
/// Finds the user's Crisp conversation by email (cached), then returns
/// operator messages newer than the `since` timestamp.
async fn get_unread_messages(
    State(state): State<AppState>,
    user: AuthUser,
    Query(query): Query<UnreadQuery>,
) -> Result<Json<UnreadResponse>, StatusCode> {
    let config = &state.config;

    let (identifier, key, website_id) = match (
        config.crisp_plugin_identifier.as_ref(),
        config.crisp_plugin_key.as_ref(),
        config.crisp_website_id.as_ref(),
    ) {
        (Some(id), Some(k), Some(wid)) => (id, k, wid),
        _ => {
            // Crisp not configured — return empty (feature disabled, not an error)
            return Ok(Json(UnreadResponse {
                unread_count: 0,
                messages: vec![],
            }));
        }
    };

    let email = match &user.email {
        Some(e) => {
            tracing::info!("Crisp unread check for {} ({})", user.uid, e);
            e.clone()
        }
        None => {
            tracing::info!("Crisp: no email in auth token for user {}", user.uid);
            return Ok(Json(UnreadResponse {
                unread_count: 0,
                messages: vec![],
            }));
        }
    };

    let auth = BASE64.encode(format!("{}:{}", identifier, key));
    let client = crate::services::http::bounded_client(std::time::Duration::from_secs(15));
    let email_lower = email.to_lowercase();

    // Try cache first, then fall back to conversation list search
    let session_id =
        if let Some(cached) = get_cached_session(&state.crisp_session_cache, &email_lower).await {
            tracing::info!("Crisp: cache hit for {} -> {}", email, cached);
            cached
        } else {
            match find_session_by_email(&client, &auth, website_id, &email).await? {
                Some(id) => {
                    tracing::info!("Crisp: found session {} for {} (caching)", id, email);
                    set_cached_session(&state.crisp_session_cache, email_lower, id.clone()).await;
                    id
                }
                None => {
                    tracing::info!("Crisp: no conversation found for email {}", email);
                    return Ok(Json(UnreadResponse {
                        unread_count: 0,
                        messages: vec![],
                    }));
                }
            }
        };

    // Fetch messages for this conversation (1 API call)
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
        return Ok(Json(UnreadResponse {
            unread_count: 0,
            messages: vec![],
        }));
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

    tracing::info!(
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn prune_removes_expired_entries() {
        let ttl = Duration::from_secs(SESSION_CACHE_TTL_SECS);
        let base = Instant::now();
        let mut map = HashMap::new();
        map.insert("fresh@x.com".to_string(), ("s1".to_string(), base));
        map.insert(
            "stale@x.com".to_string(),
            (
                "s2".to_string(),
                base - Duration::from_secs(SESSION_CACHE_TTL_SECS + 1),
            ),
        );

        prune_sessions(&mut map, base, ttl, SESSION_CACHE_MAX_ENTRIES);

        assert!(map.contains_key("fresh@x.com"));
        assert!(
            !map.contains_key("stale@x.com"),
            "expired entry must be evicted"
        );
    }

    #[test]
    fn prune_caps_map_size_dropping_oldest() {
        let ttl = Duration::from_secs(SESSION_CACHE_TTL_SECS);
        let base = Instant::now();
        let mut map = HashMap::new();
        // All within TTL, but more than the cap; oldest must go first.
        for i in 0..10u64 {
            map.insert(
                format!("user{i}@x.com"),
                (format!("s{i}"), base + Duration::from_millis(i)),
            );
        }

        prune_sessions(&mut map, base + Duration::from_secs(1), ttl, 4);

        assert_eq!(map.len(), 4, "map must be capped at max_entries");
        // The 4 newest (i = 6..=9) survive; the 6 oldest are dropped.
        assert!(map.contains_key("user9@x.com"));
        assert!(!map.contains_key("user0@x.com"));
    }
}
