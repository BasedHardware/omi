// Chat completions route — OpenAI-compatible POST /v2/chat/completions
//
// Proxies requests to Anthropic (and future providers) with format translation.
// All tokens and cost are logged server-side for billing/cost control.
//
// Issue #6594: Pi-mono harness with Omi API proxy for server-side cost control.

use axum::{
    body::Bytes,
    extract::{DefaultBodyLimit, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::post,
    Json, Router,
};
use futures::StreamExt;
use serde_json::json;

use crate::auth::AuthUser;
use crate::models::chat_completions::*;
use crate::AppState;

use super::rate_limit::RateDecision;

/// Default max_tokens when client doesn't specify one.
const DEFAULT_MAX_TOKENS: u64 = 8192;

/// Maximum allowed max_tokens to prevent abuse.
const MAX_TOKENS_CAP: u64 = 16384;

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

/// Anthropic API base URL.
const ANTHROPIC_API_URL: &str = "https://api.anthropic.com/v1/messages";

/// Anthropic API version header.
const ANTHROPIC_API_VERSION: &str = "2023-06-01";

/// Per-token costs for Anthropic models (USD per token).
/// Updated for Claude 4 / Sonnet 4 pricing.
struct ModelCost {
    input_per_token: f64,
    output_per_token: f64,
    cache_read_per_token: f64,
    cache_write_per_token: f64,
}

fn model_cost(upstream_model: &str) -> ModelCost {
    match upstream_model {
        "claude-sonnet-4-6" => ModelCost {
            input_per_token: 3.0 / 1_000_000.0,
            output_per_token: 15.0 / 1_000_000.0,
            cache_read_per_token: 0.30 / 1_000_000.0,
            cache_write_per_token: 3.75 / 1_000_000.0,
        },
        "claude-opus-4-6" => ModelCost {
            input_per_token: 15.0 / 1_000_000.0,
            output_per_token: 75.0 / 1_000_000.0,
            cache_read_per_token: 1.50 / 1_000_000.0,
            cache_write_per_token: 18.75 / 1_000_000.0,
        },
        _ => ModelCost {
            input_per_token: 3.0 / 1_000_000.0,
            output_per_token: 15.0 / 1_000_000.0,
            cache_read_per_token: 0.30 / 1_000_000.0,
            cache_write_per_token: 3.75 / 1_000_000.0,
        },
    }
}

fn compute_cost(usage: &AnthropicUsage, upstream_model: &str) -> f64 {
    let c = model_cost(upstream_model);
    (usage.input_tokens as f64 * c.input_per_token)
        + (usage.output_tokens as f64 * c.output_per_token)
        + (usage.cache_read_input_tokens as f64 * c.cache_read_per_token)
        + (usage.cache_creation_input_tokens as f64 * c.cache_write_per_token)
}

// ── OpenAI → Anthropic request translation ──────────────────────────────────

fn translate_request(
    req: &ChatCompletionRequest,
    upstream_model: &str,
) -> Result<AnthropicRequest, String> {
    let mut system_prompt: Option<String> = None;
    let mut anthropic_messages: Vec<AnthropicMessage> = Vec::new();

    for msg in &req.messages {
        match msg.role.as_str() {
            // OpenAI uses "developer" as a drop-in replacement for "system" for
            // o1+/reasoning models. Pi's openai-completions client sends this
            // role when reasoning is enabled; treat it identically to "system".
            "system" | "developer" => {
                let text = extract_text_content(&msg.content);
                system_prompt = Some(text);
            }
            "user" => {
                let content = convert_user_content(
                    msg.content.as_ref().cloned().unwrap_or(json!("")),
                );
                anthropic_messages.push(AnthropicMessage {
                    role: "user".to_string(),
                    content,
                });
            }
            "assistant" => {
                let mut content_blocks = Vec::new();

                // Add text content if present
                let text = extract_text_content(&msg.content);
                if !text.is_empty() {
                    content_blocks.push(json!({
                        "type": "text",
                        "text": text
                    }));
                }

                // Add tool_calls as tool_use blocks
                if let Some(tool_calls) = &msg.tool_calls {
                    for tc in tool_calls {
                        let args: serde_json::Value =
                            serde_json::from_str(&tc.function.arguments)
                                .unwrap_or(json!({}));
                        content_blocks.push(json!({
                            "type": "tool_use",
                            "id": tc.id,
                            "name": tc.function.name,
                            "input": args
                        }));
                    }
                }

                if content_blocks.is_empty() {
                    content_blocks.push(json!({
                        "type": "text",
                        "text": ""
                    }));
                }

                anthropic_messages.push(AnthropicMessage {
                    role: "assistant".to_string(),
                    content: json!(content_blocks),
                });
            }
            "tool" => {
                // OpenAI tool result → Anthropic user message with tool_result block
                let tool_call_id = msg
                    .tool_call_id
                    .as_ref()
                    .ok_or("tool message missing tool_call_id")?;
                let result_text = extract_text_content(&msg.content);

                anthropic_messages.push(AnthropicMessage {
                    role: "user".to_string(),
                    content: json!([{
                        "type": "tool_result",
                        "tool_use_id": tool_call_id,
                        "content": result_text
                    }]),
                });
            }
            _ => {
                return Err(format!("unsupported message role: {}", msg.role));
            }
        }
    }

    // Translate tools
    let anthropic_tools = req.tools.as_ref().map(|tools| {
        tools
            .iter()
            .map(|t| AnthropicTool {
                name: t.function.name.clone(),
                description: t.function.description.clone(),
                input_schema: t
                    .function
                    .parameters
                    .clone()
                    .unwrap_or(json!({"type": "object", "properties": {}})),
            })
            .collect()
    });

    let max_tokens = req
        .max_completion_tokens
        .or(req.max_tokens)
        .unwrap_or(DEFAULT_MAX_TOKENS)
        .min(MAX_TOKENS_CAP);

    // Translate tool_choice from OpenAI format to Anthropic format.
    // When tool_choice is "none", strip tools entirely — Anthropic has no "none"
    // and would auto-use tools if they're present in the request.
    let is_tool_choice_none = matches!(
        &req.tool_choice,
        Some(serde_json::Value::String(s)) if s == "none"
    );
    let anthropic_tool_choice = translate_tool_choice(&req.tool_choice)?;

    Ok(AnthropicRequest {
        model: upstream_model.to_string(),
        max_tokens,
        messages: anthropic_messages,
        system: system_prompt,
        temperature: req.temperature,
        stream: req.stream,
        tools: if is_tool_choice_none { None } else { anthropic_tools },
        tool_choice: anthropic_tool_choice,
    })
}

/// Translate OpenAI tool_choice to Anthropic format.
/// OpenAI: "none" | "auto" | "required" | {"type":"function","function":{"name":"..."}}
/// Anthropic: {"type":"auto"} | {"type":"any"} | {"type":"tool","name":"..."}
///
/// Returns Err for unsupported strings or malformed objects — the caller maps
/// this to a 400 Bad Request so clients don't silently get "tools auto-run"
/// behavior when they sent an invalid value.
fn translate_tool_choice(
    choice: &Option<serde_json::Value>,
) -> Result<Option<serde_json::Value>, String> {
    match choice {
        None => Ok(None),
        Some(serde_json::Value::String(s)) => match s.as_str() {
            "none" => Ok(None), // Anthropic has no "none" — tools are stripped upstream
            "auto" => Ok(Some(json!({"type": "auto"}))),
            "required" => Ok(Some(json!({"type": "any"}))),
            other => Err(format!(
                "invalid tool_choice string: {:?} (expected one of: none, auto, required)",
                other
            )),
        },
        Some(serde_json::Value::Object(obj)) => {
            // {"type":"function","function":{"name":"get_weather"}}
            let choice_type = obj
                .get("type")
                .and_then(|t| t.as_str())
                .ok_or_else(|| {
                    "invalid tool_choice object: missing 'type' field".to_string()
                })?;
            if choice_type != "function" {
                return Err(format!(
                    "invalid tool_choice object: unsupported type {:?}",
                    choice_type
                ));
            }
            let func = obj.get("function").ok_or_else(|| {
                "invalid tool_choice object: missing 'function' field".to_string()
            })?;
            let name = func
                .get("name")
                .and_then(|n| n.as_str())
                .ok_or_else(|| {
                    "invalid tool_choice object: missing function.name".to_string()
                })?;
            Ok(Some(json!({"type": "tool", "name": name})))
        }
        Some(other) => Err(format!(
            "invalid tool_choice type: expected string or object, got {}",
            match other {
                serde_json::Value::Null => "null",
                serde_json::Value::Bool(_) => "bool",
                serde_json::Value::Number(_) => "number",
                serde_json::Value::Array(_) => "array",
                _ => "unknown",
            }
        )),
    }
}

/// Convert OpenAI user content to Anthropic format.
///
/// Handles three cases:
/// - String → passed through as-is
/// - Array with `image_url` blocks → converted to Anthropic `image` blocks
///   (data:mime;base64,DATA → { type: "image", source: { type: "base64", media_type, data } })
/// - Everything else → passed through
fn convert_user_content(content: serde_json::Value) -> serde_json::Value {
    match &content {
        serde_json::Value::Array(parts) => {
            let converted: Vec<serde_json::Value> = parts
                .iter()
                .map(|part| {
                    let part_type = part.get("type").and_then(|t| t.as_str()).unwrap_or("");
                    if part_type == "image_url" {
                        // OpenAI format: { type: "image_url", image_url: { url: "data:image/jpeg;base64,..." } }
                        if let Some(url) = part
                            .get("image_url")
                            .and_then(|iu| iu.get("url"))
                            .and_then(|u| u.as_str())
                        {
                            if let Some(rest) = url.strip_prefix("data:") {
                                if let Some(semi_pos) = rest.find(";base64,") {
                                    let media_type = &rest[..semi_pos];
                                    let data = &rest[semi_pos + 8..];
                                    return json!({
                                        "type": "image",
                                        "source": {
                                            "type": "base64",
                                            "media_type": media_type,
                                            "data": data
                                        }
                                    });
                                }
                            }
                        }
                        part.clone()
                    } else {
                        part.clone()
                    }
                })
                .collect();
            json!(converted)
        }
        _ => content,
    }
}

fn extract_text_content(content: &Option<serde_json::Value>) -> String {
    match content {
        Some(serde_json::Value::String(s)) => s.clone(),
        Some(serde_json::Value::Array(parts)) => {
            parts
                .iter()
                .filter_map(|p| {
                    if p.get("type")?.as_str()? == "text" {
                        p.get("text")?.as_str().map(String::from)
                    } else {
                        None
                    }
                })
                .collect::<Vec<_>>()
                .join("")
        }
        Some(serde_json::Value::Null) | None => String::new(),
        Some(other) => other.to_string(),
    }
}

// ── Anthropic non-streaming response → OpenAI format ────────────────────────

fn translate_response(
    resp: &AnthropicResponse,
    public_model: &str,
) -> ChatCompletionResponse {
    let mut text_parts = Vec::new();
    let mut tool_calls = Vec::new();
    let mut tool_index: u32 = 0;

    for block in &resp.content {
        match block {
            AnthropicContentBlock::Text { text } => {
                text_parts.push(text.clone());
            }
            AnthropicContentBlock::ToolUse { id, name, input } => {
                tool_calls.push(ToolCall {
                    id: id.clone(),
                    call_type: "function".to_string(),
                    function: FunctionCall {
                        name: name.clone(),
                        arguments: serde_json::to_string(input).unwrap_or_default(),
                    },
                });
                tool_index += 1;
            }
        }
    }
    let _ = tool_index; // suppress unused warning

    let content = if text_parts.is_empty() {
        None
    } else {
        Some(text_parts.join(""))
    };

    let finish_reason = map_stop_reason(resp.stop_reason.as_deref());
    let usage = anthropic_usage_to_openai(&resp.usage);

    ChatCompletionResponse {
        id: format!("chatcmpl-{}", &resp.id),
        object: "chat.completion",
        created: chrono::Utc::now().timestamp(),
        model: public_model.to_string(),
        choices: vec![Choice {
            index: 0,
            message: ResponseMessage {
                role: "assistant".to_string(),
                content,
                tool_calls: if tool_calls.is_empty() {
                    None
                } else {
                    Some(tool_calls)
                },
            },
            finish_reason,
        }],
        usage: Some(usage),
    }
}

// ── Streaming handler helpers ───────────────────────────────────────────────

fn sse_line(data: &serde_json::Value) -> Bytes {
    let json_str = serde_json::to_string(data).unwrap_or_default();
    Bytes::from(format!("data: {}\n\n", json_str))
}

fn make_chunk(
    id: &str,
    created: i64,
    model: &str,
    delta: ChunkDelta,
    finish_reason: Option<String>,
    usage: Option<Usage>,
) -> serde_json::Value {
    let chunk = ChatCompletionChunk {
        id: id.to_string(),
        object: "chat.completion.chunk",
        created,
        model: model.to_string(),
        choices: vec![ChunkChoice {
            index: 0,
            delta,
            finish_reason,
        }],
        usage,
    };
    serde_json::to_value(chunk).unwrap_or(json!({}))
}

// ── Main handler ────────────────────────────────────────────────────────────

async fn chat_completions(
    State(state): State<AppState>,
    user: AuthUser,
    Json(req): Json<ChatCompletionRequest>,
) -> Result<Response, StatusCode> {
    // Validate model
    let route = resolve_model(&req.model).ok_or_else(|| {
        tracing::warn!(
            "chat_completions: unknown model '{}' from user {}",
            req.model,
            user.uid
        );
        StatusCode::BAD_REQUEST
    })?;

    // Rate limiting
    let decision = state
        .gemini_rate_limiter
        .check_and_record(&user.uid, state.redis.as_ref())
        .await;
    if decision == RateDecision::Reject {
        return Ok(Response::builder()
            .status(StatusCode::TOO_MANY_REQUESTS)
            .header("content-type", "application/json")
            .header("retry-after", "60")
            .body(axum::body::Body::from(
                json!({"error": {"message": "Rate limit exceeded", "type": "rate_limit_error", "code": 429}}).to_string()
            ))
            .unwrap());
    }

    // Get API key
    let api_key = match route.provider {
        Provider::Anthropic => state
            .config
            .anthropic_api_key
            .as_ref()
            .ok_or_else(|| {
                tracing::error!("chat_completions: ANTHROPIC_API_KEY not configured");
                StatusCode::INTERNAL_SERVER_ERROR
            })?,
    };

    // Translate request
    let anthropic_req = translate_request(&req, route.upstream_model).map_err(|e| {
        tracing::warn!("chat_completions: request translation error: {}", e);
        StatusCode::BAD_REQUEST
    })?;

    let client = reqwest::Client::new();

    if req.stream {
        handle_streaming(
            &client,
            api_key,
            &anthropic_req,
            route,
            &user,
            &state,
        )
        .await
    } else {
        handle_non_streaming(
            &client,
            api_key,
            &anthropic_req,
            route,
            &user,
            &state,
        )
        .await
    }
}

async fn handle_non_streaming(
    client: &reqwest::Client,
    api_key: &str,
    anthropic_req: &AnthropicRequest,
    route: &ModelRoute,
    user: &AuthUser,
    state: &AppState,
) -> Result<Response, StatusCode> {
    let upstream_resp = client
        .post(ANTHROPIC_API_URL)
        .header("x-api-key", api_key)
        .header("anthropic-version", ANTHROPIC_API_VERSION)
        .header("content-type", "application/json")
        .json(anthropic_req)
        .send()
        .await
        .map_err(|e| {
            tracing::error!("chat_completions: upstream request failed: {}", e);
            StatusCode::BAD_GATEWAY
        })?;

    let status = upstream_resp.status();
    if !status.is_success() {
        let body = upstream_resp.text().await.unwrap_or_default();
        tracing::warn!(
            "chat_completions: Anthropic returned {} for user {}: {}",
            status,
            user.uid,
            &body[..body.len().min(500)]
        );
        return Ok(Response::builder()
            .status(StatusCode::from_u16(status.as_u16()).unwrap_or(StatusCode::BAD_GATEWAY))
            .header("content-type", "application/json")
            .body(axum::body::Body::from(body))
            .unwrap());
    }

    let anthropic_resp: AnthropicResponse = upstream_resp.json().await.map_err(|e| {
        tracing::error!("chat_completions: failed to parse Anthropic response: {}", e);
        StatusCode::BAD_GATEWAY
    })?;

    // Log usage
    let cost = compute_cost(&anthropic_resp.usage, route.upstream_model);
    log_usage(state, user, &anthropic_resp.usage, cost).await;

    let openai_resp = translate_response(&anthropic_resp, route.public_model);

    Ok(Json(openai_resp).into_response())
}

async fn handle_streaming(
    client: &reqwest::Client,
    api_key: &str,
    anthropic_req: &AnthropicRequest,
    route: &ModelRoute,
    user: &AuthUser,
    state: &AppState,
) -> Result<Response, StatusCode> {
    let upstream_resp = client
        .post(ANTHROPIC_API_URL)
        .header("x-api-key", api_key)
        .header("anthropic-version", ANTHROPIC_API_VERSION)
        .header("content-type", "application/json")
        .json(anthropic_req)
        .send()
        .await
        .map_err(|e| {
            tracing::error!("chat_completions: upstream stream request failed: {}", e);
            StatusCode::BAD_GATEWAY
        })?;

    let status = upstream_resp.status();
    if !status.is_success() {
        let body = upstream_resp.text().await.unwrap_or_default();
        tracing::warn!(
            "chat_completions: Anthropic stream returned {} for user {}: {}",
            status,
            user.uid,
            &body[..body.len().min(500)]
        );
        return Ok(Response::builder()
            .status(StatusCode::from_u16(status.as_u16()).unwrap_or(StatusCode::BAD_GATEWAY))
            .header("content-type", "application/json")
            .body(axum::body::Body::from(body))
            .unwrap());
    }

    // State for stream translation
    let public_model = route.public_model.to_string();
    let upstream_model = route.upstream_model.to_string();
    let uid = user.uid.clone();
    let firestore = state.firestore.clone();

    let byte_stream = upstream_resp.bytes_stream();

    let translated_stream = async_stream::stream! {
        let mut stream_id = String::new();
        let created = chrono::Utc::now().timestamp();
        let model = public_model.clone();
        // Track tool call ordinals: Anthropic content index → OpenAI tool_calls index
        let mut tool_ordinals: std::collections::HashMap<usize, u32> = std::collections::HashMap::new();
        let mut next_tool_ordinal: u32 = 0;
        let mut final_usage: Option<AnthropicUsage> = None;
        let mut initial_usage: Option<AnthropicUsage> = None;
        let mut sent_role = false;
        let mut buffer = String::new();

        // Collect raw bytes and split into SSE events
        let mut byte_stream = std::pin::pin!(byte_stream);
        while let Some(chunk_result) = byte_stream.next().await {
            let chunk = match chunk_result {
                Ok(c) => c,
                Err(e) => {
                    tracing::error!("chat_completions: stream read error: {}", e);
                    break;
                }
            };

            buffer.push_str(&String::from_utf8_lossy(&chunk));

            // Parse SSE events from buffer
            while let Some(event_end) = buffer.find("\n\n") {
                let event_block = buffer[..event_end].to_string();
                buffer = buffer[event_end + 2..].to_string();

                // Extract data line
                let data_line = event_block
                    .lines()
                    .find(|l| l.starts_with("data: "))
                    .map(|l| &l[6..]);

                let data = match data_line {
                    Some(d) => d,
                    None => continue,
                };

                let event: AnthropicStreamEvent = match serde_json::from_str(data) {
                    Ok(e) => e,
                    Err(_) => continue,
                };

                match event {
                    AnthropicStreamEvent::MessageStart { message } => {
                        stream_id = format!("chatcmpl-{}", message.id);
                        initial_usage = Some(message.usage);

                        // Send initial chunk with role
                        if !sent_role {
                            sent_role = true;
                            let chunk_val = make_chunk(
                                &stream_id,
                                created,
                                &model,
                                ChunkDelta {
                                    role: Some("assistant".to_string()),
                                    content: None,
                                    tool_calls: None,
                                },
                                None,
                                None,
                            );
                            yield Ok::<Bytes, std::io::Error>(sse_line(&chunk_val));
                        }
                    }

                    AnthropicStreamEvent::ContentBlockStart { index, content_block } => {
                        match content_block {
                            AnthropicContentBlock::ToolUse { id, name, .. } => {
                                let ordinal = next_tool_ordinal;
                                tool_ordinals.insert(index, ordinal);
                                next_tool_ordinal += 1;

                                let chunk_val = make_chunk(
                                    &stream_id,
                                    created,
                                    &model,
                                    ChunkDelta {
                                        role: None,
                                        content: None,
                                        tool_calls: Some(vec![ChunkToolCall {
                                            index: ordinal,
                                            id: Some(id),
                                            call_type: Some("function".to_string()),
                                            function: Some(ChunkFunctionCall {
                                                name: Some(name),
                                                arguments: Some(String::new()),
                                            }),
                                        }]),
                                    },
                                    None,
                                    None,
                                );
                                yield Ok(sse_line(&chunk_val));
                            }
                            AnthropicContentBlock::Text { .. } => {
                                // text_start — no chunk needed, text comes via deltas
                            }
                        }
                    }

                    AnthropicStreamEvent::ContentBlockDelta { index, delta } => {
                        match delta {
                            AnthropicDelta::TextDelta { text } => {
                                let chunk_val = make_chunk(
                                    &stream_id,
                                    created,
                                    &model,
                                    ChunkDelta {
                                        role: None,
                                        content: Some(text),
                                        tool_calls: None,
                                    },
                                    None,
                                    None,
                                );
                                yield Ok(sse_line(&chunk_val));
                            }
                            AnthropicDelta::InputJsonDelta { partial_json } => {
                                if let Some(&ordinal) = tool_ordinals.get(&index) {
                                    let chunk_val = make_chunk(
                                        &stream_id,
                                        created,
                                        &model,
                                        ChunkDelta {
                                            role: None,
                                            content: None,
                                            tool_calls: Some(vec![ChunkToolCall {
                                                index: ordinal,
                                                id: None,
                                                call_type: None,
                                                function: Some(ChunkFunctionCall {
                                                    name: None,
                                                    arguments: Some(partial_json),
                                                }),
                                            }]),
                                        },
                                        None,
                                        None,
                                    );
                                    yield Ok(sse_line(&chunk_val));
                                }
                            }
                        }
                    }

                    AnthropicStreamEvent::ContentBlockStop { .. } => {
                        // No action needed
                    }

                    AnthropicStreamEvent::MessageDelta { delta, usage } => {
                        if let Some(u) = usage {
                            final_usage = Some(u);
                        }

                        let finish = map_stop_reason(delta.stop_reason.as_deref());
                        let chunk_val = make_chunk(
                            &stream_id,
                            created,
                            &model,
                            ChunkDelta {
                                role: None,
                                content: None,
                                tool_calls: None,
                            },
                            finish,
                            None,
                        );
                        yield Ok(sse_line(&chunk_val));

                        // Send usage chunk
                        if let Some(ref fu) = final_usage {
                            // Merge initial + final usage
                            let merged = AnthropicUsage {
                                input_tokens: initial_usage.as_ref().map_or(0, |u| u.input_tokens),
                                output_tokens: fu.output_tokens,
                                cache_creation_input_tokens: initial_usage.as_ref().map_or(0, |u| u.cache_creation_input_tokens),
                                cache_read_input_tokens: initial_usage.as_ref().map_or(0, |u| u.cache_read_input_tokens),
                            };
                            let openai_usage = anthropic_usage_to_openai(&merged);
                            let usage_chunk = ChatCompletionChunk {
                                id: stream_id.clone(),
                                object: "chat.completion.chunk",
                                created,
                                model: model.clone(),
                                choices: vec![],
                                usage: Some(openai_usage),
                            };
                            let val = serde_json::to_value(usage_chunk).unwrap_or(json!({}));
                            yield Ok(sse_line(&val));
                        }
                    }

                    AnthropicStreamEvent::MessageStop {} => {
                        yield Ok(Bytes::from_static(b"data: [DONE]\n\n"));

                        // Log usage asynchronously
                        if let Some(ref fu) = final_usage {
                            let merged = AnthropicUsage {
                                input_tokens: initial_usage.as_ref().map_or(0, |u| u.input_tokens),
                                output_tokens: fu.output_tokens,
                                cache_creation_input_tokens: initial_usage.as_ref().map_or(0, |u| u.cache_creation_input_tokens),
                                cache_read_input_tokens: initial_usage.as_ref().map_or(0, |u| u.cache_read_input_tokens),
                            };
                            let cost = compute_cost(&merged, &upstream_model);
                            let uid_clone = uid.clone();
                            let fs = firestore.clone();
                            tokio::spawn(async move {
                                if let Err(e) = fs.record_llm_usage(
                                    &uid_clone,
                                    merged.input_tokens,
                                    merged.output_tokens,
                                    merged.cache_read_input_tokens,
                                    merged.cache_creation_input_tokens,
                                    merged.input_tokens + merged.cache_creation_input_tokens
                                        + merged.cache_read_input_tokens + merged.output_tokens,
                                    cost,
                                    "omi",
                                ).await {
                                    tracing::error!("chat_completions: usage log failed: {}", e);
                                }
                            });
                        }
                    }

                    AnthropicStreamEvent::Ping {} => {}

                    AnthropicStreamEvent::Error { error } => {
                        tracing::error!("chat_completions: Anthropic stream error: {}", error.message);
                        let err_chunk = json!({
                            "error": {
                                "message": "Upstream provider error",
                                "type": "server_error",
                                "code": 502
                            }
                        });
                        yield Ok(sse_line(&err_chunk));
                        yield Ok(Bytes::from_static(b"data: [DONE]\n\n"));
                    }
                }
            }
        }
    };

    let body = axum::body::Body::from_stream(translated_stream);

    Ok(Response::builder()
        .status(StatusCode::OK)
        .header("content-type", "text/event-stream")
        .header("cache-control", "no-cache")
        .header("connection", "keep-alive")
        .body(body)
        .unwrap())
}

async fn log_usage(state: &AppState, user: &AuthUser, usage: &AnthropicUsage, cost: f64) {
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
        tracing::error!(
            "chat_completions: usage log failed for {}: {}",
            user.uid,
            e
        );
    }
}

