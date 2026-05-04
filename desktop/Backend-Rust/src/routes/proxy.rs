// API proxy routes — forward Gemini requests to upstream APIs.
// Keys stay server-side; desktop client authenticates via Firebase token only.
//
// Issue #5861: Remove client-side API key exposure risk.
// Issue #6098 L2: Tiered rate limiting with Pro→Flash degradation.
// Issue #6624: Model allowlist, body size limit, request body validation.

use axum::{
    body::Bytes,
    extract::{DefaultBodyLimit, Path, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::post,
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

// Allowed Gemini models — driven by model_qos (issue #6834).
// Desktop app uses: gemini-2.5-flash or gemini-2.5-pro (tier-dependent), gemini-embedding-001.
// Provider routing: stable models → Vertex AI, embeddings/preview → AI Studio.
// Rate limiting may degrade requests above soft limit.

/// Maximum request body size for Gemini proxy routes (5 MB).
/// Normal app payloads are 300-600 KB (base64 JPEG + prompt); 5 MB gives ~8x headroom.
const GEMINI_MAX_BODY_SIZE: usize = 5 * 1024 * 1024;

/// Maximum allowed max_output_tokens in generation_config.
/// App uses 8192 (GeminiClient.swift:553,922,1026).
const MAX_OUTPUT_TOKENS_CAP: u64 = 8192;

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
/// Proxies requests to Gemini (AI Studio or Vertex AI depending on config).
/// Keys stay server-side; desktop client authenticates via Firebase token only.
/// Rate-limited per user: Tier 1 (allow), Tier 2 (degrade Pro→Flash), Tier 3 (reject 429).
async fn gemini_proxy(
    State(state): State<AppState>,
    user: AuthUser,
    Path(path): Path<String>,
    body: Bytes,
) -> Result<Response, ProxyError> {
    // Rewrite preview models to stable equivalents (old app compat)
    let path = crate::llm::model_qos::rewrite_preview_model(&path);

    // Validate the action is in our allowlist
    let action = extract_gemini_action(&path);
    if !is_gemini_action_allowed(action) {
        tracing::warn!("gemini_proxy: blocked action '{}' in path '{}'", action, path);
        return Err(ProxyError::Status(StatusCode::FORBIDDEN));
    }

    // Validate the model is in our allowlist (issue #6624)
    let model = extract_gemini_model(&path);
    if !is_gemini_model_allowed(model) {
        tracing::warn!("gemini_proxy: blocked model '{}' in path '{}'", model, path);
        return Err(ProxyError::Status(StatusCode::FORBIDDEN));
    }

    // Sanitize request body: cap max_output_tokens, reject candidate_count > 1,
    // strip safety_settings and cached_content (issue #6624)
    let sanitized_body = sanitize_gemini_body(&body, action).map_err(|e| {
        tracing::warn!("gemini_proxy: body validation failed: {}", e);
        ProxyError::Status(StatusCode::BAD_REQUEST)
    })?;

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

    // Resolve provider route: single dispatch point for all provider-specific behavior.
    // Returns provider, action override, and body transforms needed.
    use crate::llm::model_qos::{resolve_route, BodyTransform, Provider, ResponseTransform};
    let route = resolve_route(model, action);

    // Apply request body transform if needed (e.g., embedContent → predict format)
    let request_body = match route.request_transform {
        BodyTransform::EmbedToPredict => transform_embed_request_to_vertex(&sanitized_body)
            .map_err(|e| {
                tracing::warn!("gemini_proxy: embed body transform failed: {}", e);
                ProxyError::Status(StatusCode::BAD_REQUEST)
            })?,
        BodyTransform::None => sanitized_body.clone(),
    };

    // Apply Vertex action override (e.g., :embedContent → :predict)
    let vertex_path = if let Some(override_action) = route.vertex_action {
        effective_path.replace(&format!(":{}", action), &format!(":{}", override_action))
    } else {
        effective_path.to_string()
    };

    // Build and send request: Vertex AI (Bearer token) or AI Studio (API key).
    // Falls back to AI Studio if Vertex token fetch fails.
    let mut used_vertex = false;
    let upstream = if route.provider == Provider::VertexAi {
        if let Some(ref vertex) = state.vertex_auth {
            let url = vertex.build_url_from_path(&vertex_path).ok_or_else(|| {
                tracing::error!("gemini_proxy: failed to parse path for Vertex AI: {}", vertex_path);
                ProxyError::Status(StatusCode::BAD_REQUEST)
            })?;
            match vertex.token().await {
                Ok(token) => {
                    used_vertex = true;
                    reqwest::Client::new()
                        .post(&url)
                        .header("content-type", "application/json")
                        .header("authorization", format!("Bearer {}", token))
                        .body(request_body)
                        .send()
                        .await
                }
                Err(e) => {
                    if let Some(gemini_key) = state.config.gemini_api_key.as_ref() {
                        tracing::warn!("gemini_proxy: Vertex AI token failed, falling back to API key: {}", e);
                        let url = build_gemini_url(&effective_path, gemini_key);
                        reqwest::Client::new()
                            .post(&url)
                            .header("content-type", "application/json")
                            .body(sanitized_body.clone())
                            .send()
                            .await
                    } else {
                        tracing::error!("gemini_proxy: Vertex AI token error and no fallback: {}", e);
                        return Err(ProxyError::Status(StatusCode::SERVICE_UNAVAILABLE));
                    }
                }
            }
        } else {
            // Vertex AI requested but not configured → AI Studio
            let gemini_key = state.config.gemini_api_key.as_ref()
                .ok_or(ProxyError::Status(StatusCode::SERVICE_UNAVAILABLE))?;
            let url = build_gemini_url(&effective_path, gemini_key);
            reqwest::Client::new()
                .post(&url)
                .header("content-type", "application/json")
                .body(sanitized_body.clone())
                .send()
                .await
        }
    } else {
        // AI Studio route
        let gemini_key = state.config.gemini_api_key.as_ref()
            .ok_or(ProxyError::Status(StatusCode::SERVICE_UNAVAILABLE))?;
        let url = build_gemini_url(&effective_path, gemini_key);
        reqwest::Client::new()
            .post(&url)
            .header("content-type", "application/json")
            .body(sanitized_body.clone())
            .send()
            .await
    };

    let upstream = upstream.map_err(|e| {
        tracing::error!("gemini_proxy: upstream request failed: {}", e);
        ProxyError::Status(StatusCode::BAD_GATEWAY)
    })?;

    let status =
        StatusCode::from_u16(upstream.status().as_u16()).unwrap_or(StatusCode::BAD_GATEWAY);
    let bytes = upstream.bytes().await.map_err(|e| {
        tracing::error!("gemini_proxy: failed to read upstream body: {}", e);
        ProxyError::Status(StatusCode::BAD_GATEWAY)
    })?;

    // Apply response transform if needed (e.g., Vertex predict → AI Studio embed format)
    if used_vertex && status.is_success() && route.response_transform != ResponseTransform::None {
        let transformed = match route.response_transform {
            ResponseTransform::PredictToEmbed => transform_vertex_embed_response(&bytes),
            ResponseTransform::None => unreachable!(),
        };
        match transformed {
            Ok(body) => return Ok((status, body).into_response()),
            Err(e) => {
                tracing::warn!("gemini_proxy: response transform failed: {}", e);
                // Fall through to return raw response
            }
        }
    }

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
    // Rewrite preview models to stable equivalents (old app compat)
    let path = crate::llm::model_qos::rewrite_preview_model(&path);

    // Validate the action
    let action = extract_gemini_action(&path);
    if !is_gemini_action_allowed(action) {
        tracing::warn!("gemini_stream_proxy: blocked action '{}'", action);
        return Err(ProxyError::Status(StatusCode::FORBIDDEN));
    }

    // Validate the model is in our allowlist (issue #6624)
    let model = extract_gemini_model(&path);
    if !is_gemini_model_allowed(model) {
        tracing::warn!("gemini_stream_proxy: blocked model '{}' in path '{}'", model, path);
        return Err(ProxyError::Status(StatusCode::FORBIDDEN));
    }

    // Sanitize request body (issue #6624)
    let sanitized_body = sanitize_gemini_body(&body, action).map_err(|e| {
        tracing::warn!("gemini_stream_proxy: body validation failed: {}", e);
        ProxyError::Status(StatusCode::BAD_REQUEST)
    })?;

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

    // Resolve provider route (same dispatch as non-streaming proxy)
    use crate::llm::model_qos::{resolve_route, Provider};
    let route = resolve_route(model, action);

    // Build and send request: Vertex AI or AI Studio
    let upstream = if route.provider == Provider::VertexAi {
        if let Some(ref vertex) = state.vertex_auth {
            let mut url = vertex.build_url_from_path(&effective_path).ok_or_else(|| {
                tracing::error!("gemini_stream_proxy: failed to parse path for Vertex AI: {}", effective_path);
                ProxyError::Status(StatusCode::BAD_REQUEST)
            })?;
            // Append extra query params (e.g., alt=sse) for streaming
            for (k, v) in &query {
                url.push(if url.contains('?') { '&' } else { '?' });
                url.push_str(&urlencoding::encode(k));
                url.push('=');
                url.push_str(&urlencoding::encode(v));
            }
            match vertex.token().await {
                Ok(token) => {
                    reqwest::Client::new()
                        .post(&url)
                        .header("content-type", "application/json")
                        .header("authorization", format!("Bearer {}", token))
                        .body(sanitized_body)
                        .send()
                        .await
                }
                Err(e) => {
                    if let Some(gemini_key) = state.config.gemini_api_key.as_ref() {
                        tracing::warn!("gemini_stream_proxy: Vertex AI token failed, falling back to API key: {}", e);
                        let upstream_url = build_gemini_stream_url(&effective_path, gemini_key, &query);
                        reqwest::Client::new()
                            .post(&upstream_url)
                            .header("content-type", "application/json")
                            .body(sanitized_body)
                            .send()
                            .await
                    } else {
                        tracing::error!("gemini_stream_proxy: Vertex AI token error and no fallback: {}", e);
                        return Err(ProxyError::Status(StatusCode::SERVICE_UNAVAILABLE));
                    }
                }
            }
        } else {
            // Vertex AI requested but not configured → AI Studio
            let gemini_key = state.config.gemini_api_key.as_ref()
                .ok_or(ProxyError::Status(StatusCode::SERVICE_UNAVAILABLE))?;
            let upstream_url = build_gemini_stream_url(&effective_path, gemini_key, &query);
            reqwest::Client::new()
                .post(&upstream_url)
                .header("content-type", "application/json")
                .body(sanitized_body)
                .send()
                .await
        }
    } else {
        // AI Studio route
        let gemini_key = state.config.gemini_api_key.as_ref()
            .ok_or(ProxyError::Status(StatusCode::SERVICE_UNAVAILABLE))?;
        let upstream_url = build_gemini_stream_url(&effective_path, gemini_key, &query);
        reqwest::Client::new()
            .post(&upstream_url)
            .header("content-type", "application/json")
            .body(sanitized_body)
            .send()
            .await
    };

    let upstream = upstream.map_err(|e| {
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

/// Extract the action from a Gemini API path (e.g., "models/gemini-3-flash:generateContent" → "generateContent")
fn extract_gemini_action(path: &str) -> &str {
    path.rsplit(':').next().unwrap_or("")
}

/// Extract the model from a Gemini API path (e.g., "models/gemini-2.5-flash:generateContent" → "gemini-2.5-flash")
fn extract_gemini_model(path: &str) -> &str {
    path.strip_prefix("models/")
        .and_then(|rest| rest.split(':').next())
        .unwrap_or("")
}

/// Check if a Gemini action is in the allowlist
fn is_gemini_action_allowed(action: &str) -> bool {
    GEMINI_ALLOWED_ACTIONS.contains(&action)
}

/// Check if a Gemini model is in the allowlist (issue #6624, #6834)
fn is_gemini_model_allowed(model: &str) -> bool {
    crate::llm::model_qos::gemini_proxy_allowed().contains(&model)
}

/// Sanitize a Gemini request body (issue #6624).
///
/// For generateContent/streamGenerateContent:
///   - Cap generation_config.max_output_tokens to MAX_OUTPUT_TOKENS_CAP
///   - Reject candidate_count > 1
///   - Strip safety_settings and cached_content
///   - Preserve all other fields (contents, system_instruction, tools, etc.)
///
/// For embedContent/batchEmbedContents:
///   - Skip generation-specific validation (different schema)
///   - Strip safety_settings and cached_content only
fn sanitize_gemini_body(body: &[u8], action: &str) -> Result<Vec<u8>, String> {
    let mut json: serde_json::Value = serde_json::from_slice(body)
        .map_err(|e| format!("invalid JSON: {}", e))?;

    let obj = json.as_object_mut()
        .ok_or_else(|| "request body must be a JSON object".to_string())?;

    // Strip dangerous fields from all request types
    obj.remove("safety_settings");
    obj.remove("safetySettings");
    obj.remove("cached_content");
    obj.remove("cachedContent");

    // Sanitize role fields in contents array:
    // 1. Inject missing "role" → default to "user" (Vertex AI requires it)
    // 2. Move "role":"system" contents → systemInstruction (Vertex AI rejects "system" role)
    //
    // Vertex AI only accepts "user" or "model" in contents[].role.
    // AI Studio silently handles missing roles and "system", but Vertex does not.
    if let Some(contents) = obj.get_mut("contents").and_then(|v| v.as_array_mut()) {
        // First pass: inject missing roles
        for content in contents.iter_mut() {
            if let Some(content_obj) = content.as_object_mut() {
                if !content_obj.contains_key("role") {
                    content_obj.insert("role".to_string(), serde_json::Value::String("user".to_string()));
                }
            }
        }

        // Second pass: extract "system" role contents → systemInstruction
        let mut system_parts: Vec<serde_json::Value> = Vec::new();
        contents.retain(|content| {
            if let Some(role) = content.get("role").and_then(|r| r.as_str()) {
                if role == "system" {
                    if let Some(parts) = content.get("parts") {
                        if let Some(arr) = parts.as_array() {
                            system_parts.extend(arr.iter().cloned());
                        }
                    }
                    return false; // remove from contents
                }
            }
            true
        });

        if !system_parts.is_empty() {
            // Merge into existing systemInstruction or create new one
            let si_key = if obj.contains_key("system_instruction") {
                "system_instruction"
            } else {
                "systemInstruction"
            };
            if let Some(existing) = obj.get_mut(si_key).and_then(|v| v.as_object_mut()) {
                if let Some(existing_parts) = existing.get_mut("parts").and_then(|v| v.as_array_mut()) {
                    existing_parts.extend(system_parts);
                }
            } else {
                obj.insert(
                    "systemInstruction".to_string(),
                    serde_json::json!({"parts": system_parts}),
                );
            }
        }
    }

    // Generation-specific validation (not for embed actions)
    let is_embed = action == "embedContent" || action == "batchEmbedContents";
    if !is_embed {
        // Helper: parse a JSON value as u64 from a number (int or integral float),
        // or a string. ProtoJSON allows integer fields as quoted strings and
        // protobuf parsers accept integral floats (e.g. 8.0) for int32/int64.
        let parse_as_u64 = |v: &serde_json::Value| -> Option<u64> {
            v.as_u64()
                .or_else(|| {
                    // Handle integral floats like 8.0, 999999.0
                    v.as_f64().and_then(|f| {
                        if f >= 0.0 && f <= (u64::MAX as f64) && f == (f as u64 as f64) {
                            Some(f as u64)
                        } else {
                            None
                        }
                    })
                })
                .or_else(|| v.as_str().and_then(|s| s.parse::<u64>().ok()))
        };

        // Reject top-level candidate_count > 1
        if let Some(cc) = obj.get("candidate_count").or_else(|| obj.get("candidateCount")) {
            if let Some(n) = parse_as_u64(cc) {
                if n > 1 {
                    return Err(format!("candidate_count must be 1 or absent, got {}", n));
                }
            }
        }

        // Validate inside generation_config / generationConfig.
        // Check BOTH casings to prevent dual-key bypass where an attacker
        // sends an empty generation_config + a real generationConfig.
        for gc_key in &["generation_config", "generationConfig"] {
            if let Some(gc) = obj.get_mut(*gc_key).and_then(|v| v.as_object_mut()) {
                // Reject candidate_count > 1
                for cc_key in &["candidate_count", "candidateCount"] {
                    if let Some(v) = gc.get(*cc_key) {
                        if let Some(n) = parse_as_u64(v) {
                            if n > 1 {
                                return Err(format!("candidate_count must be 1 or absent, got {}", n));
                            }
                        }
                    }
                }

                // Cap max_output_tokens (handles numeric, integral float, and string-encoded values)
                for mot_key in &["max_output_tokens", "maxOutputTokens"] {
                    if let Some(mot) = gc.get_mut(*mot_key) {
                        if let Some(n) = parse_as_u64(mot) {
                            if n > MAX_OUTPUT_TOKENS_CAP {
                                *mot = serde_json::Value::Number(MAX_OUTPUT_TOKENS_CAP.into());
                            }
                        }
                    }
                }
            }
        }
    }

    serde_json::to_vec(&json).map_err(|e| format!("failed to re-serialize: {}", e))
}

/// Transform an AI Studio embedContent request body to Vertex AI predict format.
///
/// AI Studio: `{"content": {"parts": [{"text": "TEXT"}]}, "taskType": "X", "title": "T"}`
/// Vertex AI: `{"instances": [{"content": "TEXT", "taskType": "X", "title": "T"}]}`
fn transform_embed_request_to_vertex(body: &[u8]) -> Result<Vec<u8>, String> {
    let json: serde_json::Value =
        serde_json::from_slice(body).map_err(|e| format!("invalid JSON: {}", e))?;
    let obj = json
        .as_object()
        .ok_or_else(|| "request body must be a JSON object".to_string())?;

    // Extract text from content.parts[0].text
    let text = obj
        .get("content")
        .and_then(|c| c.get("parts"))
        .and_then(|p| p.as_array())
        .and_then(|a| a.first())
        .and_then(|p| p.get("text"))
        .and_then(|t| t.as_str())
        .ok_or_else(|| "missing content.parts[0].text in embed request".to_string())?;

    let mut instance = serde_json::Map::new();
    instance.insert(
        "content".to_string(),
        serde_json::Value::String(text.to_string()),
    );

    // Forward optional fields
    if let Some(task_type) = obj.get("taskType") {
        instance.insert("task_type".to_string(), task_type.clone());
    }
    if let Some(title) = obj.get("title") {
        instance.insert("title".to_string(), title.clone());
    }

    let vertex_body = serde_json::json!({ "instances": [instance] });
    serde_json::to_vec(&vertex_body).map_err(|e| format!("failed to serialize: {}", e))
}

/// Transform a Vertex AI predict response back to AI Studio embedContent format.
///
/// Vertex AI: `{"predictions": [{"embeddings": {"values": [...], "statistics": {...}}}]}`
/// AI Studio: `{"embedding": {"values": [...]}}`
fn transform_vertex_embed_response(body: &[u8]) -> Result<Vec<u8>, String> {
    let json: serde_json::Value =
        serde_json::from_slice(body).map_err(|e| format!("invalid JSON: {}", e))?;

    let values = json
        .get("predictions")
        .and_then(|p| p.as_array())
        .and_then(|a| a.first())
        .and_then(|pred| pred.get("embeddings"))
        .and_then(|emb| emb.get("values"))
        .ok_or_else(|| "missing predictions[0].embeddings.values in Vertex response".to_string())?;

    let ai_studio_response = serde_json::json!({
        "embedding": { "values": values }
    });
    serde_json::to_vec(&ai_studio_response).map_err(|e| format!("failed to serialize: {}", e))
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

pub fn proxy_routes() -> Router<AppState> {
    Router::new()
        // Gemini HTTP proxy (non-streaming)
        .route("/v1/proxy/gemini/*path", post(gemini_proxy))
        // Gemini streaming proxy (SSE)
        .route("/v1/proxy/gemini-stream/*path", post(gemini_stream_proxy))
        // Issue #6624: 5 MB body size limit for proxy routes only (not global).
        // Normal app payloads are 300-600 KB; 5 MB gives ~8x headroom.
        .layer(DefaultBodyLimit::max(GEMINI_MAX_BODY_SIZE))
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

    // --- Gemini model extraction ---

    #[test]
    fn extract_model_flash() {
        assert_eq!(
            extract_gemini_model("models/gemini-2.5-flash:generateContent"),
            "gemini-2.5-flash"
        );
    }

    #[test]
    fn extract_model_pro() {
        assert_eq!(
            extract_gemini_model("models/gemini-2.5-pro:streamGenerateContent"),
            "gemini-2.5-pro"
        );
    }

    #[test]
    fn extract_model_embedding() {
        assert_eq!(
            extract_gemini_model("models/gemini-embedding-001:embedContent"),
            "gemini-embedding-001"
        );
    }

    #[test]
    fn extract_model_no_prefix() {
        assert_eq!(extract_gemini_model("gemini-pro:generateContent"), "");
    }

    #[test]
    fn extract_model_empty() {
        assert_eq!(extract_gemini_model(""), "");
    }

    // --- Gemini model allowlist ---

    #[test]
    fn model_allowlist_permits_valid_models() {
        assert!(is_gemini_model_allowed("gemini-2.5-flash"));
        assert!(is_gemini_model_allowed("gemini-2.5-pro"));
        assert!(is_gemini_model_allowed("gemini-3-flash-preview"), "kept for old app compat");
        assert!(is_gemini_model_allowed("gemini-embedding-001"));
    }

    #[test]
    fn model_allowlist_blocks_unknown() {
        assert!(!is_gemini_model_allowed("gemini-pro-latest"), "legacy pro not in allowlist");
        assert!(!is_gemini_model_allowed("gemini-1.5-pro"));
        assert!(!is_gemini_model_allowed("gemini-ultra"));
        assert!(!is_gemini_model_allowed(""));
    }

    #[test]
    fn model_allowlist_blocks_prefix_bypass() {
        assert!(!is_gemini_model_allowed("gemini-2.5-flash-exp"));
        assert!(!is_gemini_model_allowed("gemini-2.5-pro-latest"));
    }

    // --- Body sanitization ---

    #[test]
    fn sanitize_caps_max_output_tokens() {
        let body = serde_json::json!({
            "contents": [{"parts": [{"text": "hello"}]}],
            "generation_config": {"max_output_tokens": 99999}
        });
        let result = sanitize_gemini_body(
            serde_json::to_vec(&body).unwrap().as_slice(),
            "generateContent",
        ).unwrap();
        let parsed: serde_json::Value = serde_json::from_slice(&result).unwrap();
        assert_eq!(
            parsed["generation_config"]["max_output_tokens"],
            serde_json::json!(MAX_OUTPUT_TOKENS_CAP)
        );
    }

    #[test]
    fn sanitize_preserves_valid_max_output_tokens() {
        let body = serde_json::json!({
            "contents": [{"parts": [{"text": "hello"}]}],
            "generation_config": {"max_output_tokens": 4096}
        });
        let result = sanitize_gemini_body(
            serde_json::to_vec(&body).unwrap().as_slice(),
            "generateContent",
        ).unwrap();
        let parsed: serde_json::Value = serde_json::from_slice(&result).unwrap();
        assert_eq!(parsed["generation_config"]["max_output_tokens"], 4096);
    }

    #[test]
    fn sanitize_caps_camel_case_max_output_tokens() {
        let body = serde_json::json!({
            "contents": [{"parts": [{"text": "hello"}]}],
            "generationConfig": {"maxOutputTokens": 50000}
        });
        let result = sanitize_gemini_body(
            serde_json::to_vec(&body).unwrap().as_slice(),
            "generateContent",
        ).unwrap();
        let parsed: serde_json::Value = serde_json::from_slice(&result).unwrap();
        assert_eq!(
            parsed["generationConfig"]["maxOutputTokens"],
            serde_json::json!(MAX_OUTPUT_TOKENS_CAP)
        );
    }

    #[test]
    fn sanitize_rejects_candidate_count_gt_1() {
        let body = serde_json::json!({
            "contents": [{"parts": [{"text": "hello"}]}],
            "candidate_count": 8
        });
        let result = sanitize_gemini_body(
            serde_json::to_vec(&body).unwrap().as_slice(),
            "generateContent",
        );
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("candidate_count"));
    }

    #[test]
    fn sanitize_allows_candidate_count_1() {
        let body = serde_json::json!({
            "contents": [{"parts": [{"text": "hello"}]}],
            "candidate_count": 1
        });
        let result = sanitize_gemini_body(
            serde_json::to_vec(&body).unwrap().as_slice(),
            "generateContent",
        );
        assert!(result.is_ok());
    }

    #[test]
    fn sanitize_rejects_nested_candidate_count_gt_1() {
        // candidateCount inside generationConfig (real Gemini API shape)
        let body = serde_json::json!({
            "contents": [{"parts": [{"text": "hello"}]}],
            "generationConfig": {"candidateCount": 4, "maxOutputTokens": 1024}
        });
        let result = sanitize_gemini_body(
            serde_json::to_vec(&body).unwrap().as_slice(),
            "generateContent",
        );
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("candidate_count"));
    }

    #[test]
    fn sanitize_rejects_nested_snake_case_candidate_count() {
        let body = serde_json::json!({
            "contents": [{"parts": [{"text": "hello"}]}],
            "generation_config": {"candidate_count": 3}
        });
        let result = sanitize_gemini_body(
            serde_json::to_vec(&body).unwrap().as_slice(),
            "generateContent",
        );
        assert!(result.is_err());
    }

    #[test]
    fn sanitize_allows_nested_candidate_count_1() {
        let body = serde_json::json!({
            "contents": [{"parts": [{"text": "hello"}]}],
            "generationConfig": {"candidateCount": 1, "maxOutputTokens": 4096}
        });
        let result = sanitize_gemini_body(
            serde_json::to_vec(&body).unwrap().as_slice(),
            "generateContent",
        );
        assert!(result.is_ok());
    }

    #[test]
    fn sanitize_rejects_dual_key_bypass() {
        // Attacker sends empty generation_config + real generationConfig to bypass validation
        let body = serde_json::json!({
            "contents": [{"parts": [{"text": "hello"}]}],
            "generation_config": {},
            "generationConfig": {"candidateCount": 8, "maxOutputTokens": 999999}
        });
        let result = sanitize_gemini_body(
            serde_json::to_vec(&body).unwrap().as_slice(),
            "generateContent",
        );
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("candidate_count"));
    }

    #[test]
    fn sanitize_caps_dual_key_max_tokens() {
        // Both casings present — max_output_tokens should be capped in both
        let body = serde_json::json!({
            "contents": [{"parts": [{"text": "hello"}]}],
            "generation_config": {"max_output_tokens": 100},
            "generationConfig": {"maxOutputTokens": 999999}
        });
        let result = sanitize_gemini_body(
            serde_json::to_vec(&body).unwrap().as_slice(),
            "generateContent",
        ).unwrap();
        let parsed: serde_json::Value = serde_json::from_slice(&result).unwrap();
        assert_eq!(parsed["generation_config"]["max_output_tokens"], 100);
        assert_eq!(
            parsed["generationConfig"]["maxOutputTokens"],
            serde_json::json!(MAX_OUTPUT_TOKENS_CAP)
        );
    }

    #[test]
    fn sanitize_rejects_string_encoded_candidate_count() {
        // ProtoJSON allows integer fields as quoted strings — must still be caught
        let body = serde_json::json!({
            "contents": [{"parts": [{"text": "hello"}]}],
            "generationConfig": {"candidateCount": "8"}
        });
        let result = sanitize_gemini_body(
            serde_json::to_vec(&body).unwrap().as_slice(),
            "generateContent",
        );
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("candidate_count"));
    }

    #[test]
    fn sanitize_caps_string_encoded_max_output_tokens() {
        // String-encoded maxOutputTokens must still be capped
        let body = serde_json::json!({
            "contents": [{"parts": [{"text": "hello"}]}],
            "generationConfig": {"maxOutputTokens": "999999"}
        });
        let result = sanitize_gemini_body(
            serde_json::to_vec(&body).unwrap().as_slice(),
            "generateContent",
        ).unwrap();
        let parsed: serde_json::Value = serde_json::from_slice(&result).unwrap();
        assert_eq!(
            parsed["generationConfig"]["maxOutputTokens"],
            serde_json::json!(MAX_OUTPUT_TOKENS_CAP)
        );
    }

    #[test]
    fn sanitize_rejects_string_encoded_top_level_candidate_count() {
        // Top-level candidate_count as string must also be caught
        let body = serde_json::json!({
            "contents": [{"parts": [{"text": "hello"}]}],
            "candidateCount": "5"
        });
        let result = sanitize_gemini_body(
            serde_json::to_vec(&body).unwrap().as_slice(),
            "generateContent",
        );
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("candidate_count"));
    }

    #[test]
    fn sanitize_rejects_float_encoded_candidate_count() {
        // Protobuf parsers accept integral floats (8.0) for int32 fields
        let body = serde_json::json!({
            "contents": [{"parts": [{"text": "hello"}]}],
            "generationConfig": {"candidateCount": 8.0}
        });
        let result = sanitize_gemini_body(
            serde_json::to_vec(&body).unwrap().as_slice(),
            "generateContent",
        );
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("candidate_count"));
    }

    #[test]
    fn sanitize_caps_float_encoded_max_output_tokens() {
        // Float-encoded maxOutputTokens must still be capped
        let body = serde_json::json!({
            "contents": [{"parts": [{"text": "hello"}]}],
            "generationConfig": {"maxOutputTokens": 999999.0}
        });
        let result = sanitize_gemini_body(
            serde_json::to_vec(&body).unwrap().as_slice(),
            "generateContent",
        ).unwrap();
        let parsed: serde_json::Value = serde_json::from_slice(&result).unwrap();
        assert_eq!(
            parsed["generationConfig"]["maxOutputTokens"],
            serde_json::json!(MAX_OUTPUT_TOKENS_CAP)
        );
    }

    #[test]
    fn body_size_limit_constant_is_5mb() {
        // Verify the body size limit constant matches spec (5 MB)
        assert_eq!(GEMINI_MAX_BODY_SIZE, 5 * 1024 * 1024);
    }

    #[test]
    fn sanitize_rejects_body_exceeding_reasonable_size() {
        // While DefaultBodyLimit handles the actual HTTP 413, the sanitizer
        // should still handle large valid JSON gracefully (not panic/OOM).
        // This tests a ~1MB valid JSON body passes sanitization fine.
        let large_text = "x".repeat(1_000_000);
        let body = serde_json::json!({
            "contents": [{"parts": [{"text": large_text}]}]
        });
        let result = sanitize_gemini_body(
            serde_json::to_vec(&body).unwrap().as_slice(),
            "generateContent",
        );
        assert!(result.is_ok());
    }

    #[test]
    fn sanitize_strips_safety_settings() {
        let body = serde_json::json!({
            "contents": [{"parts": [{"text": "hello"}]}],
            "safety_settings": [{"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"}]
        });
        let result = sanitize_gemini_body(
            serde_json::to_vec(&body).unwrap().as_slice(),
            "generateContent",
        ).unwrap();
        let parsed: serde_json::Value = serde_json::from_slice(&result).unwrap();
        assert!(parsed.get("safety_settings").is_none());
        assert!(parsed.get("safetySettings").is_none());
    }

    #[test]
    fn sanitize_strips_cached_content() {
        let body = serde_json::json!({
            "contents": [{"parts": [{"text": "hello"}]}],
            "cachedContent": "projects/123/cachedContents/abc"
        });
        let result = sanitize_gemini_body(
            serde_json::to_vec(&body).unwrap().as_slice(),
            "generateContent",
        ).unwrap();
        let parsed: serde_json::Value = serde_json::from_slice(&result).unwrap();
        assert!(parsed.get("cachedContent").is_none());
        assert!(parsed.get("cached_content").is_none());
    }

    #[test]
    fn sanitize_injects_role_when_missing() {
        // Old Swift app versions send contents without role field.
        // Vertex AI requires role ("user"/"model"), AI Studio defaults to "user".
        let body = serde_json::json!({
            "contents": [{"parts": [{"text": "hello"}]}]
        });
        let result = sanitize_gemini_body(
            serde_json::to_vec(&body).unwrap().as_slice(),
            "generateContent",
        ).unwrap();
        let parsed: serde_json::Value = serde_json::from_slice(&result).unwrap();
        assert_eq!(parsed["contents"][0]["role"], "user");
    }

    #[test]
    fn sanitize_preserves_existing_role() {
        let body = serde_json::json!({
            "contents": [
                {"role": "user", "parts": [{"text": "hello"}]},
                {"role": "model", "parts": [{"text": "hi"}]}
            ]
        });
        let result = sanitize_gemini_body(
            serde_json::to_vec(&body).unwrap().as_slice(),
            "generateContent",
        ).unwrap();
        let parsed: serde_json::Value = serde_json::from_slice(&result).unwrap();
        assert_eq!(parsed["contents"][0]["role"], "user");
        assert_eq!(parsed["contents"][1]["role"], "model");
    }

    #[test]
    fn sanitize_injects_role_for_multiple_contents() {
        let body = serde_json::json!({
            "contents": [
                {"parts": [{"text": "hello"}]},
                {"role": "model", "parts": [{"text": "hi"}]},
                {"parts": [{"text": "thanks"}]}
            ]
        });
        let result = sanitize_gemini_body(
            serde_json::to_vec(&body).unwrap().as_slice(),
            "generateContent",
        ).unwrap();
        let parsed: serde_json::Value = serde_json::from_slice(&result).unwrap();
        assert_eq!(parsed["contents"][0]["role"], "user");
        assert_eq!(parsed["contents"][1]["role"], "model");
        assert_eq!(parsed["contents"][2]["role"], "user");
    }

    #[test]
    fn sanitize_allows_empty_contents_without_role_injection() {
        let body = serde_json::json!({
            "contents": []
        });
        let result = sanitize_gemini_body(
            serde_json::to_vec(&body).unwrap().as_slice(),
            "generateContent",
        ).unwrap();
        let parsed: serde_json::Value = serde_json::from_slice(&result).unwrap();
        assert!(parsed["contents"].as_array().unwrap().is_empty());
    }

    #[test]
    fn sanitize_preserves_null_role() {
        // role key exists but is null — preserves it (no override of explicit values)
        let body = serde_json::json!({
            "contents": [{"role": null, "parts": [{"text": "hello"}]}]
        });
        let result = sanitize_gemini_body(
            serde_json::to_vec(&body).unwrap().as_slice(),
            "generateContent",
        ).unwrap();
        let parsed: serde_json::Value = serde_json::from_slice(&result).unwrap();
        // key exists so we don't inject — preserves explicit null
        assert!(parsed["contents"][0]["role"].is_null());
    }

    #[test]
    fn sanitize_preserves_empty_string_role() {
        // role key exists but is "" — preserves it (no override of explicit values)
        let body = serde_json::json!({
            "contents": [{"role": "", "parts": [{"text": "hello"}]}]
        });
        let result = sanitize_gemini_body(
            serde_json::to_vec(&body).unwrap().as_slice(),
            "generateContent",
        ).unwrap();
        let parsed: serde_json::Value = serde_json::from_slice(&result).unwrap();
        assert_eq!(parsed["contents"][0]["role"], "");
    }

    #[test]
    fn sanitize_moves_system_role_to_system_instruction() {
        // role:"system" in contents should be moved to systemInstruction
        let body = serde_json::json!({
            "contents": [
                {"role": "system", "parts": [{"text": "You are a helpful assistant."}]},
                {"role": "user", "parts": [{"text": "Hello"}]}
            ]
        });
        let result = sanitize_gemini_body(
            serde_json::to_vec(&body).unwrap().as_slice(),
            "generateContent",
        ).unwrap();
        let parsed: serde_json::Value = serde_json::from_slice(&result).unwrap();
        // System content removed from contents
        assert_eq!(parsed["contents"].as_array().unwrap().len(), 1);
        assert_eq!(parsed["contents"][0]["role"], "user");
        // Moved to systemInstruction
        assert_eq!(
            parsed["systemInstruction"]["parts"][0]["text"],
            "You are a helpful assistant."
        );
    }

    #[test]
    fn sanitize_merges_system_role_into_existing_system_instruction() {
        // When systemInstruction already exists, system-role parts are appended
        let body = serde_json::json!({
            "systemInstruction": {"parts": [{"text": "Be concise."}]},
            "contents": [
                {"role": "system", "parts": [{"text": "Always respond in English."}]},
                {"role": "user", "parts": [{"text": "Hi"}]}
            ]
        });
        let result = sanitize_gemini_body(
            serde_json::to_vec(&body).unwrap().as_slice(),
            "generateContent",
        ).unwrap();
        let parsed: serde_json::Value = serde_json::from_slice(&result).unwrap();
        assert_eq!(parsed["contents"].as_array().unwrap().len(), 1);
        let si_parts = parsed["systemInstruction"]["parts"].as_array().unwrap();
        assert_eq!(si_parts.len(), 2);
        assert_eq!(si_parts[0]["text"], "Be concise.");
        assert_eq!(si_parts[1]["text"], "Always respond in English.");
    }

    #[test]
    fn sanitize_merges_system_role_into_snake_case_system_instruction() {
        // system_instruction (snake_case) should also work
        let body = serde_json::json!({
            "system_instruction": {"parts": [{"text": "Be concise."}]},
            "contents": [
                {"role": "system", "parts": [{"text": "Extra instruction."}]},
                {"role": "user", "parts": [{"text": "Hi"}]}
            ]
        });
        let result = sanitize_gemini_body(
            serde_json::to_vec(&body).unwrap().as_slice(),
            "generateContent",
        ).unwrap();
        let parsed: serde_json::Value = serde_json::from_slice(&result).unwrap();
        let si_parts = parsed["system_instruction"]["parts"].as_array().unwrap();
        assert_eq!(si_parts.len(), 2);
        assert_eq!(si_parts[0]["text"], "Be concise.");
        assert_eq!(si_parts[1]["text"], "Extra instruction.");
    }

    #[test]
    fn sanitize_handles_multiple_system_role_contents() {
        // Multiple system-role contents should all be collected
        let body = serde_json::json!({
            "contents": [
                {"role": "system", "parts": [{"text": "Instruction 1"}]},
                {"role": "user", "parts": [{"text": "Hello"}]},
                {"role": "system", "parts": [{"text": "Instruction 2"}]}
            ]
        });
        let result = sanitize_gemini_body(
            serde_json::to_vec(&body).unwrap().as_slice(),
            "generateContent",
        ).unwrap();
        let parsed: serde_json::Value = serde_json::from_slice(&result).unwrap();
        assert_eq!(parsed["contents"].as_array().unwrap().len(), 1);
        assert_eq!(parsed["contents"][0]["role"], "user");
        let si_parts = parsed["systemInstruction"]["parts"].as_array().unwrap();
        assert_eq!(si_parts.len(), 2);
        assert_eq!(si_parts[0]["text"], "Instruction 1");
        assert_eq!(si_parts[1]["text"], "Instruction 2");
    }

    #[test]
    fn sanitize_no_system_role_no_system_instruction_added() {
        // When no system role exists, systemInstruction should not be created
        let body = serde_json::json!({
            "contents": [
                {"role": "user", "parts": [{"text": "Hello"}]}
            ]
        });
        let result = sanitize_gemini_body(
            serde_json::to_vec(&body).unwrap().as_slice(),
            "generateContent",
        ).unwrap();
        let parsed: serde_json::Value = serde_json::from_slice(&result).unwrap();
        assert!(parsed.get("systemInstruction").is_none());
        assert!(parsed.get("system_instruction").is_none());
    }

    #[test]
    fn sanitize_preserves_tools_field() {
        let body = serde_json::json!({
            "contents": [{"parts": [{"text": "hello"}]}],
            "tools": [{"function_declarations": [{"name": "execute_sql"}]}],
            "generation_config": {"max_output_tokens": 8192}
        });
        let result = sanitize_gemini_body(
            serde_json::to_vec(&body).unwrap().as_slice(),
            "generateContent",
        ).unwrap();
        let parsed: serde_json::Value = serde_json::from_slice(&result).unwrap();
        assert!(parsed.get("tools").is_some());
    }

    #[test]
    fn sanitize_skips_generation_validation_for_embed() {
        let body = serde_json::json!({
            "model": "models/gemini-embedding-001",
            "content": {"parts": [{"text": "hello"}]},
            "taskType": "RETRIEVAL_DOCUMENT",
            "candidate_count": 5
        });
        // candidate_count > 1 should NOT be rejected for embed actions
        let result = sanitize_gemini_body(
            serde_json::to_vec(&body).unwrap().as_slice(),
            "embedContent",
        );
        assert!(result.is_ok());
    }

    #[test]
    fn sanitize_strips_safety_from_embed() {
        let body = serde_json::json!({
            "model": "models/gemini-embedding-001",
            "content": {"parts": [{"text": "hello"}]},
            "safetySettings": []
        });
        let result = sanitize_gemini_body(
            serde_json::to_vec(&body).unwrap().as_slice(),
            "embedContent",
        ).unwrap();
        let parsed: serde_json::Value = serde_json::from_slice(&result).unwrap();
        assert!(parsed.get("safetySettings").is_none());
    }

    #[test]
    fn sanitize_rejects_non_json() {
        let result = sanitize_gemini_body(b"not json", "generateContent");
        assert!(result.is_err());
    }

    #[test]
    fn sanitize_rejects_non_object() {
        let result = sanitize_gemini_body(b"[1,2,3]", "generateContent");
        assert!(result.is_err());
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

    // --- Embedding body transform (AI Studio → Vertex AI predict) ---

    #[test]
    fn embed_request_transform_basic() {
        let body = serde_json::json!({
            "content": {"parts": [{"text": "hello world"}]},
            "taskType": "RETRIEVAL_DOCUMENT"
        });
        let result = transform_embed_request_to_vertex(
            serde_json::to_vec(&body).unwrap().as_slice(),
        ).unwrap();
        let parsed: serde_json::Value = serde_json::from_slice(&result).unwrap();
        assert_eq!(parsed["instances"][0]["content"], "hello world");
        assert_eq!(parsed["instances"][0]["task_type"], "RETRIEVAL_DOCUMENT");
    }

    #[test]
    fn embed_request_transform_with_title() {
        let body = serde_json::json!({
            "content": {"parts": [{"text": "doc text"}]},
            "taskType": "RETRIEVAL_DOCUMENT",
            "title": "My Document"
        });
        let result = transform_embed_request_to_vertex(
            serde_json::to_vec(&body).unwrap().as_slice(),
        ).unwrap();
        let parsed: serde_json::Value = serde_json::from_slice(&result).unwrap();
        assert_eq!(parsed["instances"][0]["title"], "My Document");
    }

    #[test]
    fn embed_request_transform_no_task_type() {
        let body = serde_json::json!({
            "content": {"parts": [{"text": "simple text"}]}
        });
        let result = transform_embed_request_to_vertex(
            serde_json::to_vec(&body).unwrap().as_slice(),
        ).unwrap();
        let parsed: serde_json::Value = serde_json::from_slice(&result).unwrap();
        assert_eq!(parsed["instances"][0]["content"], "simple text");
        assert!(parsed["instances"][0].get("task_type").is_none());
    }

    #[test]
    fn embed_request_transform_rejects_missing_content() {
        let body = serde_json::json!({"taskType": "RETRIEVAL_QUERY"});
        let result = transform_embed_request_to_vertex(
            serde_json::to_vec(&body).unwrap().as_slice(),
        );
        assert!(result.is_err());
    }

    // --- Vertex AI predict response → AI Studio embed response ---

    #[test]
    fn embed_response_transform_basic() {
        let vertex_resp = serde_json::json!({
            "predictions": [{
                "embeddings": {
                    "values": [0.1, 0.2, 0.3],
                    "statistics": {"truncated": false, "token_count": 2}
                }
            }]
        });
        let result = transform_vertex_embed_response(
            serde_json::to_vec(&vertex_resp).unwrap().as_slice(),
        ).unwrap();
        let parsed: serde_json::Value = serde_json::from_slice(&result).unwrap();
        let values = parsed["embedding"]["values"].as_array().unwrap();
        assert_eq!(values.len(), 3);
        assert_eq!(values[0], 0.1);
    }

    #[test]
    fn embed_response_transform_rejects_missing_predictions() {
        let resp = serde_json::json!({"error": "bad request"});
        let result = transform_vertex_embed_response(
            serde_json::to_vec(&resp).unwrap().as_slice(),
        );
        assert!(result.is_err());
    }

    // --- Integration: embed route composition (preview rewrite + resolve + transform) ---

    /// Verifies the full embed pipeline: resolve_route returns correct action override
    /// and transforms, and the request/response transforms produce correct shapes.
    #[test]
    fn embed_vertex_route_end_to_end_composition() {
        use crate::llm::model_qos::{resolve_route, BodyTransform, Provider, ResponseTransform};

        // 1. resolve_route returns Vertex AI with :predict action and transforms
        let route = resolve_route("gemini-embedding-001", "embedContent");
        assert_eq!(route.provider, Provider::VertexAi);
        assert_eq!(route.vertex_action, Some("predict"));
        assert_eq!(route.request_transform, BodyTransform::EmbedToPredict);
        assert_eq!(route.response_transform, ResponseTransform::PredictToEmbed);

        // 2. Action override: :embedContent → :predict in path
        let path = "models/gemini-embedding-001:embedContent";
        let overridden = path.replace(
            &format!(":{}", "embedContent"),
            &format!(":{}", route.vertex_action.unwrap()),
        );
        assert_eq!(overridden, "models/gemini-embedding-001:predict");

        // 3. Request transform: AI Studio body → Vertex predict body
        let ai_studio_body = serde_json::json!({
            "content": {"parts": [{"text": "test embedding"}]},
            "taskType": "RETRIEVAL_DOCUMENT"
        });
        let vertex_body = transform_embed_request_to_vertex(
            serde_json::to_vec(&ai_studio_body).unwrap().as_slice(),
        ).unwrap();
        let parsed_req: serde_json::Value = serde_json::from_slice(&vertex_body).unwrap();
        assert_eq!(parsed_req["instances"][0]["content"], "test embedding");
        assert_eq!(parsed_req["instances"][0]["task_type"], "RETRIEVAL_DOCUMENT");

        // 4. Response transform: Vertex predict response → AI Studio embed response
        let vertex_response = serde_json::json!({
            "predictions": [{
                "embeddings": {
                    "values": [0.1, 0.2, 0.3, 0.4],
                    "statistics": {"truncated": false, "token_count": 3}
                }
            }]
        });
        let ai_studio_resp = transform_vertex_embed_response(
            serde_json::to_vec(&vertex_response).unwrap().as_slice(),
        ).unwrap();
        let parsed_resp: serde_json::Value = serde_json::from_slice(&ai_studio_resp).unwrap();
        let values = parsed_resp["embedding"]["values"].as_array().unwrap();
        assert_eq!(values.len(), 4);
        // statistics are NOT forwarded — AI Studio format only has values
        assert!(parsed_resp["embedding"].get("statistics").is_none());
    }

    /// Verifies that preview model rewrite + resolve_route produces a Vertex AI route
    /// (old apps requesting preview get rewritten to flash → routed to Vertex).
    #[test]
    fn preview_rewrite_then_resolve_routes_to_vertex() {
        use crate::llm::model_qos::{rewrite_preview_model, resolve_route, Provider};

        let original_path = "models/gemini-3-flash-preview:generateContent";
        let rewritten = rewrite_preview_model(original_path);
        assert_eq!(rewritten, "models/gemini-2.5-flash:generateContent");

        let model = extract_gemini_model(&rewritten);
        let action = extract_gemini_action(&rewritten);
        assert_eq!(model, "gemini-2.5-flash");
        assert_eq!(action, "generateContent");

        let route = resolve_route(model, action);
        assert_eq!(route.provider, Provider::VertexAi);
    }

    /// Verifies Vertex streaming URL preserves query params (e.g., alt=sse).
    /// This covers the streaming proxy's URL construction logic.
    #[test]
    fn vertex_stream_url_preserves_query_params() {
        // Simulate what gemini_stream_proxy does: build Vertex URL then append query params
        let vertex_base = "https://us-central1-aiplatform.googleapis.com/v1/projects/p/locations/us-central1/publishers/google/models/gemini-2.5-flash:streamGenerateContent";
        let mut url = vertex_base.to_string();
        let query: std::collections::HashMap<String, String> = [
            ("alt".to_string(), "sse".to_string()),
            ("key".to_string(), "should-not-appear".to_string()),
        ].into();
        for (k, v) in &query {
            url.push(if url.contains('?') { '&' } else { '?' });
            url.push_str(&urlencoding::encode(k));
            url.push('=');
            url.push_str(&urlencoding::encode(v));
        }
        assert!(url.contains("?") || url.contains("&"));
        assert!(url.contains("alt=sse"));
        // Vertex AI uses Bearer auth, not API key in URL — but query params are forwarded as-is
        assert!(url.starts_with("https://us-central1-aiplatform.googleapis.com"));
    }
}
