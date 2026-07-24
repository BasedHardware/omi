use axum::{
    body::Body,
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::json;
use std::time::Duration;

use crate::auth::AuthUser;
use crate::models::chat_completions::*;
use crate::request_deadline::{send_with_deadline, DeadlineSendError, RequestDeadline};
use crate::AppState;

use super::request_translation::{compute_cost, translate_response};
use super::response_or_500;

/// Anthropic API base URL.
const ANTHROPIC_API_URL: &str = "https://api.anthropic.com/v1/messages";

/// Anthropic API version header.
const ANTHROPIC_API_VERSION: &str = "2023-06-01";

/// Max attempts for the INITIAL Anthropic request (1 try + 2 retries).
const ANTHROPIC_MAX_ATTEMPTS: usize = 3;

/// Anthropic can pause a long-running server-tool turn (for example, web
/// search) and asks callers to resend the complete paused assistant content.
/// Bound internal continuations so an unhealthy upstream cannot hold a client
/// request indefinitely.
const ANTHROPIC_MAX_PAUSE_TURN_CONTINUATIONS: usize = 3;

/// Connection establishment bound; also the floor below which a retry or
/// continuation attempt is not worth starting — an attempt that cannot even
/// finish its handshake inside the budget only delays the typed timeout.
const ANTHROPIC_CONNECT_TIMEOUT: Duration = Duration::from_secs(10);

/// Per-call cap for a non-streaming Anthropic response, bounded further by the
/// request budget at each attempt.
const ANTHROPIC_NON_STREAMING_CAP: Duration = Duration::from_secs(120);

/// A retry/continuation attempt starts only if this much budget remains.
pub(super) const ANTHROPIC_ATTEMPT_FLOOR: Duration = ANTHROPIC_CONNECT_TIMEOUT;

/// The budget ran out before the first client-visible semantic event. Returned
/// inside the platform bound so the gateway, not Cloud Run, owns the mapping.
pub(super) fn chat_timeout_response() -> Response {
    response_or_500(
        Response::builder()
            .status(StatusCode::GATEWAY_TIMEOUT)
            .header("content-type", "application/json")
            .header("retry-after", "5"),
        Body::from(
            json!({
                "error": {
                    "message": "The request exceeded the chat deadline budget before a response started. Please retry.",
                    "type": "upstream_timeout",
                    "code": 504
                }
            })
            .to_string(),
        ),
    )
}

/// Failure surface of the budgeted Anthropic send path.
pub(super) enum AnthropicSendError {
    /// Budget exhausted pre-first-byte; callers return `chat_timeout_response()`.
    DeadlineExpired,
    /// Existing non-budget failure surface, unchanged.
    Gateway(StatusCode),
}

impl AnthropicSendError {
    pub(super) fn into_response_or_status(self) -> Result<Response, StatusCode> {
        match self {
            AnthropicSendError::DeadlineExpired => Ok(chat_timeout_response()),
            AnthropicSendError::Gateway(status) => Err(status),
        }
    }
}

pub(super) fn new_anthropic_client() -> reqwest::Client {
    reqwest::Client::builder()
        .connect_timeout(ANTHROPIC_CONNECT_TIMEOUT)
        .build()
        .unwrap_or_default()
}
pub(super) fn is_transient_status(status: u16) -> bool {
    matches!(status, 408 | 425 | 429 | 500 | 502 | 503 | 504 | 529)
}

/// Backoff before a retry (attempt is the 1-based number that just failed).
pub(super) fn retry_backoff(attempt: usize) -> Duration {
    // 250ms, 500ms — chat is latency-sensitive, so keep retries short and few.
    Duration::from_millis(250u64 * (1u64 << attempt.saturating_sub(1).min(3)))
}

/// Outcome of one provider attempt inside the budgeted retry loop.
pub(super) enum AttemptOutcome<T> {
    /// Final answer (success, or a non-transient status passed through).
    Success(T),
    /// Transient status carrying the pass-through value: if no retry is
    /// available the upstream error is returned as-is, exactly as before.
    Transient { value: T, status: u16 },
    /// Transport error within the budget; nothing to pass through.
    TransportError,
    /// The send hit the budget edge.
    Expired,
}

/// Budget-aware retry policy, generic over the attempt so the policy is
/// testable with a scripted attempt and `tokio::time::pause`.
///
/// - An attempt never starts on an expired budget.
/// - A retry starts only if `remaining()` exceeds `floor` — an attempt that
///   cannot finish its connect handshake only delays the typed timeout.
/// - Backoff sleeps are truncated at the budget edge.
pub(super) async fn retry_with_budget<T, F, Fut>(
    deadline: &RequestDeadline,
    max_attempts: usize,
    floor: Duration,
    mut attempt: F,
) -> Result<T, AnthropicSendError>
where
    F: FnMut(usize) -> Fut,
    Fut: std::future::Future<Output = AttemptOutcome<T>>,
{
    for attempt_number in 1..=max_attempts {
        if deadline.expired() {
            return Err(AnthropicSendError::DeadlineExpired);
        }
        let retry_available =
            |d: &RequestDeadline| attempt_number < max_attempts && d.remaining() > floor;
        match attempt(attempt_number).await {
            AttemptOutcome::Success(value) => return Ok(value),
            AttemptOutcome::Expired => return Err(AnthropicSendError::DeadlineExpired),
            AttemptOutcome::Transient { value, status } => {
                if !retry_available(deadline) {
                    return Ok(value);
                }
                tracing::warn!(
                    "chat_completions: Anthropic {} (attempt {}/{}), retrying",
                    status,
                    attempt_number,
                    max_attempts
                );
                tokio::time::sleep(deadline.derive(retry_backoff(attempt_number))).await;
            }
            AttemptOutcome::TransportError => {
                if !retry_available(deadline) {
                    return Err(AnthropicSendError::Gateway(StatusCode::BAD_GATEWAY));
                }
                tokio::time::sleep(deadline.derive(retry_backoff(attempt_number))).await;
            }
        }
    }
    Err(AnthropicSendError::Gateway(StatusCode::BAD_GATEWAY))
}

/// Send the Anthropic request, retrying the INITIAL response on transient failures
/// (network errors + 429/5xx/529). This is the chat fallback: a single Anthropic blip
/// no longer fails the request. Safe to retry because no output has been produced yet
/// (for streaming we retry before consuming the body). A transient status on the final
/// attempt is returned as-is so the caller passes the upstream error through.
/// Every attempt is bounded by the request budget (#9835).
pub(super) async fn send_anthropic_with_retry(
    client: &reqwest::Client,
    api_key: &str,
    anthropic_req: &AnthropicRequest,
    streaming: bool,
    deadline: &RequestDeadline,
) -> Result<reqwest::Response, AnthropicSendError> {
    retry_with_budget(
        deadline,
        ANTHROPIC_MAX_ATTEMPTS,
        ANTHROPIC_ATTEMPT_FLOOR,
        |attempt_number| async move {
            let mut builder = client
                .post(ANTHROPIC_API_URL)
                .header("x-api-key", api_key)
                .header("anthropic-version", ANTHROPIC_API_VERSION)
                .header("content-type", "application/json")
                .json(anthropic_req);
            // Bound non-streaming calls inside the budget; a streaming response must
            // NOT have a total-response timeout (it would abort long replies) — after
            // headers, progress is governed by the semantic idle timer downstream.
            if !streaming {
                builder = builder.timeout(deadline.derive(ANTHROPIC_NON_STREAMING_CAP));
            }
            match send_with_deadline(builder, deadline).await {
                Ok(resp) => {
                    let status = resp.status().as_u16();
                    if is_transient_status(status) {
                        AttemptOutcome::Transient {
                            value: resp,
                            status,
                        }
                    } else {
                        AttemptOutcome::Success(resp)
                    }
                }
                Err(DeadlineSendError::Expired) => AttemptOutcome::Expired,
                Err(DeadlineSendError::Transport(error)) => {
                    tracing::warn!(
                        "chat_completions: Anthropic request error (attempt {}/{}): {}",
                        attempt_number,
                        ANTHROPIC_MAX_ATTEMPTS,
                        error
                    );
                    AttemptOutcome::TransportError
                }
            }
        },
    )
    .await
}

struct ParsedAnthropicResponse {
    response: AnthropicResponse,
    /// Keep the provider's content blocks verbatim for pause-turn
    /// continuation. The typed response intentionally drops fields that are
    /// irrelevant to OpenAI translation (such as citations), but Anthropic
    /// requires the original assistant content on the next request.
    raw_content: serde_json::Value,
}

async fn receive_anthropic_response(
    client: &reqwest::Client,
    api_key: &str,
    anthropic_req: &AnthropicRequest,
    deadline: &RequestDeadline,
) -> Result<ParsedAnthropicResponse, AnthropicSendError> {
    let upstream_resp =
        send_anthropic_with_retry(client, api_key, anthropic_req, false, deadline).await?;
    let status = upstream_resp.status();
    if !status.is_success() {
        let body = upstream_resp.text().await.unwrap_or_default();
        tracing::warn!(
            "chat_completions: Anthropic continuation returned {}: {}",
            status,
            super::truncate_for_log(&body, 500)
        );
        return Err(AnthropicSendError::Gateway(StatusCode::BAD_GATEWAY));
    }

    let raw_response: serde_json::Value = upstream_resp.json().await.map_err(|e| {
        tracing::error!(
            "chat_completions: failed to parse Anthropic continuation response: {}",
            e
        );
        AnthropicSendError::Gateway(StatusCode::BAD_GATEWAY)
    })?;
    let raw_content = raw_response
        .get("content")
        .cloned()
        .filter(|content| content.is_array())
        .ok_or_else(|| {
            tracing::error!("chat_completions: Anthropic response omitted content blocks");
            AnthropicSendError::Gateway(StatusCode::BAD_GATEWAY)
        })?;
    let response = serde_json::from_value(raw_response).map_err(|e| {
        tracing::error!(
            "chat_completions: failed to decode Anthropic continuation response: {}",
            e
        );
        AnthropicSendError::Gateway(StatusCode::BAD_GATEWAY)
    })?;

    Ok(ParsedAnthropicResponse {
        response,
        raw_content,
    })
}

fn accumulate_anthropic_usage(total: &mut AnthropicUsage, usage: &AnthropicUsage) {
    total.input_tokens += usage.input_tokens;
    total.output_tokens += usage.output_tokens;
    total.cache_creation_input_tokens += usage.cache_creation_input_tokens;
    total.cache_read_input_tokens += usage.cache_read_input_tokens;

    let current_web_searches = total
        .server_tool_use
        .as_ref()
        .map(|tool_use| tool_use.web_search_requests)
        .unwrap_or_default();
    let next_web_searches = usage
        .server_tool_use
        .as_ref()
        .map(|tool_use| tool_use.web_search_requests)
        .unwrap_or_default();
    if total.server_tool_use.is_some() || usage.server_tool_use.is_some() {
        total.server_tool_use = Some(AnthropicServerToolUsage {
            web_search_requests: current_web_searches + next_web_searches,
        });
    }
}

pub(super) fn append_pause_turn_continuation(
    anthropic_req: &mut AnthropicRequest,
    paused_assistant_content: serde_json::Value,
) {
    anthropic_req.messages.push(AnthropicMessage {
        role: "assistant".to_string(),
        content: paused_assistant_content,
    });
}

/// Complete an Anthropic server-tool turn, including bounded `pause_turn`
/// continuations. This stays gateway-owned: OpenAI clients never receive
/// Anthropic's server-tool blocks, but Anthropic receives them unchanged on
/// each continuation as its API requires.
pub(super) async fn complete_anthropic_server_tool_turn(
    client: &reqwest::Client,
    api_key: &str,
    anthropic_req: &AnthropicRequest,
    deadline: &RequestDeadline,
) -> Result<AnthropicResponse, AnthropicSendError> {
    let mut continuation_request = anthropic_req.clone();
    continuation_request.stream = false;
    let mut continuation_count = 0usize;
    let mut aggregate_content = Vec::new();
    let mut aggregate_usage = AnthropicUsage::default();

    loop {
        let ParsedAnthropicResponse {
            mut response,
            raw_content,
        } = receive_anthropic_response(client, api_key, &continuation_request, deadline).await?;
        aggregate_content.append(&mut response.content);
        accumulate_anthropic_usage(&mut aggregate_usage, &response.usage);

        if response.stop_reason.as_deref() != Some("pause_turn") {
            response.content = aggregate_content;
            response.usage = aggregate_usage;
            return Ok(response);
        }

        if continuation_count >= ANTHROPIC_MAX_PAUSE_TURN_CONTINUATIONS {
            tracing::error!(
                max_continuations = ANTHROPIC_MAX_PAUSE_TURN_CONTINUATIONS,
                "chat_completions: Anthropic pause_turn continuation limit reached"
            );
            return Err(AnthropicSendError::Gateway(StatusCode::BAD_GATEWAY));
        }

        // A continuation is pre-first-visible-event work: it starts only if it
        // can plausibly finish inside the budget.
        if deadline.remaining() <= ANTHROPIC_ATTEMPT_FLOOR {
            tracing::warn!(
                "chat_completions: budget exhausted before pause_turn continuation {}",
                continuation_count + 1
            );
            return Err(AnthropicSendError::DeadlineExpired);
        }

        continuation_count += 1;
        append_pause_turn_continuation(&mut continuation_request, raw_content);
        tracing::info!(
            continuation = continuation_count,
            "chat_completions: continuing paused Anthropic server-tool turn"
        );
    }
}

pub(super) async fn handle_non_streaming(
    client: &reqwest::Client,
    api_key: &str,
    anthropic_req: &AnthropicRequest,
    route: &ModelRoute,
    user: &AuthUser,
    state: &AppState,
    is_byok: bool,
    deadline: &RequestDeadline,
) -> Result<Response, StatusCode> {
    let anthropic_resp =
        match complete_anthropic_server_tool_turn(client, api_key, anthropic_req, deadline).await {
            Ok(resp) => resp,
            Err(error) => return error.into_response_or_status(),
        };

    // Log usage — skip for BYOK since the user pays their own bill and
    // including it would overstate Omi's spend in cost dashboards.
    if !is_byok {
        let cost = compute_cost(&anthropic_resp.usage, route.upstream_model);
        log_usage(state, user, &anthropic_resp.usage, cost).await;
    }

    let openai_resp = translate_response(&anthropic_resp, route.public_model);

    Ok(Json(openai_resp).into_response())
}

pub(super) async fn log_usage(
    state: &AppState,
    user: &AuthUser,
    usage: &AnthropicUsage,
    cost: f64,
) {
    let total = usage.input_tokens
        + usage.cache_creation_input_tokens
        + usage.cache_read_input_tokens
        + usage.output_tokens;

    if let Err(e) = state
        .firestore
        .record_llm_usage(
            &user.uid,
            usage.input_tokens,
            usage.output_tokens,
            usage.cache_read_input_tokens,
            usage.cache_creation_input_tokens,
            total,
            cost,
            "omi",
        )
        .await
    {
        tracing::error!("chat_completions: usage log failed for {}: {}", user.uid, e);
    }
}

// ── Route registration ──────────────────────────────────────────────────────
