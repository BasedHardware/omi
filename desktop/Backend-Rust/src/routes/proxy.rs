// API proxy routes — forward Gemini and Deepgram requests to upstream APIs.
// Keys stay server-side; desktop client authenticates via Firebase token only.
//
// Issue #5861: Remove client-side API key exposure risk.
// Issue #6098 L2: Tiered rate limiting with Pro→Flash degradation.

use axum::{
    body::Bytes,
    extract::{Path, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::{any, post},
    Router,
};

use crate::auth::AuthUser;
use crate::AppState;

use super::rate_limit::{self, RateDecision};

// Allowed Gemini API actions (suffix after model name)
const GEMINI_ALLOWED_ACTIONS: &[&str] = &[
    "generateContent",
    "streamGenerateContent",
    "embedContent",
    "batchEmbedContents",
];

/// Proxy-specific error type — allows JSON 429 responses alongside bare status codes.
enum ProxyError {
    Status(StatusCode),
    RateLimited,
}

impl IntoResponse for ProxyError {
    fn into_response(self) -> Response {
        match self {
            ProxyError::Status(status) => status.into_response(),
            ProxyError::RateLimited => {
                // Message must contain "resource exhausted" or "429" for Swift GeminiClient
                // to treat it as a transient error and apply retry backoff.
                let body = rate_limit::rate_limit_error_json(
                    "Resource exhausted: rate limit exceeded. Please try again later.",
                );
                Response::builder()
                    .status(StatusCode::TOO_MANY_REQUESTS)
                    .header("content-type", "application/json")
                    .header("retry-after", "60")
                    .body(axum::body::Body::from(body))
                    .unwrap()
            }
        }
    }
}

/// POST /v1/proxy/gemini/*path
/// Proxies requests to https://generativelanguage.googleapis.com/v1beta/...
/// Appends the server-side Gemini API key. Client sends Bearer Firebase token.
/// Rate-limited per user: Tier 1 (allow), Tier 2 (degrade Pro→Flash), Tier 3 (reject 429).
async fn gemini_proxy(
    State(state): State<AppState>,
    user: AuthUser,
    Path(path): Path<String>,
    body: Bytes,
) -> Result<Response, ProxyError> {
    let gemini_key = state
        .config
        .gemini_api_key
        .as_ref()
        .ok_or(ProxyError::Status(StatusCode::SERVICE_UNAVAILABLE))?;

    // Validate the action is in our allowlist
    let action = extract_gemini_action(&path);
    if !is_gemini_action_allowed(action) {
        tracing::warn!("gemini_proxy: blocked action '{}' in path '{}'", action, path);
        return Err(ProxyError::Status(StatusCode::FORBIDDEN));
    }

    // Rate limit check
    let decision = state.gemini_rate_limiter.check_and_record(&user.uid, state.redis.as_ref()).await;
    if decision == RateDecision::Reject {
        tracing::warn!("gemini_proxy: rate limit rejected uid={}", user.uid);
        return Err(ProxyError::RateLimited);
    }

    // Apply model degradation if needed
    let effective_path = rate_limit::maybe_rewrite_model_path(&path, &decision, action);
    if effective_path != path {
        tracing::info!(
            "gemini_proxy: degraded uid={} {} -> {}",
            user.uid,
            path,
            effective_path
        );
    }

    let url = build_gemini_url(&effective_path, gemini_key);

    let upstream = reqwest::Client::new()
        .post(&url)
        .header("content-type", "application/json")
        .body(body)
        .send()
        .await
        .map_err(|e| {
            tracing::error!("gemini_proxy: upstream request failed: {}", e);
            ProxyError::Status(StatusCode::BAD_GATEWAY)
        })?;

    let status =
        StatusCode::from_u16(upstream.status().as_u16()).unwrap_or(StatusCode::BAD_GATEWAY);
    let bytes = upstream.bytes().await.map_err(|e| {
        tracing::error!("gemini_proxy: failed to read upstream body: {}", e);
        ProxyError::Status(StatusCode::BAD_GATEWAY)
    })?;

    Ok((status, bytes).into_response())
}

/// POST /v1/proxy/gemini-stream/*path
/// Same as gemini_proxy but streams the response using SSE (for streamGenerateContent).
/// Rate-limited per user with same tiers as gemini_proxy.
async fn gemini_stream_proxy(
    State(state): State<AppState>,
    user: AuthUser,
    Path(path): Path<String>,
    axum::extract::Query(query): axum::extract::Query<std::collections::HashMap<String, String>>,
    body: Bytes,
) -> Result<Response, ProxyError> {
    let gemini_key = state
        .config
        .gemini_api_key
        .as_ref()
        .ok_or(ProxyError::Status(StatusCode::SERVICE_UNAVAILABLE))?;

    // Validate the action
    let action = extract_gemini_action(&path);
    if !is_gemini_action_allowed(action) {
        tracing::warn!("gemini_stream_proxy: blocked action '{}'", action);
        return Err(ProxyError::Status(StatusCode::FORBIDDEN));
    }

    // Rate limit check
    let decision = state.gemini_rate_limiter.check_and_record(&user.uid, state.redis.as_ref()).await;
    if decision == RateDecision::Reject {
        tracing::warn!("gemini_stream_proxy: rate limit rejected uid={}", user.uid);
        return Err(ProxyError::RateLimited);
    }

    // Apply model degradation if needed
    let effective_path = rate_limit::maybe_rewrite_model_path(&path, &decision, action);
    if effective_path != path {
        tracing::info!(
            "gemini_stream_proxy: degraded uid={} {} -> {}",
            user.uid,
            path,
            effective_path
        );
    }

    // Build upstream URL with query params (e.g., alt=sse)
    let upstream_url = build_gemini_stream_url(&effective_path, gemini_key, &query);

    let upstream = reqwest::Client::new()
        .post(&upstream_url)
        .header("content-type", "application/json")
        .body(body)
        .send()
        .await
        .map_err(|e| {
            tracing::error!("gemini_stream_proxy: upstream request failed: {}", e);
            ProxyError::Status(StatusCode::BAD_GATEWAY)
        })?;

    let status =
        StatusCode::from_u16(upstream.status().as_u16()).unwrap_or(StatusCode::BAD_GATEWAY);

    // Stream the response body through
    let stream = upstream.bytes_stream();
    let body = axum::body::Body::from_stream(stream);

    Ok(Response::builder()
        .status(status)
        .header("content-type", "text/event-stream")
        .body(body)
        .unwrap())
}

/// Check if the Deepgram proxy deprecation period has passed.
/// Returns true after 2026-04-05 05:00:00 UTC (24h after migration PR #6287 merge).
fn is_deepgram_proxy_deprecated() -> bool {
    use std::time::{SystemTime, UNIX_EPOCH};
    // 2026-04-05 05:00:00 UTC = 1775,541,600 seconds since epoch
    const DEPRECATION_TIMESTAMP: u64 = 1_775_541_600;
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs() >= DEPRECATION_TIMESTAMP)
        .unwrap_or(false)
}

