use axum::{
    body::Body,
    extract::{DefaultBodyLimit, State},
    http::{HeaderMap, StatusCode},
    response::Response,
    routing::post,
    Json, Router,
};
use serde_json::json;

use crate::auth::{AuthUser, PaywalledAuthUser};
use crate::byok;
use crate::models::chat_completions::*;
use crate::routes::llm_stub::{llm_stub_enabled, stub_chat_completions_response};
use crate::routes::rate_limit::{requires_server_metering, RateDecision};
use crate::routes::retrieval_policy::{caller_disabled_tools, retrieval_policy, RetrievalSource};
use crate::AppState;

use super::request_translation::{translate_request_inner, web_search_enabled, ReasoningEffort};
use super::response_or_500;
use super::streaming::{handle_server_tool_streaming, handle_streaming};
use super::transport::{handle_non_streaming, new_anthropic_client};

pub(super) fn chat_metering_response(decision: &RateDecision) -> Option<Response> {
    match decision {
        RateDecision::Reject => Some(response_or_500(
            Response::builder()
                .status(StatusCode::TOO_MANY_REQUESTS)
                .header("content-type", "application/json")
                .header("retry-after", "60"),
            Body::from(
                json!({"error": {"message": "Rate limit exceeded", "type": "rate_limit_error", "code": 429}})
                    .to_string(),
            ),
        )),
        RateDecision::Unavailable => Some(response_or_500(
            Response::builder()
                .status(StatusCode::SERVICE_UNAVAILABLE)
                .header("content-type", "application/json")
                .header("retry-after", "5"),
            Body::from(
                json!({"error": {"message": "Chat metering is temporarily unavailable", "type": "metering_unavailable", "code": 503}})
                    .to_string(),
            ),
        )),
        RateDecision::Allow | RateDecision::DegradeToFlash => None,
    }
}
/// Request body size limit for /v2/chat/completions.
///
/// Axum's default is 2 MB, which is too small for multi-modal chat: the
/// pi-mono floating-bar session reuses history across turns and posts every
/// prior screenshot back to Anthropic on every request, so after ~3 turns
/// with a 500 KB WebP screenshot per turn the body exceeds 2 MB and requests
/// fail with `413 Failed to buffer the request body: length limit exceeded`.
///
/// 16 MB gives headroom for ~20 accumulated screenshots before hitting the
/// cap, which covers all realistic floating-bar sessions. History trimming
/// is tracked separately as the longer-term fix.
const CHAT_COMPLETIONS_MAX_BODY_SIZE: usize = 16 * 1024 * 1024;

const OMI_REQUEST_ID_HEADER: &str = "x-omi-request-id";
const RESPONSE_REQUEST_ID_HEADER: &str = "x-request-id";
/// Per-turn effort directive from the desktop app (relayed by the pi-mono
/// extension). Header wins over the OpenAI-compatible body field.
const OMI_REASONING_EFFORT_HEADER: &str = "x-omi-reasoning-effort";

fn inbound_reasoning_effort(headers: &HeaderMap, req: &ChatCompletionRequest) -> ReasoningEffort {
    headers
        .get(OMI_REASONING_EFFORT_HEADER)
        .and_then(|value| value.to_str().ok())
        .and_then(ReasoningEffort::parse)
        .or_else(|| {
            req.reasoning_effort
                .as_deref()
                .and_then(ReasoningEffort::parse)
        })
        .unwrap_or_default()
}

fn inbound_request_id(headers: &HeaderMap) -> String {
    headers
        .get(OMI_REQUEST_ID_HEADER)
        .and_then(|value| value.to_str().ok())
        .filter(|value| {
            !value.is_empty()
                && value.len() <= 128
                && value
                    .bytes()
                    .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_'))
        })
        .map(ToOwned::to_owned)
        .unwrap_or_else(|| ulid::Ulid::new().to_string())
}

fn attach_request_id(response: &mut Response, request_id: &str) {
    if let Ok(value) = request_id.parse() {
        response
            .headers_mut()
            .insert(RESPONSE_REQUEST_ID_HEADER, value);
    }
}

async fn chat_completions(
    State(state): State<AppState>,
    deadline: crate::request_deadline::RequestDeadline,
    user: PaywalledAuthUser,
    headers: HeaderMap,
    Json(req): Json<ChatCompletionRequest>,
) -> Result<Response, StatusCode> {
    let request_id = inbound_request_id(&headers);
    tracing::info!(
        event = "chat_completion_request",
        request_id = %request_id,
        streaming = req.stream,
        reasoning_effort = ?inbound_reasoning_effort(&headers, &req),
        "chat completion received"
    );
    let response = chat_completions_inner(state, user, headers, req, deadline).await;
    response.map(|mut response| {
        attach_request_id(&mut response, &request_id);
        response
    })
}

