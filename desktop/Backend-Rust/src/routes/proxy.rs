// API proxy routes — forward Gemini and Deepgram requests to upstream APIs.
// Keys stay server-side; desktop client authenticates via Firebase token only.
//
// Issue #5861: Remove client-side API key exposure risk.

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

// Allowed Gemini API actions (suffix after model name)
const GEMINI_ALLOWED_ACTIONS: &[&str] = &[
    "generateContent",
    "streamGenerateContent",
    "embedContent",
    "batchEmbedContents",
];

/// POST /v1/proxy/gemini/*path
/// Proxies requests to https://generativelanguage.googleapis.com/v1beta/...
/// Appends the server-side Gemini API key. Client sends Bearer Firebase token.
async fn gemini_proxy(
    State(state): State<AppState>,
    _user: AuthUser,
    Path(path): Path<String>,
    body: Bytes,
) -> Result<Response, StatusCode> {
    let gemini_key = state
        .config
        .gemini_api_key
        .as_ref()
        .ok_or(StatusCode::SERVICE_UNAVAILABLE)?;

    // Validate the action is in our allowlist
    let action = extract_gemini_action(&path);
    if !is_gemini_action_allowed(action) {
        tracing::warn!("gemini_proxy: blocked action '{}' in path '{}'", action, path);
        return Err(StatusCode::FORBIDDEN);
    }

    let url = build_gemini_url(&path, gemini_key);

    let upstream = reqwest::Client::new()
        .post(&url)
        .header("content-type", "application/json")
        .body(body)
        .send()
        .await
        .map_err(|e| {
            tracing::error!("gemini_proxy: upstream request failed: {}", e);
            StatusCode::BAD_GATEWAY
        })?;

    let status =
        StatusCode::from_u16(upstream.status().as_u16()).unwrap_or(StatusCode::BAD_GATEWAY);
    let bytes = upstream.bytes().await.map_err(|e| {
        tracing::error!("gemini_proxy: failed to read upstream body: {}", e);
        StatusCode::BAD_GATEWAY
    })?;

    Ok((status, bytes).into_response())
}

/// POST /v1/proxy/gemini-stream/*path
/// Same as gemini_proxy but streams the response using SSE (for streamGenerateContent).
async fn gemini_stream_proxy(
    State(state): State<AppState>,
    _user: AuthUser,
    Path(path): Path<String>,
    axum::extract::Query(query): axum::extract::Query<std::collections::HashMap<String, String>>,
    body: Bytes,
) -> Result<Response, StatusCode> {
    let gemini_key = state
        .config
        .gemini_api_key
        .as_ref()
        .ok_or(StatusCode::SERVICE_UNAVAILABLE)?;

    // Validate the action
    let action = extract_gemini_action(&path);
    if !is_gemini_action_allowed(action) {
        tracing::warn!("gemini_stream_proxy: blocked action '{}'", action);
        return Err(StatusCode::FORBIDDEN);
    }

    // Build upstream URL with query params (e.g., alt=sse)
    let upstream_url = build_gemini_stream_url(&path, gemini_key, &query);

    let upstream = reqwest::Client::new()
        .post(&upstream_url)
        .header("content-type", "application/json")
        .body(body)
        .send()
        .await
        .map_err(|e| {
            tracing::error!("gemini_stream_proxy: upstream request failed: {}", e);
            StatusCode::BAD_GATEWAY
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

/// POST /v1/proxy/deepgram/v1/listen?<query_params>
/// Proxies pre-recorded (batch) transcription to Deepgram REST API.
/// Client sends audio body; server adds Deepgram auth.
async fn deepgram_listen_proxy(
    State(state): State<AppState>,
    _user: AuthUser,
    axum::extract::OriginalUri(original_uri): axum::extract::OriginalUri,
    body: Bytes,
) -> Result<Response, StatusCode> {
    let dg_key = state
        .config
        .deepgram_api_key
        .as_ref()
        .ok_or(StatusCode::SERVICE_UNAVAILABLE)?;

    // Forward query params from the original request
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

/// WebSocket proxy for Deepgram streaming transcription.
/// GET /v1/proxy/deepgram/ws/v1/listen?<query_params> — upgrades to WS,
/// then pipes bidirectionally to wss://api.deepgram.com/v1/listen.
async fn deepgram_ws_proxy(
    ws: axum::extract::WebSocketUpgrade,
    State(state): State<AppState>,
    _user: AuthUser,
    axum::extract::OriginalUri(original_uri): axum::extract::OriginalUri,
) -> Result<impl IntoResponse, StatusCode> {
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
    }))
}

/// Bidirectional WebSocket proxy between client (axum) and upstream (tokio-tungstenite).
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
        while let Some(Ok(msg)) = client_stream.next().await {
            let tung_msg = match msg {
                AxumMsg::Text(t) => TungMsg::Text(t),
                AxumMsg::Binary(b) => TungMsg::Binary(b),
                AxumMsg::Ping(p) => TungMsg::Ping(p),
                AxumMsg::Pong(p) => TungMsg::Pong(p),
                AxumMsg::Close(_) => {
                    let _ = upstream_sink.close().await;
                    return;
                }
            };
            if upstream_sink.send(tung_msg).await.is_err() {
                return;
            }
        }
    };

    // Upstream → Client
    let upstream_to_client = async {
        while let Some(Ok(msg)) = upstream_stream.next().await {
            let axum_msg = match msg {
                TungMsg::Text(t) => AxumMsg::Text(t),
                TungMsg::Binary(b) => AxumMsg::Binary(b),
                TungMsg::Ping(p) => AxumMsg::Ping(p),
                TungMsg::Pong(p) => AxumMsg::Pong(p),
                TungMsg::Close(_) => {
                    let _ = client_sink.close().await;
                    return;
                }
                TungMsg::Frame(_) => continue,
            };
            if client_sink.send(axum_msg).await.is_err() {
                return;
            }
        }
    };

    // Run both directions concurrently; when either ends, drop both
    tokio::select! {
        _ = client_to_upstream => {},
        _ = upstream_to_client => {},
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
}