/// POST /v1/proxy/deepgram/v1/listen — DEPRECATED.
/// STT moved to Python backend endpoints: POST /v2/voice-message/transcribe
/// and WS /v2/voice-message/transcribe-stream (PR #6287).
/// Returns 410 Gone after 2026-04-05 05:00 UTC; proxies to Deepgram until then.
async fn deepgram_listen_proxy(
    State(state): State<AppState>,
    _user: AuthUser,
    axum::extract::OriginalUri(original_uri): axum::extract::OriginalUri,
    body: Bytes,
) -> Result<Response, StatusCode> {
    if is_deepgram_proxy_deprecated() {
        tracing::warn!("deepgram_listen_proxy: endpoint deprecated, returning 410 Gone");
        return Ok((
            StatusCode::GONE,
            "Deepgram proxy is deprecated. Use POST /v2/voice-message/transcribe instead.",
        )
            .into_response());
    }

    let dg_key = state
        .config
        .deepgram_api_key
        .as_ref()
        .ok_or(StatusCode::SERVICE_UNAVAILABLE)?;

    let query = original_uri.query().unwrap_or("");
    let url = build_deepgram_rest_url(query);

    let upstream = reqwest::Client::new()
        .post(&url)
        .header("authorization", build_deepgram_auth_header(dg_key))
        .header("content-type", "application/octet-stream")
        .body(body)
        .send()
        .await
        .map_err(|e| {
            tracing::error!("deepgram_listen_proxy: upstream request failed: {}", e);
            StatusCode::BAD_GATEWAY
        })?;

    let status =
        StatusCode::from_u16(upstream.status().as_u16()).unwrap_or(StatusCode::BAD_GATEWAY);
    let bytes = upstream.bytes().await.map_err(|e| {
        tracing::error!("deepgram_listen_proxy: failed to read upstream body: {}", e);
        StatusCode::BAD_GATEWAY
    })?;

    Ok((status, bytes).into_response())
}