async fn chat_completions_inner(
    state: AppState,
    user: PaywalledAuthUser,
    headers: HeaderMap,
    req: ChatCompletionRequest,
    deadline: crate::request_deadline::RequestDeadline,
) -> Result<Response, StatusCode> {
    let byok_stripped = user.byok_stripped;
    let user: AuthUser = user.into();

    if llm_stub_enabled() {
        return Ok(stub_chat_completions_response(&req));
    }

    // Validate model
    let route = resolve_model(&req.model).ok_or_else(|| {
        tracing::warn!(
            "chat_completions: unknown model '{}' from user {}",
            req.model,
            user.uid
        );
        StatusCode::BAD_REQUEST
    })?;

    let web_search_enabled = web_search_enabled();
    let policy = retrieval_policy(&req.messages);
    // Only an explicit "search the web" is worth failing the turn over. A
    // heuristic guess degrades to a normal answer in `translate_request_inner`.
    if policy.requires(RetrievalSource::PublicWeb)
        && policy.web_requirement_is_explicit()
        && !caller_disabled_tools(&req)
        && (!web_search_enabled || route.upstream_model.starts_with("claude-haiku"))
    {
        tracing::warn!(
            event = "retrieval_policy",
            required_web = true,
            reason = policy.reason(),
            web_search_exposed = false,
            web_search_forced = false,
            "required public web search is unavailable"
        );
        return Ok(response_or_500(
            Response::builder()
                .status(StatusCode::SERVICE_UNAVAILABLE)
                .header("content-type", "application/json"),
            Body::from(
                json!({
                    "error": {
                        "message": "Public web search is temporarily unavailable. Please try again.",
                        "type": "web_search_unavailable",
                        "code": 503
                    }
                })
                .to_string(),
            ),
        ));
    }

    // BYOK: check for user-provided Anthropic API key (issue #7357).
    // When present, use the user's key and skip server-key rate limiting.
    let byok_anthropic_key =
        byok::get_byok_key_if_active(&headers, byok::HEADER_ANTHROPIC, byok_stripped);
    let is_byok = byok_anthropic_key.is_some();

    // Rate limiting — uses the dedicated CHAT limiter (NOT the Gemini one), so a
    // burst of proactive/vision Gemini calls can never 429 a user's chat. The chat
    // limiter only trips on a pathological per-minute burst (runaway client), which
    // a human typing never reaches. Skipped entirely when using a BYOK key.
    if requires_server_metering(is_byok) {
        let decision = state
            .chat_rate_limiter
            .check_and_record(&user.uid, state.redis.as_ref())
            .await;
        if let Some(response) = chat_metering_response(&decision) {
            return Ok(response);
        }
    }

    // Get API key — prefer BYOK, fall back to server key
    let api_key: String = if let Some(byok_key) = byok_anthropic_key {
        tracing::info!(
            "chat_completions: using BYOK Anthropic key for uid={}",
            user.uid
        );
        byok_key.to_string()
    } else {
        state
            .config
            .anthropic_api_key
            .as_ref()
            .ok_or_else(|| {
                tracing::error!("chat_completions: ANTHROPIC_API_KEY not configured");
                StatusCode::INTERNAL_SERVER_ERROR
            })?
            .clone()
    };

    // Translate request
    let reasoning_effort = inbound_reasoning_effort(&headers, &req);
    let anthropic_req = translate_request_inner(
        &req,
        route.upstream_model,
        web_search_enabled,
        reasoning_effort,
    )
    .map_err(|e| {
        tracing::warn!("chat_completions: request translation error: {}", e);
        StatusCode::BAD_REQUEST
    })?;

    // Bound connection establishment so a network blip can't hang the request; the
    // total-response timeout is applied per-call (non-streaming only) inside the retry
    // helper so it never aborts a long streaming reply.
    let client = new_anthropic_client();

    if req.stream && anthropic_req.requires_public_web {
        handle_server_tool_streaming(
            &client,
            &api_key,
            &anthropic_req,
            route,
            &user,
            &state,
            is_byok,
            &deadline,
        )
        .await
    } else if req.stream {
        handle_streaming(
            &client,
            &api_key,
            &anthropic_req,
            route,
            &user,
            &state,
            is_byok,
            &deadline,
        )
        .await
    } else {
        handle_non_streaming(
            &client,
            &api_key,
            &anthropic_req,
            route,
            &user,
            &state,
            is_byok,
            &deadline,
        )
        .await
    }
}

pub(crate) fn chat_completions_routes() -> Router<AppState> {
    Router::new()
        .route("/v2/chat/completions", post(chat_completions))
        .layer(DefaultBodyLimit::max(CHAT_COMPLETIONS_MAX_BODY_SIZE))
        // Outermost for this route: the budget must exist before extractors and
        // body extraction so auth/paywall waits are inside it (#9835).
        .layer(axum::middleware::from_fn(
            crate::request_deadline::attach_request_deadline,
        ))
}

#[cfg(test)]
mod tests {
    use axum::{
        body::Body,
        http::{HeaderMap, HeaderValue},
        response::Response,
    };

    use super::{attach_request_id, inbound_request_id};

    #[test]
    fn preserves_a_valid_opaque_request_id() {
        let mut headers = HeaderMap::new();
        headers.insert("x-omi-request-id", HeaderValue::from_static("req_01AB-cd"));

        assert_eq!(inbound_request_id(&headers), "req_01AB-cd");
    }

    #[test]
    fn replaces_invalid_request_ids_without_echoing_them() {
        let mut headers = HeaderMap::new();
        headers.insert(
            "x-omi-request-id",
            HeaderValue::from_static("request id with spaces"),
        );

        let request_id = inbound_request_id(&headers);
        assert_ne!(request_id, "request id with spaces");
        assert!(request_id.parse::<ulid::Ulid>().is_ok());
    }

    #[test]
    fn echoes_the_resolved_request_id_on_the_response() {
        let mut response = Response::new(Body::empty());

        attach_request_id(&mut response, "req_01AB-cd");

        assert_eq!(response.headers()["x-request-id"], "req_01AB-cd");
    }
}