// ── Route registration ──────────────────────────────────────────────────────

pub fn chat_completions_routes() -> Router<AppState> {
    Router::new()
        .route("/v2/chat/completions", post(chat_completions))
        .layer(DefaultBodyLimit::max(CHAT_COMPLETIONS_MAX_BODY_SIZE))
}

// ── Tests ───────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_resolve_model_sonnet() {
        let route = resolve_model("omi-sonnet").unwrap();
        assert_eq!(route.public_model, "omi-sonnet");
        assert_eq!(route.upstream_model, "claude-sonnet-4-6");
        assert_eq!(route.provider, Provider::Anthropic);
    }

    #[test]
    fn test_resolve_model_opus() {
        let route = resolve_model("omi-opus").unwrap();
        assert_eq!(route.public_model, "omi-opus");
        assert_eq!(route.upstream_model, "claude-opus-4-6");
    }

    #[test]
    fn test_resolve_model_claude_aliases() {
        let route = resolve_model("claude-opus-4-6").unwrap();
        assert_eq!(route.upstream_model, "claude-opus-4-6");

        let route = resolve_model("claude-sonnet-4-6").unwrap();
        assert_eq!(route.upstream_model, "claude-sonnet-4-6");
    }

    #[test]
    fn test_resolve_model_legacy_dated_ids() {
        let route = resolve_model("claude-opus-4-20250514").unwrap();
        assert_eq!(route.upstream_model, "claude-opus-4-6");

        let route = resolve_model("claude-sonnet-4-20250514").unwrap();
        assert_eq!(route.upstream_model, "claude-sonnet-4-6");
    }

    #[test]
    fn test_resolve_model_unknown() {
        assert!(resolve_model("gpt-4").is_none());
        assert!(resolve_model("").is_none());
        assert!(resolve_model("omi-haiku").is_none());
    }

    #[test]
    fn test_map_stop_reason() {
        assert_eq!(map_stop_reason(Some("end_turn")), Some("stop".to_string()));
        assert_eq!(
            map_stop_reason(Some("max_tokens")),
            Some("length".to_string())
        );
        assert_eq!(
            map_stop_reason(Some("tool_use")),
            Some("tool_calls".to_string())
        );
        assert_eq!(
            map_stop_reason(Some("stop_sequence")),
            Some("stop".to_string())
        );
        assert_eq!(map_stop_reason(None), None);
    }

    #[test]
    fn test_anthropic_usage_to_openai() {
        let usage = AnthropicUsage {
            input_tokens: 100,
            output_tokens: 50,
            cache_creation_input_tokens: 10,
            cache_read_input_tokens: 20,
        };
        let openai = anthropic_usage_to_openai(&usage);
        assert_eq!(openai.prompt_tokens, 130); // 100 + 10 + 20
        assert_eq!(openai.completion_tokens, 50);
        assert_eq!(openai.total_tokens, 180);
    }

    #[test]
    fn test_compute_cost_sonnet() {
        let usage = AnthropicUsage {
            input_tokens: 1000,
            output_tokens: 500,
            cache_creation_input_tokens: 0,
            cache_read_input_tokens: 0,
        };
        let cost = compute_cost(&usage, "claude-sonnet-4-6");
        // input: 1000 * 3/1M = 0.003, output: 500 * 15/1M = 0.0075
        let expected = 0.003 + 0.0075;
        assert!((cost - expected).abs() < 1e-10);
    }

    #[test]
    fn test_extract_text_content_string() {
        let content = Some(json!("hello world"));
        assert_eq!(extract_text_content(&content), "hello world");
    }

    #[test]
    fn test_extract_text_content_array() {
        let content = Some(json!([
            {"type": "text", "text": "hello "},
            {"type": "text", "text": "world"}
        ]));
        assert_eq!(extract_text_content(&content), "hello world");
    }

    #[test]
    fn test_extract_text_content_none() {
        assert_eq!(extract_text_content(&None), "");
    }

    #[test]
    fn test_translate_request_basic() {
        let req = ChatCompletionRequest {
            model: "omi-sonnet".to_string(),
            messages: vec![
                ChatMessage {
                    role: "system".to_string(),
                    content: Some(json!("You are helpful.")),
                    name: None,
                    tool_calls: None,
                    tool_call_id: None,
                },
                ChatMessage {
                    role: "user".to_string(),
                    content: Some(json!("Hello")),
                    name: None,
                    tool_calls: None,
                    tool_call_id: None,
                },
            ],
            stream: false,
            temperature: Some(0.7),
            max_tokens: Some(1024),
            max_completion_tokens: None,
            tools: None,
            tool_choice: None,
        };

        let result = translate_request(&req, "claude-sonnet-4-6").unwrap();
        assert_eq!(result.model, "claude-sonnet-4-6");
        assert_eq!(result.system, Some("You are helpful.".to_string()));
        assert_eq!(result.messages.len(), 1); // only user message, system extracted
        assert_eq!(result.messages[0].role, "user");
        assert_eq!(result.max_tokens, 1024);
        assert_eq!(result.temperature, Some(0.7));
        assert!(!result.stream);
    }

    #[test]
    fn test_translate_request_max_tokens_cap() {
        let req = ChatCompletionRequest {
            model: "omi-sonnet".to_string(),
            messages: vec![ChatMessage {
                role: "user".to_string(),
                content: Some(json!("Hi")),
                name: None,
                tool_calls: None,
                tool_call_id: None,
            }],
            stream: false,
            temperature: None,
            max_tokens: Some(999999),
            max_completion_tokens: None,
            tools: None,
            tool_choice: None,
        };

        let result = translate_request(&req, "claude-sonnet-4-6").unwrap();
        assert_eq!(result.max_tokens, MAX_TOKENS_CAP);
    }

    #[test]
    fn test_translate_request_default_max_tokens() {
        let req = ChatCompletionRequest {
            model: "omi-sonnet".to_string(),
            messages: vec![ChatMessage {
                role: "user".to_string(),
                content: Some(json!("Hi")),
                name: None,
                tool_calls: None,
                tool_call_id: None,
            }],
            stream: false,
            temperature: None,
            max_tokens: None,
            max_completion_tokens: None,
            tools: None,
            tool_choice: None,
        };

        let result = translate_request(&req, "claude-sonnet-4-6").unwrap();
        assert_eq!(result.max_tokens, DEFAULT_MAX_TOKENS);
    }

    #[test]
    fn test_translate_request_developer_role_treated_as_system() {
        // OpenAI reasoning models (and pi-mono) send role="developer" as a
        // drop-in replacement for role="system". The translator must accept
        // both and fold the message into the top-level Anthropic `system`
        // field. Without this support the request fails validation with a
        // bare 400 (no body), which is invisible to the user.
        let req = ChatCompletionRequest {
            model: "omi-sonnet".to_string(),
            messages: vec![
                ChatMessage {
                    role: "developer".to_string(),
                    content: Some(json!("You are terse.")),
                    name: None,
                    tool_calls: None,
                    tool_call_id: None,
                },
                ChatMessage {
                    role: "user".to_string(),
                    content: Some(json!("hi")),
                    name: None,
                    tool_calls: None,
                    tool_call_id: None,
                },
            ],
            stream: false,
            temperature: None,
            max_tokens: None,
            max_completion_tokens: None,
            tools: None,
            tool_choice: None,
        };

        let result = translate_request(&req, "claude-sonnet-4-6").unwrap();
        assert_eq!(result.system, Some("You are terse.".to_string()));
        assert_eq!(result.messages.len(), 1, "developer msg must be extracted, not forwarded");
        assert_eq!(result.messages[0].role, "user");
    }

    #[test]
    fn test_translate_request_max_completion_tokens_preferred() {
        // OpenAI renamed `max_tokens` → `max_completion_tokens` for reasoning
        // models. Pi sends the new field. Accept both, and prefer
        // max_completion_tokens when both are present (matches OpenAI docs).
        let req = ChatCompletionRequest {
            model: "omi-sonnet".to_string(),
            messages: vec![ChatMessage {
                role: "user".to_string(),
                content: Some(json!("Hi")),
                name: None,
                tool_calls: None,
                tool_call_id: None,
            }],
            stream: false,
            temperature: None,
            max_tokens: Some(100),
            max_completion_tokens: Some(2048),
            tools: None,
            tool_choice: None,
        };

        let result = translate_request(&req, "claude-sonnet-4-6").unwrap();
        assert_eq!(result.max_tokens, 2048);
    }

    #[test]
    fn test_translate_request_max_completion_tokens_only() {
        // Pi only sends max_completion_tokens; max_tokens is absent.
        let req = ChatCompletionRequest {
            model: "omi-sonnet".to_string(),
            messages: vec![ChatMessage {
                role: "user".to_string(),
                content: Some(json!("Hi")),
                name: None,
                tool_calls: None,
                tool_call_id: None,
            }],
            stream: false,
            temperature: None,
            max_tokens: None,
            max_completion_tokens: Some(4096),
            tools: None,
            tool_choice: None,
        };

        let result = translate_request(&req, "claude-sonnet-4-6").unwrap();
        assert_eq!(result.max_tokens, 4096);
    }

    #[test]
    fn test_translate_request_max_completion_tokens_cap() {
        // max_completion_tokens must also respect MAX_TOKENS_CAP to prevent
        // abuse of the hardened cap via the new field name.
        let req = ChatCompletionRequest {
            model: "omi-sonnet".to_string(),
            messages: vec![ChatMessage {
                role: "user".to_string(),
                content: Some(json!("Hi")),
                name: None,
                tool_calls: None,
                tool_call_id: None,
            }],
            stream: false,
            temperature: None,
            max_tokens: None,
            max_completion_tokens: Some(999_999),
            tools: None,
            tool_choice: None,
        };

        let result = translate_request(&req, "claude-sonnet-4-6").unwrap();
        assert_eq!(result.max_tokens, MAX_TOKENS_CAP);
    }

    #[test]
    fn test_translate_request_tool_result() {
        let req = ChatCompletionRequest {
            model: "omi-sonnet".to_string(),
            messages: vec![
                ChatMessage {
                    role: "user".to_string(),
                    content: Some(json!("What's the weather?")),
                    name: None,
                    tool_calls: None,
                    tool_call_id: None,
                },
                ChatMessage {
                    role: "assistant".to_string(),
                    content: None,
                    name: None,
                    tool_calls: Some(vec![ToolCall {
                        id: "call_123".to_string(),
                        call_type: "function".to_string(),
                        function: FunctionCall {
                            name: "get_weather".to_string(),
                            arguments: r#"{"location":"SF"}"#.to_string(),
                        },
                    }]),
                    tool_call_id: None,
                },
                ChatMessage {
                    role: "tool".to_string(),
                    content: Some(json!("72°F and sunny")),
                    name: None,
                    tool_calls: None,
                    tool_call_id: Some("call_123".to_string()),
                },
            ],
            stream: false,
            temperature: None,
            max_tokens: None,
            max_completion_tokens: None,
            tools: None,
            tool_choice: None,
        };

        let result = translate_request(&req, "claude-sonnet-4-6").unwrap();
        assert_eq!(result.messages.len(), 3);
        assert_eq!(result.messages[0].role, "user");
        assert_eq!(result.messages[1].role, "assistant");
        assert_eq!(result.messages[2].role, "user"); // tool result becomes user message
    }

    #[test]
    fn test_translate_request_with_tools() {
        let req = ChatCompletionRequest {
            model: "omi-sonnet".to_string(),
            messages: vec![ChatMessage {
                role: "user".to_string(),
                content: Some(json!("Hi")),
                name: None,
                tool_calls: None,
                tool_call_id: None,
            }],
            stream: false,
            temperature: None,
            max_tokens: None,
            max_completion_tokens: None,
            tools: Some(vec![ToolDefinition {
                tool_type: "function".to_string(),
                function: FunctionDefinition {
                    name: "get_weather".to_string(),
                    description: Some("Get weather for a location".to_string()),
                    parameters: Some(json!({
                        "type": "object",
                        "properties": {
                            "location": {"type": "string"}
                        },
                        "required": ["location"]
                    })),
                },
            }]),
            tool_choice: None,
        };

        let result = translate_request(&req, "claude-sonnet-4-6").unwrap();
        let tools = result.tools.unwrap();
        assert_eq!(tools.len(), 1);
        assert_eq!(tools[0].name, "get_weather");
        assert_eq!(
            tools[0].description,
            Some("Get weather for a location".to_string())
        );
    }

    #[test]
    fn test_translate_response_text_only() {
        let resp = AnthropicResponse {
            id: "msg_123".to_string(),
            response_type: "message".to_string(),
            model: "claude-sonnet-4-6".to_string(),
            role: "assistant".to_string(),
            content: vec![AnthropicContentBlock::Text {
                text: "Hello!".to_string(),
            }],
            stop_reason: Some("end_turn".to_string()),
            usage: AnthropicUsage {
                input_tokens: 10,
                output_tokens: 5,
                cache_creation_input_tokens: 0,
                cache_read_input_tokens: 0,
            },
        };

        let openai = translate_response(&resp, "omi-sonnet");
        assert_eq!(openai.model, "omi-sonnet");
        assert_eq!(openai.choices.len(), 1);
        assert_eq!(
            openai.choices[0].message.content,
            Some("Hello!".to_string())
        );
        assert!(openai.choices[0].message.tool_calls.is_none());
        assert_eq!(
            openai.choices[0].finish_reason,
            Some("stop".to_string())
        );
        let usage = openai.usage.unwrap();
        assert_eq!(usage.prompt_tokens, 10);
        assert_eq!(usage.completion_tokens, 5);
    }

    #[test]
    fn test_translate_response_with_tool_use() {
        let resp = AnthropicResponse {
            id: "msg_456".to_string(),
            response_type: "message".to_string(),
            model: "claude-sonnet-4-6".to_string(),
            role: "assistant".to_string(),
            content: vec![
                AnthropicContentBlock::Text {
                    text: "Let me check.".to_string(),
                },
                AnthropicContentBlock::ToolUse {
                    id: "toolu_789".to_string(),
                    name: "get_weather".to_string(),
                    input: json!({"location": "SF"}),
                },
            ],
            stop_reason: Some("tool_use".to_string()),
            usage: AnthropicUsage {
                input_tokens: 100,
                output_tokens: 50,
                cache_creation_input_tokens: 0,
                cache_read_input_tokens: 0,
            },
        };

        let openai = translate_response(&resp, "omi-sonnet");
        assert_eq!(
            openai.choices[0].message.content,
            Some("Let me check.".to_string())
        );
        let tool_calls = openai.choices[0].message.tool_calls.as_ref().unwrap();
        assert_eq!(tool_calls.len(), 1);
        assert_eq!(tool_calls[0].id, "toolu_789");
        assert_eq!(tool_calls[0].function.name, "get_weather");
        assert_eq!(
            openai.choices[0].finish_reason,
            Some("tool_calls".to_string())
        );
    }

    #[test]
    fn test_translate_response_tool_only_no_text() {
        let resp = AnthropicResponse {
            id: "msg_abc".to_string(),
            response_type: "message".to_string(),
            model: "claude-sonnet-4-6".to_string(),
            role: "assistant".to_string(),
            content: vec![AnthropicContentBlock::ToolUse {
                id: "toolu_def".to_string(),
                name: "bash".to_string(),
                input: json!({"command": "ls"}),
            }],
            stop_reason: Some("tool_use".to_string()),
            usage: AnthropicUsage::default(),
        };

        let openai = translate_response(&resp, "omi-sonnet");
        assert!(openai.choices[0].message.content.is_none());
        assert!(openai.choices[0].message.tool_calls.is_some());
    }

    #[test]
    fn test_sse_line_format() {
        let val = json!({"test": true});
        let line = sse_line(&val);
        let s = std::str::from_utf8(&line).unwrap();
        assert!(s.starts_with("data: "));
        assert!(s.ends_with("\n\n"));
        assert!(s.contains("\"test\":true"));
    }

    #[test]
    fn test_make_chunk_text_delta() {
        let val = make_chunk(
            "chatcmpl-123",
            1700000000,
            "omi-sonnet",
            ChunkDelta {
                role: None,
                content: Some("Hello".to_string()),
                tool_calls: None,
            },
            None,
            None,
        );

        assert_eq!(val["object"], "chat.completion.chunk");
        assert_eq!(val["choices"][0]["delta"]["content"], "Hello");
        assert!(val["choices"][0]["finish_reason"].is_null());
    }

    #[test]
    fn test_make_chunk_finish() {
        let val = make_chunk(
            "chatcmpl-123",
            1700000000,
            "omi-sonnet",
            ChunkDelta {
                role: None,
                content: None,
                tool_calls: None,
            },
            Some("stop".to_string()),
            None,
        );

        assert_eq!(val["choices"][0]["finish_reason"], "stop");
    }

    #[test]
    fn test_translate_tool_choice_auto() {
        let choice = Some(json!("auto"));
        let result = translate_tool_choice(&choice).unwrap();
        assert_eq!(result, Some(json!({"type": "auto"})));
    }

    #[test]
    fn test_translate_tool_choice_required() {
        let choice = Some(json!("required"));
        let result = translate_tool_choice(&choice).unwrap();
        assert_eq!(result, Some(json!({"type": "any"})));
    }

    #[test]
    fn test_translate_tool_choice_none() {
        let choice = Some(json!("none"));
        let result = translate_tool_choice(&choice).unwrap();
        assert!(result.is_none());
    }

    #[test]
    fn test_translate_tool_choice_named_function() {
        let choice = Some(json!({
            "type": "function",
            "function": {"name": "get_weather"}
        }));
        let result = translate_tool_choice(&choice).unwrap();
        assert_eq!(result, Some(json!({"type": "tool", "name": "get_weather"})));
    }

    #[test]
    fn test_translate_tool_choice_absent() {
        let result = translate_tool_choice(&None).unwrap();
        assert!(result.is_none());
    }

    #[test]
    fn test_tool_choice_none_strips_tools() {
        let req = ChatCompletionRequest {
            model: "omi-sonnet".to_string(),
            messages: vec![ChatMessage {
                role: "user".to_string(),
                content: Some(json!("hello")),
                name: None,
                tool_calls: None,
                tool_call_id: None,
            }],
            stream: false,
            temperature: None,
            max_tokens: None,
            max_completion_tokens: None,
            tools: Some(vec![ToolDefinition {
                tool_type: "function".to_string(),
                function: FunctionDefinition {
                    name: "get_weather".to_string(),
                    description: Some("Get weather".to_string()),
                    parameters: Some(json!({"type": "object", "properties": {}})),
                },
            }]),
            tool_choice: Some(json!("none")),
        };

        let result = translate_request(&req, "claude-sonnet-4-6").unwrap();
        // tool_choice "none" must strip tools entirely
        assert!(result.tools.is_none(), "tools should be stripped when tool_choice is 'none'");
        assert!(result.tool_choice.is_none());
    }

    #[test]
    fn test_translate_request_unsupported_role() {
        let req = ChatCompletionRequest {
            model: "omi-sonnet".to_string(),
            messages: vec![ChatMessage {
                role: "function".to_string(),
                content: Some(json!("result")),
                name: None,
                tool_calls: None,
                tool_call_id: None,
            }],
            stream: false,
            temperature: None,
            max_tokens: None,
            max_completion_tokens: None,
            tools: None,
            tool_choice: None,
        };

        let result = translate_request(&req, "claude-sonnet-4-6");
        assert!(result.is_err());
    }

    // ── Boundary tests for tool_choice edge cases ──────────────────────

    #[test]
    fn test_translate_tool_choice_unknown_string() {
        // Unknown strings must return Err (→ 400) instead of silently coercing
        let choice = Some(json!("invalid_value"));
        let result = translate_tool_choice(&choice);
        assert!(result.is_err(), "unknown string tool_choice must return Err");
    }

    #[test]
    fn test_translate_tool_choice_empty_string() {
        let choice = Some(json!(""));
        let result = translate_tool_choice(&choice);
        assert!(result.is_err(), "empty string tool_choice must return Err");
    }

    #[test]
    fn test_translate_tool_choice_null() {
        let choice = Some(serde_json::Value::Null);
        let result = translate_tool_choice(&choice);
        assert!(result.is_err(), "null tool_choice must return Err");
    }

    #[test]
    fn test_translate_tool_choice_object_without_function_name() {
        // Malformed objects must return Err (→ 400)
        let choice = Some(json!({"type": "function", "function": {}}));
        let result = translate_tool_choice(&choice);
        assert!(result.is_err(), "object without function.name must return Err");
    }

    #[test]
    fn test_translate_tool_choice_object_with_non_string_function_name() {
        let choice = Some(json!({
            "type": "function",
            "function": {"name": 123}
        }));
        let result = translate_tool_choice(&choice);
        assert!(result.is_err(), "non-string function.name must return Err");
    }

    #[test]
    fn test_translate_tool_choice_object_with_non_function_type() {
        let choice = Some(json!({
            "type": "tool",
            "function": {"name": "get_weather"}
        }));
        let result = translate_tool_choice(&choice);
        assert!(result.is_err(), "non-function tool_choice object must return Err");
    }

    #[test]
    fn test_translate_tool_choice_object_wrong_shape() {
        // Non-function object shape must return Err (→ 400)
        let choice = Some(json!({"type": "tool", "name": "foo"}));
        let result = translate_tool_choice(&choice);
        assert!(result.is_err(), "non-function object shape must return Err");
    }

    #[test]
    fn test_translate_tool_choice_wrong_type() {
        // Non-string/object values (numbers, bools, arrays) must return Err
        assert!(translate_tool_choice(&Some(json!(42))).is_err());
        assert!(translate_tool_choice(&Some(json!(true))).is_err());
        assert!(translate_tool_choice(&Some(json!([]))).is_err());
    }

    #[test]
    fn test_translate_request_invalid_tool_choice_propagates_error() {
        // Invalid tool_choice must bubble up as Err from translate_request
        let req = ChatCompletionRequest {
            model: "omi-sonnet".to_string(),
            messages: vec![ChatMessage {
                role: "user".to_string(),
                content: Some(json!("hello")),
                name: None,
                tool_calls: None,
                tool_call_id: None,
            }],
            stream: false,
            temperature: None,
            max_tokens: None,
            max_completion_tokens: None,
            tools: None,
            tool_choice: Some(json!("bogus")),
        };
        let result = translate_request(&req, "claude-sonnet-4-6");
        assert!(result.is_err(), "invalid tool_choice must propagate as Err");
    }

    // ── Boundary tests for max_tokens ──────────────────────────────────

    #[test]
    fn test_max_tokens_zero() {
        let req = ChatCompletionRequest {
            model: "omi-sonnet".to_string(),
            messages: vec![ChatMessage {
                role: "user".to_string(),
                content: Some(json!("hello")),
                name: None,
                tool_calls: None,
                tool_call_id: None,
            }],
            stream: false,
            temperature: None,
            max_tokens: Some(0),
            max_completion_tokens: None,
            tools: None,
            tool_choice: None,
        };
        let result = translate_request(&req, "claude-sonnet-4-6").unwrap();
        assert_eq!(result.max_tokens, 0, "max_tokens=0 should be respected (capped at min)");
    }

    #[test]
    fn test_max_tokens_at_cap() {
        let req = ChatCompletionRequest {
            model: "omi-sonnet".to_string(),
            messages: vec![ChatMessage {
                role: "user".to_string(),
                content: Some(json!("hello")),
                name: None,
                tool_calls: None,
                tool_call_id: None,
            }],
            stream: false,
            temperature: None,
            max_tokens: Some(MAX_TOKENS_CAP),
            max_completion_tokens: None,
            tools: None,
            tool_choice: None,
        };
        let result = translate_request(&req, "claude-sonnet-4-6").unwrap();
        assert_eq!(result.max_tokens, MAX_TOKENS_CAP, "max_tokens at exactly the cap should be preserved");
    }

    // ── SSE helper tests ───────────────────────────────────────────────

    #[test]
    fn test_make_chunk_tool_call_delta() {
        let delta = ChunkDelta {
            role: None,
            content: None,
            tool_calls: Some(vec![ChunkToolCall {
                index: 0,
                id: Some("call_123".to_string()),
                function: Some(ChunkFunctionCall {
                    name: Some("get_weather".to_string()),
                    arguments: Some("{\"city\":\"SF\"}".to_string()),
                }),
                call_type: Some("function".to_string()),
            }]),
        };
        let chunk = make_chunk("id-1", 1000, "omi-sonnet", delta, None, None);
        let tool_calls = chunk["choices"][0]["delta"]["tool_calls"].as_array().unwrap();
        assert_eq!(tool_calls.len(), 1);
        assert_eq!(tool_calls[0]["function"]["name"], "get_weather");
        assert_eq!(tool_calls[0]["index"], 0);
    }

    #[test]
    fn test_make_chunk_finish_reason_stop() {
        let delta = ChunkDelta {
            role: None,
            content: Some("done".to_string()),
            tool_calls: None,
        };
        let chunk = make_chunk("id-2", 2000, "omi-sonnet", delta, Some("stop".to_string()), None);
        assert_eq!(chunk["choices"][0]["finish_reason"], "stop");
    }

    #[test]
    fn test_make_chunk_with_usage() {
        let delta = ChunkDelta {
            role: None,
            content: None,
            tool_calls: None,
        };
        let usage = Usage {
            prompt_tokens: 10,
            completion_tokens: 20,
            total_tokens: 30,
        };
        let chunk = make_chunk("id-3", 3000, "omi-sonnet", delta, Some("stop".to_string()), Some(usage));
        assert_eq!(chunk["usage"]["prompt_tokens"], 10);
        assert_eq!(chunk["usage"]["completion_tokens"], 20);
        assert_eq!(chunk["usage"]["total_tokens"], 30);
    }

    #[test]
    fn test_sse_line_done_marker() {
        let done = Bytes::from("data: [DONE]\n\n");
        assert_eq!(done, "data: [DONE]\n\n".as_bytes());
    }

}