/// WS /v1/proxy/deepgram/ws/v1/listen — DEPRECATED.
/// STT moved to Python backend: WS /v2/voice-message/transcribe-stream (PR #6287).
/// Returns 410 Gone after 2026-04-05 05:00 UTC; proxies to Deepgram until then.
async fn deepgram_ws_proxy(
    ws: axum::extract::WebSocketUpgrade,
    State(state): State<AppState>,
    _user: AuthUser,
    axum::extract::OriginalUri(original_uri): axum::extract::OriginalUri,
) -> Result<Response, StatusCode> {
    if is_deepgram_proxy_deprecated() {
        tracing::warn!("deepgram_ws_proxy: endpoint deprecated, returning 410 Gone");
        return Ok((
            StatusCode::GONE,
            "Deepgram WS proxy is deprecated. Use WS /v2/voice-message/transcribe-stream instead.",
        )
            .into_response());
    }

    let dg_key = state
        .config
        .deepgram_api_key
        .as_ref()
        .ok_or(StatusCode::SERVICE_UNAVAILABLE)?
        .clone();

    let query = original_uri.query().unwrap_or("").to_string();
    let upstream_url = build_deepgram_ws_url(&query);

    Ok(ws.on_upgrade(move |client_socket| async move {
        if let Err(e) = proxy_ws_bidirectional(client_socket, &upstream_url, &dg_key).await {
            tracing::error!("deepgram_ws_proxy: proxy error: {}", e);
        }
    })
    .into_response())
}

/// Which side of the proxy terminated first
#[derive(Debug)]
enum ProxyCloseOrigin {
    ClientClosed,
    UpstreamClosed,
    ClientError,
    UpstreamError,
}

/// Bidirectional WebSocket proxy between client (axum) and upstream (tokio-tungstenite).
/// When one side closes or errors, a close frame is forwarded to the other side before teardown.
async fn proxy_ws_bidirectional(
    client_socket: axum::extract::ws::WebSocket,
    upstream_url: &str,
    api_key: &str,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    use axum::extract::ws::Message as AxumMsg;
    use futures::{SinkExt, StreamExt};
    use tokio_tungstenite::tungstenite::{
        client::IntoClientRequest, http::HeaderValue, Message as TungMsg,
    };

    // Connect to upstream Deepgram with auth header
    let mut request = upstream_url.into_client_request()?;
    request.headers_mut().insert(
        "Authorization",
        HeaderValue::from_str(&format!("Token {}", api_key))?,
    );

    let (upstream_ws, _) = tokio_tungstenite::connect_async(request).await?;
    let (mut upstream_sink, mut upstream_stream) = upstream_ws.split();
    let (mut client_sink, mut client_stream) = client_socket.split();

    // Client → Upstream
    let client_to_upstream = async {
        while let Some(result) = client_stream.next().await {
            match result {
                Ok(msg) => {
                    let tung_msg = match msg {
                        AxumMsg::Text(t) => TungMsg::Text(t),
                        AxumMsg::Binary(b) => TungMsg::Binary(b),
                        AxumMsg::Ping(p) => TungMsg::Ping(p),
                        AxumMsg::Pong(p) => TungMsg::Pong(p),
                        AxumMsg::Close(_) => {
                            let _ = upstream_sink.close().await;
                            return ProxyCloseOrigin::ClientClosed;
                        }
                    };
                    if upstream_sink.send(tung_msg).await.is_err() {
                        return ProxyCloseOrigin::UpstreamError;
                    }
                }
                Err(_) => return ProxyCloseOrigin::ClientError,
            }
        }
        ProxyCloseOrigin::ClientClosed
    };

    // Upstream → Client
    let upstream_to_client = async {
        while let Some(result) = upstream_stream.next().await {
            match result {
                Ok(msg) => {
                    let axum_msg = match msg {
                        TungMsg::Text(t) => AxumMsg::Text(t),
                        TungMsg::Binary(b) => AxumMsg::Binary(b),
                        TungMsg::Ping(p) => AxumMsg::Ping(p),
                        TungMsg::Pong(p) => AxumMsg::Pong(p),
                        TungMsg::Close(_) => {
                            let _ = client_sink.close().await;
                            return ProxyCloseOrigin::UpstreamClosed;
                        }
                        TungMsg::Frame(_) => continue,
                    };
                    if client_sink.send(axum_msg).await.is_err() {
                        return ProxyCloseOrigin::ClientError;
                    }
                }
                Err(_) => return ProxyCloseOrigin::UpstreamError,
            }
        }
        ProxyCloseOrigin::UpstreamClosed
    };

    // Run both directions concurrently; when either ends, gracefully close the other side
    let origin = tokio::select! {
        origin = client_to_upstream => origin,
        origin = upstream_to_client => origin,
    };

    // Forward close frame to the surviving side with a timeout to prevent hanging
    let close_timeout = std::time::Duration::from_secs(5);
    tracing::debug!("deepgram_ws_proxy: proxy ended ({:?})", origin);
    match origin {
        ProxyCloseOrigin::UpstreamClosed | ProxyCloseOrigin::UpstreamError => {
            let _ = tokio::time::timeout(close_timeout, client_sink.close()).await;
        }
        ProxyCloseOrigin::ClientClosed | ProxyCloseOrigin::ClientError => {
            let _ = tokio::time::timeout(close_timeout, upstream_sink.close()).await;
        }
    }

    Ok(())
}

/// Extract the action from a Gemini API path (e.g., "models/gemini-3-flash:generateContent" → "generateContent")
fn extract_gemini_action(path: &str) -> &str {
    path.rsplit(':').next().unwrap_or("")
}

/// Check if a Gemini action is in the allowlist
fn is_gemini_action_allowed(action: &str) -> bool {
    GEMINI_ALLOWED_ACTIONS.contains(&action)
}

/// Build upstream Gemini URL for non-streaming requests
fn build_gemini_url(path: &str, api_key: &str) -> String {
    format!(
        "https://generativelanguage.googleapis.com/v1beta/{}?key={}",
        path, api_key
    )
}

/// Build upstream Gemini URL for streaming requests with extra query params
fn build_gemini_stream_url(
    path: &str,
    api_key: &str,
    query: &std::collections::HashMap<String, String>,
) -> String {
    let mut url = format!(
        "https://generativelanguage.googleapis.com/v1beta/{}?key={}",
        path, api_key
    );
    for (k, v) in query {
        url.push('&');
        url.push_str(&urlencoding::encode(k));
        url.push('=');
        url.push_str(&urlencoding::encode(v));
    }
    url
}

/// Build upstream Deepgram REST URL preserving query params
fn build_deepgram_rest_url(query: &str) -> String {
    format!("https://api.deepgram.com/v1/listen?{}", query)
}

/// Build upstream Deepgram WS URL preserving query params
fn build_deepgram_ws_url(query: &str) -> String {
    format!("wss://api.deepgram.com/v1/listen?{}", query)
}

/// Build Deepgram auth header
fn build_deepgram_auth_header(api_key: &str) -> String {
    format!("Token {}", api_key)
}

pub fn proxy_routes() -> Router<AppState> {
    Router::new()
        // Gemini HTTP proxy (non-streaming)
        .route("/v1/proxy/gemini/*path", post(gemini_proxy))
        // Gemini streaming proxy (SSE)
        .route("/v1/proxy/gemini-stream/*path", post(gemini_stream_proxy))
        // Deepgram batch (pre-recorded) transcription proxy
        .route("/v1/proxy/deepgram/v1/listen", post(deepgram_listen_proxy))
        // Deepgram streaming WebSocket proxy
        .route(
            "/v1/proxy/deepgram/ws/v1/listen",
            any(deepgram_ws_proxy),
        )
}

#[cfg(test)]
mod tests {
    use super::*;

    // --- Gemini action extraction ---

    #[test]
    fn extract_action_generate_content() {
        assert_eq!(
            extract_gemini_action("models/gemini-3-flash:generateContent"),
            "generateContent"
        );
    }

    #[test]
    fn extract_action_stream() {
        assert_eq!(
            extract_gemini_action("models/gemini-3-flash:streamGenerateContent"),
            "streamGenerateContent"
        );
    }

    #[test]
    fn extract_action_embed() {
        assert_eq!(
            extract_gemini_action("models/gemini-embedding-001:embedContent"),
            "embedContent"
        );
    }

    #[test]
    fn extract_action_batch_embed() {
        assert_eq!(
            extract_gemini_action("models/gemini-embedding-001:batchEmbedContents"),
            "batchEmbedContents"
        );
    }

    #[test]
    fn extract_action_empty_path() {
        assert_eq!(extract_gemini_action(""), "");
    }

    #[test]
    fn extract_action_no_colon() {
        assert_eq!(extract_gemini_action("models/gemini"), "models/gemini");
    }

    // --- Gemini action allowlist ---

    #[test]
    fn allowlist_permits_valid_actions() {
        assert!(is_gemini_action_allowed("generateContent"));
        assert!(is_gemini_action_allowed("streamGenerateContent"));
        assert!(is_gemini_action_allowed("embedContent"));
        assert!(is_gemini_action_allowed("batchEmbedContents"));
    }

    #[test]
    fn allowlist_blocks_prefix_bypass() {
        assert!(!is_gemini_action_allowed("generateContentX"));
        assert!(!is_gemini_action_allowed("embedContentFoo"));
    }

    #[test]
    fn allowlist_blocks_unknown_actions() {
        assert!(!is_gemini_action_allowed("deleteModel"));
        assert!(!is_gemini_action_allowed("foo"));
        assert!(!is_gemini_action_allowed(""));
    }

    // --- Gemini URL construction ---

    #[test]
    fn gemini_url_construction() {
        let url = build_gemini_url("models/gemini-3-flash:generateContent", "test-key-123");
        assert_eq!(
            url,
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash:generateContent?key=test-key-123"
        );
    }

    #[test]
    fn gemini_stream_url_with_query_params() {
        let mut params = std::collections::HashMap::new();
        params.insert("alt".to_string(), "sse".to_string());
        let url = build_gemini_stream_url(
            "models/gemini-3-flash:streamGenerateContent",
            "key-456",
            &params,
        );
        assert!(url.starts_with("https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash:streamGenerateContent?key=key-456"));
        assert!(url.contains("&alt=sse"));
    }

    #[test]
    fn gemini_stream_url_empty_params() {
        let params = std::collections::HashMap::new();
        let url = build_gemini_stream_url(
            "models/gemini-3-flash:generateContent",
            "key-789",
            &params,
        );
        assert_eq!(
            url,
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash:generateContent?key=key-789"
        );
    }

    // --- Deepgram URL construction ---

    #[test]
    fn deepgram_rest_url_preserves_query() {
        let url = build_deepgram_rest_url("model=nova-3&language=en&encoding=linear16");
        assert_eq!(
            url,
            "https://api.deepgram.com/v1/listen?model=nova-3&language=en&encoding=linear16"
        );
    }

    #[test]
    fn deepgram_ws_url_preserves_query() {
        let url = build_deepgram_ws_url("model=nova-3&channels=2");
        assert_eq!(
            url,
            "wss://api.deepgram.com/v1/listen?model=nova-3&channels=2"
        );
    }

    // --- Deepgram auth header ---

    #[test]
    fn deepgram_auth_header_format() {
        assert_eq!(
            build_deepgram_auth_header("dg-test-key"),
            "Token dg-test-key"
        );
    }

    // --- ProxyError::RateLimited response ---

    #[tokio::test]
    async fn rate_limited_response_status_and_headers() {
        let response = ProxyError::RateLimited.into_response();
        assert_eq!(response.status(), StatusCode::TOO_MANY_REQUESTS);
        assert_eq!(
            response.headers().get("content-type").unwrap(),
            "application/json"
        );
        assert_eq!(response.headers().get("retry-after").unwrap(), "60");
    }

    #[tokio::test]
    async fn rate_limited_response_body() {
        let response = ProxyError::RateLimited.into_response();
        let body_bytes = axum::body::to_bytes(response.into_body(), 4096)
            .await
            .unwrap();
        let parsed: serde_json::Value = serde_json::from_slice(&body_bytes).unwrap();
        assert_eq!(parsed["error"]["code"], 429);
        assert_eq!(parsed["error"]["status"], "RESOURCE_EXHAUSTED");
        let msg = parsed["error"]["message"].as_str().unwrap().to_lowercase();
        assert!(msg.contains("resource exhausted"));
    }

    // --- ProxyCloseOrigin ---

    #[test]
    fn proxy_close_origin_debug_variants() {
        // Verify all variants exist and produce distinct debug output
        let variants = [
            ProxyCloseOrigin::ClientClosed,
            ProxyCloseOrigin::UpstreamClosed,
            ProxyCloseOrigin::ClientError,
            ProxyCloseOrigin::UpstreamError,
        ];
        let debug_strs: Vec<String> = variants.iter().map(|v| format!("{:?}", v)).collect();
        assert_eq!(debug_strs.len(), 4);
        // All distinct
        let unique: std::collections::HashSet<&String> = debug_strs.iter().collect();
        assert_eq!(unique.len(), 4, "All ProxyCloseOrigin variants should have distinct Debug output");
        // Verify expected names
        assert!(debug_strs.contains(&"ClientClosed".to_string()));
        assert!(debug_strs.contains(&"UpstreamClosed".to_string()));
        assert!(debug_strs.contains(&"ClientError".to_string()));
        assert!(debug_strs.contains(&"UpstreamError".to_string()));
    }
}
