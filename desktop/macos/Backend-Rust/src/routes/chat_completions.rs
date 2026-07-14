// Chat completions route — OpenAI-compatible POST /v2/chat/completions
//
// Proxies requests to Anthropic (and future providers) with format translation.
// All tokens and cost are logged server-side for billing/cost control.
//
// Issue #6594: Pi-mono harness with Omi API proxy for server-side cost control.

use axum::{
    body::{Body, Bytes},
    extract::{DefaultBodyLimit, State},
    http::{HeaderMap, StatusCode},
    response::{IntoResponse, Response},
    routing::post,
    Json, Router,
};
use futures::StreamExt;
use serde_json::json;
use std::time::Duration;

use crate::auth::{AuthUser, PaywalledAuthUser};
use crate::byok;
use crate::models::chat_completions::*;
use crate::AppState;

use super::llm_stub::{llm_stub_enabled, stub_chat_completions_response};
use super::rate_limit::{requires_server_metering, RateDecision};
use super::retrieval_policy::{
    caller_disabled_tools, prepend_latest_user_instruction, retrieval_policy, RetrievalSource,
    REQUIRED_WEB_SEARCH_INSTRUCTION,
};

fn response_or_500(builder: axum::http::response::Builder, body: Body) -> Response {
    crate::routes::response_or_500("chat_completions", builder, body)
}

fn chat_metering_response(decision: &RateDecision) -> Option<Response> {
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

/// Anthropic server-side web search tool type (same version the Python
/// backend's agentic chat uses). Executed entirely upstream by Anthropic —
/// the OpenAI-side client never sees or executes it.
const WEB_SEARCH_TOOL_TYPE: &str = "web_search_20260209";

/// Max web searches per request (matches the Python backend's agentic chat).
const WEB_SEARCH_MAX_USES: u32 = 5;

/// Anthropic web search pricing: $10 per 1,000 searches.
const WEB_SEARCH_COST_PER_REQUEST: f64 = 10.0 / 1_000.0;

fn web_search_tool_def() -> AnthropicToolDef {
    AnthropicToolDef::Server(json!({
        "type": WEB_SEARCH_TOOL_TYPE,
        "name": "web_search",
        "max_uses": WEB_SEARCH_MAX_USES,
    }))
}

/// Kill switch: set OMI_DESKTOP_WEB_SEARCH_DISABLED=1 to stop injecting the
/// server-side web_search tool without shipping a new desktop build.
fn web_search_enabled() -> bool {
    std::env::var("OMI_DESKTOP_WEB_SEARCH_DISABLED").map_or(true, |v| v != "1")
}

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
            cache_write_per_token: 6.0 / 1_000_000.0, // 1h cache write = 2x base input
        },
        "claude-opus-4-6" => ModelCost {
            input_per_token: 15.0 / 1_000_000.0,
            output_per_token: 75.0 / 1_000_000.0,
            cache_read_per_token: 1.50 / 1_000_000.0,
            cache_write_per_token: 30.0 / 1_000_000.0, // 1h cache write = 2x base input
        },
        "claude-haiku-4-5" => ModelCost {
            input_per_token: 1.0 / 1_000_000.0,
            output_per_token: 5.0 / 1_000_000.0,
            cache_read_per_token: 0.10 / 1_000_000.0,
            cache_write_per_token: 2.0 / 1_000_000.0, // 1h cache write = 2x base input
        },
        _ => ModelCost {
            input_per_token: 3.0 / 1_000_000.0,
            output_per_token: 15.0 / 1_000_000.0,
            cache_read_per_token: 0.30 / 1_000_000.0,
            cache_write_per_token: 6.0 / 1_000_000.0, // 1h cache write = 2x base input
        },
    }
}

fn compute_cost(usage: &AnthropicUsage, upstream_model: &str) -> f64 {
    let c = model_cost(upstream_model);
    let web_search_requests = usage
        .server_tool_use
        .as_ref()
        .map_or(0, |s| s.web_search_requests);
    (usage.input_tokens as f64 * c.input_per_token)
        + (usage.output_tokens as f64 * c.output_per_token)
        + (usage.cache_read_input_tokens as f64 * c.cache_read_per_token)
        + (usage.cache_creation_input_tokens as f64 * c.cache_write_per_token)
        + (web_search_requests as f64 * WEB_SEARCH_COST_PER_REQUEST)
}

// ── OpenAI → Anthropic request translation ──────────────────────────────────

#[cfg(test)]
fn translate_request(
    req: &ChatCompletionRequest,
    upstream_model: &str,
) -> Result<AnthropicRequest, String> {
    translate_request_inner(req, upstream_model, web_search_enabled())
}

fn translate_request_inner(
    req: &ChatCompletionRequest,
    upstream_model: &str,
    enable_web_search: bool,
) -> Result<AnthropicRequest, String> {
    let policy = retrieval_policy(&req.messages);
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
                let content =
                    convert_user_content(msg.content.as_ref().cloned().unwrap_or(json!("")));
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
                            serde_json::from_str(&tc.function.arguments).unwrap_or(json!({}));
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

    // Translate tools. A turn that requires fresh public information gets
    // Anthropic's server-side web_search tool. Keeping this scoped to the
    // retrieval policy means normal agentic turns retain their incremental
    // OpenAI streaming behavior; public-web turns use the gateway's bounded
    // pause-turn continuation below.
    // Haiku is excluded: web_search_20260209 is not supported there, and a
    // tools-bearing haiku request would 400 with it attached.
    let web_search_supported = enable_web_search && !upstream_model.starts_with("claude-haiku");
    let force_web_search =
        policy.requires(RetrievalSource::PublicWeb) && !caller_disabled_tools(req);
    if force_web_search && !web_search_supported {
        return Err(
            "required public web search is unavailable for this model or deployment".to_string(),
        );
    }
    let client_tools = req.tools.as_deref().unwrap_or(&[]);
    let inject_web_search = web_search_supported && force_web_search;
    let anthropic_tools = if client_tools.is_empty() && !inject_web_search {
        req.tools.as_ref().map(|_| Vec::new())
    } else {
        let mut defs: Vec<AnthropicToolDef> = Vec::with_capacity(client_tools.len() + 1);
        if inject_web_search {
            defs.push(web_search_tool_def());
        }
        defs.extend(client_tools.iter().map(|t| {
            AnthropicToolDef::Custom(AnthropicTool {
                name: t.function.name.clone(),
                description: t.function.description.clone(),
                input_schema: t
                    .function
                    .parameters
                    .clone()
                    .unwrap_or(json!({"type": "object", "properties": {}})),
            })
        }));
        Some(defs)
    };

    if force_web_search {
        prepend_latest_user_instruction(&mut anthropic_messages, REQUIRED_WEB_SEARCH_INSTRUCTION);
    }

    tracing::info!(
        event = "retrieval_policy",
        required_web = policy.requires(RetrievalSource::PublicWeb),
        required_private = policy.requires(RetrievalSource::OmiPrivate),
        prohibited_web = policy.prohibits(RetrievalSource::PublicWeb),
        reason = policy.reason(),
        web_search_exposed = inject_web_search,
        web_search_forced = force_web_search,
        "chat_retrieval_policy"
    );

    let max_tokens = req
        .max_completion_tokens
        .or(req.max_tokens)
        .unwrap_or(DEFAULT_MAX_TOKENS)
        .min(MAX_TOKENS_CAP);

    // Translate tool_choice from OpenAI format to Anthropic format.
    // When tool_choice is "none", strip tools entirely — Anthropic has no "none"
    // and would auto-use tools if they're present in the request. A required
    // public lookup must stay `auto`: Anthropic's server-side web_search tool
    // cannot be selected as a direct named tool choice. The instruction above
    // still requires the lookup, while `auto` lets Anthropic execute it through
    // its supported server-tool path.
    let is_tool_choice_none = matches!(
        &req.tool_choice,
        Some(serde_json::Value::String(s)) if s == "none"
    );
    let anthropic_tool_choice = if force_web_search {
        Some(json!({"type": "auto"}))
    } else {
        translate_tool_choice(&req.tool_choice)?
    };

    // ── Prompt caching ──────────────────────────────────────────────────────
    // Breakpoint 1: emit the system prompt as a content block carrying an
    // ephemeral cache_control breakpoint. Anthropic renders the request as
    // tools → system → messages, so a single breakpoint on the system block
    // caches the entire static tools+system prefix (~11k tokens for desktop
    // chat). It is stable within a pi-mono session, so every query after the
    // first reads it at 0.1x instead of re-paying full input cost.
    // (Sonnet min cacheable = 2048 tokens; our prefix clears it easily.)
    // Filter empty/whitespace system prompts — Anthropic rejects empty cached
    // text blocks with 400, and whitespace-only prompts have no semantic value.
    // Use original text (not trimmed) for non-empty prompts to preserve content.
    let system = system_prompt.and_then(|text| {
        let trimmed = text.trim();
        if trimmed.is_empty() {
            None
        } else {
            Some(cached_system_block(text))
        }
    });

    // Breakpoint 2: mark the latest user message so the conversation prefix up
    // to the current turn is cached too. During a tool-use loop one user turn
    // explodes into many assistant/tool round-trips, so caching at that
    // boundary lets every intra-turn request hit the cached prefix — directly
    // attacking the multi-second agentic case. (system + latest-user = 2
    // breakpoints, well under Anthropic's cap of 4.)
    mark_latest_user_message_cached(&mut anthropic_messages);

    Ok(AnthropicRequest {
        model: upstream_model.to_string(),
        max_tokens,
        messages: anthropic_messages,
        // Use the system block produced by cached_system_block() above
        // which already handles kernel-plan splitting for cache
        // stability — do NOT re-create here or we lose the split.
        system,
        temperature: req.temperature,
        stream: req.stream,
        tools: if is_tool_choice_none {
            None
        } else {
            anthropic_tools
        },
        tool_choice: anthropic_tool_choice,
        requires_public_web: force_web_search,
    })
}

/// Ephemeral cache_control breakpoint marker.
///
/// Uses the 1-hour cache TTL (GA — no anthropic-beta header) rather than the
/// default 5 minutes. The floating bar is used intermittently — queries are
/// routinely more than 5 minutes apart — so a 5-minute cache expires between
/// sporadic queries and almost every real query pays a full cache-write,
/// defeating the breakpoint. The 1h TTL keeps the stable system+tools prefix
/// warm across normal usage. Cost trade-off: a 1h write is 2x base input (vs
/// 1.25x for 5m); reads stay 0.1x; break-even is ~3 cache hits within the hour.
fn ephemeral_cache_control() -> serde_json::Value {
    json!({ "type": "ephemeral", "ttl": "1h" })
}

/// Kernel-rendered context starts this dynamic section after the semantic policy
/// that is safe to cache across conversations. This is a produced protocol
/// boundary, not a client-only sentinel: `renderContextSnapshot` emits it for
/// every typed and realtime plan.
const KERNEL_CONTEXT_PLAN_BOUNDARY: &str = "[Kernel Conversation Context Plan";

/// Wrap a system prompt string in cache_control content block(s).
///
/// If the prompt carries a kernel context plan, emit two blocks: the stable
/// semantic-policy prefix (cached) followed by the dynamic conversation plan
/// (uncached, re-sent every request). Otherwise emit a single cached block.
fn cached_system_block(text: String) -> serde_json::Value {
    if let Some(boundary) = text.find(KERNEL_CONTEXT_PLAN_BOUNDARY) {
        let (static_prefix, dynamic_plan) = text.split_at(boundary);
        if !static_prefix.trim().is_empty() && !dynamic_plan.trim().is_empty() {
            return json!([
                {
                    "type": "text",
                    "text": static_prefix,
                    "cache_control": ephemeral_cache_control()
                },
                {
                    "type": "text",
                    "text": dynamic_plan
                }
            ]);
        }
    }
    json!([{
        "type": "text",
        "text": text,
        "cache_control": ephemeral_cache_control()
    }])
}

/// Attach an ephemeral cache_control breakpoint to the latest user message so
/// the conversation prefix up to the current turn is cached. No-op unless the
/// final message is a `user` message. Array content → marks the last block;
/// plain-string content → promoted to a single cached text block (Anthropic
/// accepts either form).
fn mark_latest_user_message_cached(messages: &mut [AnthropicMessage]) {
    let last = match messages.last_mut() {
        Some(m) if m.role == "user" => m,
        _ => return,
    };
    if let serde_json::Value::Array(blocks) = &mut last.content {
        if let Some(serde_json::Value::Object(map)) = blocks.last_mut() {
            map.insert("cache_control".to_string(), ephemeral_cache_control());
        }
        return;
    }
    if let serde_json::Value::String(text) = &last.content {
        let text = text.clone();
        last.content = json!([{
            "type": "text",
            "text": text,
            "cache_control": ephemeral_cache_control()
        }]);
    }
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
                .ok_or_else(|| "invalid tool_choice object: missing 'type' field".to_string())?;
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
                .ok_or_else(|| "invalid tool_choice object: missing function.name".to_string())?;
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
        Some(serde_json::Value::Array(parts)) => parts
            .iter()
            .filter_map(|p| {
                if p.get("type")?.as_str()? == "text" {
                    p.get("text")?.as_str().map(String::from)
                } else {
                    None
                }
            })
            .collect::<Vec<_>>()
            .join(""),
        Some(serde_json::Value::Null) | None => String::new(),
        Some(other) => other.to_string(),
    }
}

// ── Anthropic non-streaming response → OpenAI format ────────────────────────

fn translate_response(resp: &AnthropicResponse, public_model: &str) -> ChatCompletionResponse {
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
            AnthropicContentBlock::ServerToolUse { .. }
            | AnthropicContentBlock::WebSearchToolResult {} => {
                // Server-side tool blocks are consumed upstream — only the
                // text they produced is surfaced to the client.
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

/// Pull every complete SSE event block out of the raw byte buffer, leaving any
/// trailing partial event behind.
///
/// The buffer must stay bytes: network chunks split at arbitrary offsets, so
/// decoding a chunk before it is framed destroys any multi-byte character that
/// straddles the boundary. Event blocks always end on the ASCII "\n\n", so a
/// complete block is safe to decode.
fn drain_sse_events(buffer: &mut Vec<u8>) -> Vec<String> {
    let mut events = Vec::new();
    while let Some(event_end) = buffer.windows(2).position(|w| w == b"\n\n") {
        events.push(String::from_utf8_lossy(&buffer[..event_end]).into_owned());
        buffer.drain(..event_end + 2);
    }
    events
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
    user: PaywalledAuthUser,
    headers: HeaderMap,
    Json(req): Json<ChatCompletionRequest>,
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
    if policy.requires(RetrievalSource::PublicWeb)
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
    let anthropic_req = translate_request_inner(&req, route.upstream_model, web_search_enabled)
        .map_err(|e| {
            tracing::warn!("chat_completions: request translation error: {}", e);
            StatusCode::BAD_REQUEST
        })?;

    // Bound connection establishment so a network blip can't hang the request; the
    // total-response timeout is applied per-call (non-streaming only) inside the retry
    // helper so it never aborts a long streaming reply.
    let client = reqwest::Client::builder()
        .connect_timeout(Duration::from_secs(10))
        .build()
        .unwrap_or_default();

    if req.stream && anthropic_req.requires_public_web {
        handle_server_tool_streaming(
            &client,
            &api_key,
            &anthropic_req,
            route,
            &user,
            &state,
            is_byok,
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
        )
        .await
    }
}

/// Max attempts for the INITIAL Anthropic request (1 try + 2 retries).
const ANTHROPIC_MAX_ATTEMPTS: usize = 3;

/// Anthropic can pause a long-running server-tool turn (for example, web
/// search) and asks callers to resend the complete paused assistant content.
/// Bound internal continuations so an unhealthy upstream cannot hold a client
/// request indefinitely.
const ANTHROPIC_MAX_PAUSE_TURN_CONTINUATIONS: usize = 3;

/// Upstream HTTP statuses worth retrying — transient overload/availability blips.
/// Note: 4xx like 400/401/402 are caller/auth errors and must NOT be retried.
fn is_transient_status(status: u16) -> bool {
    matches!(status, 408 | 425 | 429 | 500 | 502 | 503 | 504 | 529)
}

/// Backoff before a retry (attempt is the 1-based number that just failed).
fn retry_backoff(attempt: usize) -> Duration {
    // 250ms, 500ms — chat is latency-sensitive, so keep retries short and few.
    Duration::from_millis(250u64 * (1u64 << attempt.saturating_sub(1).min(3)))
}

/// Send the Anthropic request, retrying the INITIAL response on transient failures
/// (network errors + 429/5xx/529). This is the chat fallback: a single Anthropic blip
/// no longer fails the request. Safe to retry because no output has been produced yet
/// (for streaming we retry before consuming the body). A transient status on the final
/// attempt is returned as-is so the caller passes the upstream error through.
async fn send_anthropic_with_retry(
    client: &reqwest::Client,
    api_key: &str,
    anthropic_req: &AnthropicRequest,
    streaming: bool,
) -> Result<reqwest::Response, StatusCode> {
    for attempt in 1..=ANTHROPIC_MAX_ATTEMPTS {
        let mut builder = client
            .post(ANTHROPIC_API_URL)
            .header("x-api-key", api_key)
            .header("anthropic-version", ANTHROPIC_API_VERSION)
            .header("content-type", "application/json")
            .json(anthropic_req);
        // Bound non-streaming calls; a streaming response must NOT have a total-response
        // timeout (it would abort long replies), only the client-level connect timeout.
        if !streaming {
            builder = builder.timeout(Duration::from_secs(120));
        }
        match builder.send().await {
            Ok(resp) => {
                let s = resp.status().as_u16();
                if is_transient_status(s) && attempt < ANTHROPIC_MAX_ATTEMPTS {
                    tracing::warn!(
                        "chat_completions: Anthropic {} (attempt {}/{}), retrying",
                        s,
                        attempt,
                        ANTHROPIC_MAX_ATTEMPTS
                    );
                    tokio::time::sleep(retry_backoff(attempt)).await;
                    continue;
                }
                return Ok(resp);
            }
            Err(e) => {
                tracing::warn!(
                    "chat_completions: Anthropic request error (attempt {}/{}): {}",
                    attempt,
                    ANTHROPIC_MAX_ATTEMPTS,
                    e
                );
                if attempt < ANTHROPIC_MAX_ATTEMPTS {
                    tokio::time::sleep(retry_backoff(attempt)).await;
                    continue;
                }
                return Err(StatusCode::BAD_GATEWAY);
            }
        }
    }
    Err(StatusCode::BAD_GATEWAY)
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
) -> Result<ParsedAnthropicResponse, StatusCode> {
    let upstream_resp = send_anthropic_with_retry(client, api_key, anthropic_req, false).await?;
    let status = upstream_resp.status();
    if !status.is_success() {
        let body = upstream_resp.text().await.unwrap_or_default();
        tracing::warn!(
            "chat_completions: Anthropic continuation returned {}: {}",
            status,
            &body[..body.len().min(500)]
        );
        return Err(StatusCode::BAD_GATEWAY);
    }

    let raw_response: serde_json::Value = upstream_resp.json().await.map_err(|e| {
        tracing::error!(
            "chat_completions: failed to parse Anthropic continuation response: {}",
            e
        );
        StatusCode::BAD_GATEWAY
    })?;
    let raw_content = raw_response
        .get("content")
        .cloned()
        .filter(|content| content.is_array())
        .ok_or_else(|| {
            tracing::error!("chat_completions: Anthropic response omitted content blocks");
            StatusCode::BAD_GATEWAY
        })?;
    let response = serde_json::from_value(raw_response).map_err(|e| {
        tracing::error!(
            "chat_completions: failed to decode Anthropic continuation response: {}",
            e
        );
        StatusCode::BAD_GATEWAY
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

fn append_pause_turn_continuation(
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
async fn complete_anthropic_server_tool_turn(
    client: &reqwest::Client,
    api_key: &str,
    anthropic_req: &AnthropicRequest,
) -> Result<AnthropicResponse, StatusCode> {
    let mut continuation_request = anthropic_req.clone();
    continuation_request.stream = false;
    let mut continuation_count = 0usize;
    let mut aggregate_content = Vec::new();
    let mut aggregate_usage = AnthropicUsage::default();

    loop {
        let ParsedAnthropicResponse {
            mut response,
            raw_content,
        } = receive_anthropic_response(client, api_key, &continuation_request).await?;
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
            return Err(StatusCode::BAD_GATEWAY);
        }

        continuation_count += 1;
        append_pause_turn_continuation(&mut continuation_request, raw_content);
        tracing::info!(
            continuation = continuation_count,
            "chat_completions: continuing paused Anthropic server-tool turn"
        );
    }
}

async fn handle_non_streaming(
    client: &reqwest::Client,
    api_key: &str,
    anthropic_req: &AnthropicRequest,
    route: &ModelRoute,
    user: &AuthUser,
    state: &AppState,
    is_byok: bool,
) -> Result<Response, StatusCode> {
    let anthropic_resp =
        complete_anthropic_server_tool_turn(client, api_key, anthropic_req).await?;

    // Log usage — skip for BYOK since the user pays their own bill and
    // including it would overstate Omi's spend in cost dashboards.
    if !is_byok {
        let cost = compute_cost(&anthropic_resp.usage, route.upstream_model);
        log_usage(state, user, &anthropic_resp.usage, cost).await;
    }

    let openai_resp = translate_response(&anthropic_resp, route.public_model);

    Ok(Json(openai_resp).into_response())
}

/// Public-web turns may pause while Anthropic's server-side tool runs. Resolve
/// the bounded continuation chain before producing OpenAI SSE so clients never
/// observe `pause_turn` as a terminal answer. The final response is emitted as
/// normal OpenAI chunks; ordinary turns keep the lower-latency incremental
/// streaming path below.
async fn handle_server_tool_streaming(
    client: &reqwest::Client,
    api_key: &str,
    anthropic_req: &AnthropicRequest,
    route: &ModelRoute,
    user: &AuthUser,
    state: &AppState,
    is_byok: bool,
) -> Result<Response, StatusCode> {
    let anthropic_resp =
        complete_anthropic_server_tool_turn(client, api_key, anthropic_req).await?;

    if !is_byok {
        let cost = compute_cost(&anthropic_resp.usage, route.upstream_model);
        log_usage(state, user, &anthropic_resp.usage, cost).await;
    }

    let openai_resp = translate_response(&anthropic_resp, route.public_model);
    let choice = openai_resp
        .choices
        .first()
        .expect("translated Anthropic response always has one choice");
    let stream_id = openai_resp.id.clone();
    let created = openai_resp.created;
    let model = openai_resp.model.clone();
    let mut chunks = Vec::new();

    chunks.push(sse_line(&make_chunk(
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
    )));

    let tool_calls = choice.message.tool_calls.as_ref().map(|calls| {
        calls
            .iter()
            .enumerate()
            .map(|(index, call)| ChunkToolCall {
                index: index as u32,
                id: Some(call.id.clone()),
                call_type: Some(call.call_type.clone()),
                function: Some(ChunkFunctionCall {
                    name: Some(call.function.name.clone()),
                    arguments: Some(call.function.arguments.clone()),
                }),
            })
            .collect::<Vec<_>>()
    });
    if choice.message.content.is_some() || tool_calls.is_some() {
        chunks.push(sse_line(&make_chunk(
            &stream_id,
            created,
            &model,
            ChunkDelta {
                role: None,
                content: choice.message.content.clone(),
                tool_calls,
            },
            None,
            None,
        )));
    }

    chunks.push(sse_line(&make_chunk(
        &stream_id,
        created,
        &model,
        ChunkDelta {
            role: None,
            content: None,
            tool_calls: None,
        },
        choice.finish_reason.clone(),
        None,
    )));

    if let Some(usage) = openai_resp.usage {
        let usage_chunk = ChatCompletionChunk {
            id: stream_id,
            object: "chat.completion.chunk",
            created,
            model,
            choices: vec![],
            usage: Some(usage),
        };
        chunks.push(sse_line(
            &serde_json::to_value(usage_chunk).unwrap_or(json!({})),
        ));
    }
    chunks.push(Bytes::from_static(b"data: [DONE]\n\n"));

    let body = Body::from_stream(futures::stream::iter(
        chunks.into_iter().map(Ok::<Bytes, std::io::Error>),
    ));
    Ok(response_or_500(
        Response::builder()
            .status(StatusCode::OK)
            .header("content-type", "text/event-stream")
            .header("cache-control", "no-cache")
            .header("connection", "keep-alive"),
        body,
    ))
}

async fn handle_streaming(
    client: &reqwest::Client,
    api_key: &str,
    anthropic_req: &AnthropicRequest,
    route: &ModelRoute,
    user: &AuthUser,
    state: &AppState,
    is_byok: bool,
) -> Result<Response, StatusCode> {
    let upstream_resp = send_anthropic_with_retry(client, api_key, anthropic_req, true).await?;

    let status = upstream_resp.status();
    if !status.is_success() {
        let body = upstream_resp.text().await.unwrap_or_default();
        tracing::warn!(
            "chat_completions: Anthropic stream returned {} for user {}: {}",
            status,
            user.uid,
            &body[..body.len().min(500)]
        );
        return Ok(response_or_500(
            Response::builder()
                .status(StatusCode::from_u16(status.as_u16()).unwrap_or(StatusCode::BAD_GATEWAY))
                .header("content-type", "application/json"),
            Body::from(body),
        ));
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
        let mut buffer: Vec<u8> = Vec::new();

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

            buffer.extend_from_slice(&chunk);

            // Parse SSE events from buffer
            for event_block in drain_sse_events(&mut buffer) {
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
                            AnthropicContentBlock::ServerToolUse { name, .. } => {
                                // Executed upstream by Anthropic — no OpenAI tool_call
                                // is emitted, so the client never tries to run it.
                                // Info-level: each invocation is a billable event.
                                tracing::info!(
                                    "chat_completions: server tool '{}' running upstream",
                                    name
                                );
                            }
                            AnthropicContentBlock::WebSearchToolResult {} => {
                                // Consumed by the model upstream — nothing to forward.
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
                            AnthropicDelta::CitationsDelta {} => {
                                // Web-search citation metadata — no OpenAI equivalent.
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

                        if delta.stop_reason.as_deref() == Some("pause_turn") {
                            // Public-web turns are normalized before reaching the
                            // incremental stream. Treat this as a routing bug,
                            // while retaining a safe OpenAI finish reason below.
                            tracing::error!(
                                "chat_completions: unexpected pause_turn reached incremental stream"
                            );
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
                            let merged = merge_stream_usage(initial_usage.as_ref(), fu);
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

                        // Log usage asynchronously — skip for BYOK (user pays own bill)
                        if !is_byok {
                        if let Some(ref fu) = final_usage {
                            let merged = merge_stream_usage(initial_usage.as_ref(), fu);
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
                        } // if !is_byok
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

    let body = Body::from_stream(translated_stream);

    Ok(response_or_500(
        Response::builder()
            .status(StatusCode::OK)
            .header("content-type", "text/event-stream")
            .header("cache-control", "no-cache")
            .header("connection", "keep-alive"),
        body,
    ))
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
        tracing::error!("chat_completions: usage log failed for {}: {}", user.uid, e);
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
    fn server_key_chat_fails_closed_when_metering_is_unavailable() {
        let response = chat_metering_response(&RateDecision::Unavailable).unwrap();
        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
        assert_eq!(response.headers().get("retry-after").unwrap(), "5");
        assert!(chat_metering_response(&RateDecision::Allow).is_none());
    }

    fn test_request(messages: Vec<ChatMessage>) -> ChatCompletionRequest {
        ChatCompletionRequest {
            model: "omi-sonnet".to_string(),
            messages,
            stream: false,
            temperature: None,
            max_tokens: None,
            max_completion_tokens: None,
            tools: None,
            tool_choice: None,
        }
    }

    fn user_message(text: &str) -> ChatMessage {
        ChatMessage {
            role: "user".to_string(),
            content: Some(json!(text)),
            name: None,
            tool_calls: None,
            tool_call_id: None,
        }
    }

    fn assistant_message(text: &str) -> ChatMessage {
        ChatMessage {
            role: "assistant".to_string(),
            content: Some(json!(text)),
            name: None,
            tool_calls: None,
            tool_call_id: None,
        }
    }

    #[test]
    fn transient_statuses_retry() {
        for s in [408, 425, 429, 500, 502, 503, 504, 529] {
            assert!(is_transient_status(s), "{} should be transient", s);
        }
    }

    #[test]
    fn non_transient_statuses_dont_retry() {
        // 2xx success and caller/auth errors must never be retried.
        for s in [200, 201, 400, 401, 402, 403, 404, 422] {
            assert!(!is_transient_status(s), "{} should NOT be transient", s);
        }
    }

    #[test]
    fn backoff_is_short_and_increasing() {
        let b1 = retry_backoff(1);
        let b2 = retry_backoff(2);
        assert_eq!(b1, Duration::from_millis(250));
        assert_eq!(b2, Duration::from_millis(500));
        // Stays bounded (latency-sensitive path).
        assert!(retry_backoff(10) <= Duration::from_millis(2000));
    }

    #[test]
    fn test_resolve_model_sonnet() {
        let route = resolve_model("omi-sonnet").unwrap();
        assert_eq!(route.public_model, "omi-sonnet");
        assert_eq!(route.upstream_model, "claude-sonnet-4-6");
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
    fn test_resolve_model_haiku() {
        // The AgentPill router classifier sends this exact dated ID; without
        // it the /v2/chat/completions endpoint 400s and agent pills never
        // spawn from natural-language prompts.
        let route = resolve_model("claude-haiku-4-5-20251001").unwrap();
        assert_eq!(route.upstream_model, "claude-haiku-4-5");

        let route = resolve_model("claude-haiku-4-5").unwrap();
        assert_eq!(route.upstream_model, "claude-haiku-4-5");
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
            server_tool_use: None,
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
            server_tool_use: None,
        };
        let cost = compute_cost(&usage, "claude-sonnet-4-6");
        // input: 1000 * 3/1M = 0.003, output: 500 * 15/1M = 0.0075
        let expected = 0.003 + 0.0075;
        assert!((cost - expected).abs() < 1e-10);
    }

    #[test]
    fn test_compute_cost_includes_web_search_requests() {
        let usage = AnthropicUsage {
            input_tokens: 1000,
            output_tokens: 500,
            cache_creation_input_tokens: 0,
            cache_read_input_tokens: 0,
            server_tool_use: Some(AnthropicServerToolUsage {
                web_search_requests: 3,
            }),
        };
        let cost = compute_cost(&usage, "claude-sonnet-4-6");
        // tokens: 0.003 + 0.0075, web search: 3 * $0.01
        let expected = 0.003 + 0.0075 + 0.03;
        assert!((cost - expected).abs() < 1e-10);
    }

    #[test]
    fn test_stream_event_parses_server_tool_use_and_citations() {
        // content_block_start for a server-side web search — must parse into
        // ServerToolUse (not fail and not become a client ToolUse).
        let start: AnthropicStreamEvent = serde_json::from_str(
            r#"{"type":"content_block_start","index":1,"content_block":{"type":"server_tool_use","id":"srvtoolu_1","name":"web_search","input":{}}}"#,
        )
        .unwrap();
        match start {
            AnthropicStreamEvent::ContentBlockStart { content_block, .. } => {
                assert!(matches!(
                    content_block,
                    AnthropicContentBlock::ServerToolUse { .. }
                ));
            }
            other => panic!("unexpected event: {:?}", other),
        }

        // web_search_tool_result block start — extra fields must be tolerated.
        let result: AnthropicStreamEvent = serde_json::from_str(
            r#"{"type":"content_block_start","index":2,"content_block":{"type":"web_search_tool_result","tool_use_id":"srvtoolu_1","content":[{"type":"web_search_result","url":"https://example.com","title":"t"}]}}"#,
        )
        .unwrap();
        match result {
            AnthropicStreamEvent::ContentBlockStart { content_block, .. } => {
                assert!(matches!(
                    content_block,
                    AnthropicContentBlock::WebSearchToolResult {}
                ));
            }
            other => panic!("unexpected event: {:?}", other),
        }

        // citations_delta on a text block — must parse into CitationsDelta.
        let citation: AnthropicStreamEvent = serde_json::from_str(
            r#"{"type":"content_block_delta","index":3,"delta":{"type":"citations_delta","citation":{"type":"web_search_result_location","url":"https://example.com"}}}"#,
        )
        .unwrap();
        match citation {
            AnthropicStreamEvent::ContentBlockDelta { delta, .. } => {
                assert!(matches!(delta, AnthropicDelta::CitationsDelta {}));
            }
            other => panic!("unexpected event: {:?}", other),
        }

        // message_delta usage carrying server_tool_use must round-trip the count.
        let md: AnthropicStreamEvent = serde_json::from_str(
            r#"{"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":42,"server_tool_use":{"web_search_requests":2}}}"#,
        )
        .unwrap();
        match md {
            AnthropicStreamEvent::MessageDelta { usage, .. } => {
                let u = usage.unwrap();
                assert_eq!(u.server_tool_use.unwrap().web_search_requests, 2);
            }
            other => panic!("unexpected event: {:?}", other),
        }
    }

    #[test]
    fn test_translate_response_skips_server_tool_blocks() {
        let resp = AnthropicResponse {
            id: "msg_ws".to_string(),
            response_type: "message".to_string(),
            model: "claude-sonnet-4-6".to_string(),
            role: "assistant".to_string(),
            content: vec![
                AnthropicContentBlock::Text {
                    text: "Checking. ".to_string(),
                },
                AnthropicContentBlock::ServerToolUse {
                    id: "srvtoolu_1".to_string(),
                    name: "web_search".to_string(),
                },
                AnthropicContentBlock::WebSearchToolResult {},
                AnthropicContentBlock::Text {
                    text: "It's 75F in NYC.".to_string(),
                },
            ],
            stop_reason: Some("end_turn".to_string()),
            usage: AnthropicUsage {
                input_tokens: 10,
                output_tokens: 5,
                cache_creation_input_tokens: 0,
                cache_read_input_tokens: 0,
                server_tool_use: None,
            },
        };

        let openai = translate_response(&resp, "omi-sonnet");
        let msg = &openai.choices[0].message;
        assert_eq!(msg.content.as_deref(), Some("Checking. It's 75F in NYC."));
        // Server tool blocks must NOT surface as client tool_calls.
        assert!(msg.tool_calls.is_none());
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
        // system is Option<serde_json::Value> — compare via JSON serialization
        // to avoid type mismatch with AnthropicSystemContentBlock.
        let json = serde_json::to_value(&result).unwrap();
        assert_eq!(
            json["system"],
            json!([{
                "type": "text",
                "text": "You are helpful.",
                "cache_control": {"type": "ephemeral", "ttl": "1h"}
            }])
        );
        assert_eq!(result.messages.len(), 1); // only user message, system extracted
        assert_eq!(result.messages[0].role, "user");
        assert_eq!(result.max_tokens, 1024);
        assert_eq!(result.temperature, Some(0.7));
        assert!(!result.stream);
    }

    #[test]
    fn test_translate_request_caches_latest_user_message() {
        // The latest user message gets an ephemeral cache_control breakpoint so
        // the conversation prefix is cached across tool-loop round-trips. A
        // plain-string user content is promoted to a cached text block.
        let req = ChatCompletionRequest {
            model: "omi-sonnet".to_string(),
            messages: vec![ChatMessage {
                role: "user".to_string(),
                content: Some(json!("What did I do today?")),
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
        let last = result.messages.last().expect("a user message");
        assert_eq!(last.role, "user");
        let blocks = last.content.as_array().expect("content promoted to blocks");
        let final_block = blocks.last().expect("at least one block");
        assert_eq!(final_block["text"], "What did I do today?");
        assert_eq!(final_block["cache_control"]["type"], "ephemeral");
    }

    #[test]
    fn test_translate_request_caches_tool_result_turn() {
        // During a tool-use loop the final message is a tool result (Anthropic
        // `user` role with a tool_result block). The breakpoint must land on it
        // so each intra-turn request reads the cached prefix.
        let req = ChatCompletionRequest {
            model: "omi-sonnet".to_string(),
            messages: vec![
                ChatMessage {
                    role: "user".to_string(),
                    content: Some(json!("run it")),
                    name: None,
                    tool_calls: None,
                    tool_call_id: None,
                },
                ChatMessage {
                    role: "tool".to_string(),
                    content: Some(json!("42 rows")),
                    name: None,
                    tool_calls: None,
                    tool_call_id: Some("call_1".to_string()),
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
        let last = result.messages.last().expect("tool result message");
        assert_eq!(last.role, "user");
        let blocks = last.content.as_array().expect("tool_result blocks");
        let final_block = blocks.last().expect("at least one block");
        assert_eq!(final_block["type"], "tool_result");
        assert_eq!(final_block["cache_control"]["type"], "ephemeral");
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
        assert_eq!(result.messages[0].role, "user");
    }

    #[test]
    fn test_translate_request_system_prompt_uses_cache_control_blocks() {
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
            temperature: None,
            max_tokens: None,
            max_completion_tokens: None,
            tools: None,
            tool_choice: None,
        };

        let result = translate_request(&req, "claude-sonnet-4-6").unwrap();
        let json = serde_json::to_value(&result).unwrap();

        assert_eq!(
            json["system"],
            json!([{
                "type": "text",
                "text": "You are helpful.",
                "cache_control": {"type": "ephemeral", "ttl": "1h"}
            }])
        );
    }

    #[test]
    fn test_translate_request_splits_kernel_context_plan_for_ptt_escalation() {
        let req = ChatCompletionRequest {
            model: "omi-sonnet".to_string(),
            messages: vec![
                ChatMessage {
                    role: "system".to_string(),
                    content: Some(json!(
                        "You are Omi, a knowledgeable assistant.\n\n\
                         [Kernel Conversation Semantic Policy version=conversation-semantic-policy@1]\n\
                         Stable instructions.\n\
                         [Kernel Conversation Context Plan id=sha256:plan retained=2-65 omitted=1 strategy=truncated]\n\
                         Dynamic journal context."
                    )),
                    name: None,
                    tool_calls: None,
                    tool_call_id: None,
                },
                ChatMessage {
                    role: "user".to_string(),
                    content: Some(json!("Continue the spoken answer.")),
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
        let system = result.system.expect("system blocks");
        assert_eq!(
            system,
            json!([
                {
                    "type": "text",
                    "text": "You are Omi, a knowledgeable assistant.\n\n[Kernel Conversation Semantic Policy version=conversation-semantic-policy@1]\nStable instructions.\n",
                    "cache_control": {"type": "ephemeral", "ttl": "1h"}
                },
                {
                    "type": "text",
                    "text": "[Kernel Conversation Context Plan id=sha256:plan retained=2-65 omitted=1 strategy=truncated]\nDynamic journal context."
                }
            ])
        );
    }

    #[test]
    fn test_translate_request_without_system_prompt_omits_system() {
        let req = ChatCompletionRequest {
            model: "omi-sonnet".to_string(),
            messages: vec![ChatMessage {
                role: "user".to_string(),
                content: Some(json!("Hello")),
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
        let json = serde_json::to_value(&result).unwrap();

        assert!(result.system.is_none());
        assert!(json.get("system").is_none());
    }

    #[test]
    fn test_translate_request_empty_system_prompt_omits_system() {
        // Empty or whitespace-only system prompts must NOT be sent as cached blocks
        // (Anthropic rejects empty cached text blocks with 400).
        for content in [Some(json!("")), Some(json!("   ")), None] {
            let req = ChatCompletionRequest {
                model: "omi-sonnet".to_string(),
                messages: vec![
                    ChatMessage {
                        role: "system".to_string(),
                        content: content.clone(),
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
                temperature: None,
                max_tokens: None,
                max_completion_tokens: None,
                tools: None,
                tool_choice: None,
            };

            let result = translate_request(&req, "claude-sonnet-4-6").unwrap();
            assert!(
                result.system.is_none(),
                "empty/whitespace system prompt must omit system field, got: {:?}",
                result.system
            );
        }
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

        let result = translate_request_inner(&req, "claude-sonnet-4-6", true).unwrap();
        let tools = result.tools.unwrap();
        // Keep ordinary agentic calls on their normal incremental streaming
        // path; the server-side search tool is added only when retrieval
        // policy requires fresh public information.
        assert_eq!(tools.len(), 1);
        let custom = serde_json::to_value(&tools[0]).unwrap();
        assert_eq!(custom["name"], "get_weather");
        assert_eq!(custom["description"], "Get weather for a location");
        assert!(custom.get("input_schema").is_some());
        assert!(!result.requires_public_web);
    }

    #[test]
    fn test_translate_request_web_search_disabled() {
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
                    description: None,
                    parameters: None,
                },
            }]),
            tool_choice: None,
        };

        let result = translate_request_inner(&req, "claude-sonnet-4-6", false).unwrap();
        let tools = result.tools.unwrap();
        assert_eq!(tools.len(), 1);
        let only = serde_json::to_value(&tools[0]).unwrap();
        assert_eq!(only["name"], "get_weather");
    }

    #[test]
    fn test_translate_request_forces_required_web_search_without_client_tools() {
        let req = test_request(vec![
            user_message("I'm working on humanpost.co now"),
            assistant_message("Is HumanPost separate from Vost or part of it?"),
            user_message("look it up"),
        ]);

        let result = translate_request_inner(&req, "claude-sonnet-4-6", true).unwrap();
        let tools = result.tools.unwrap();
        assert_eq!(tools.len(), 1);
        assert_eq!(
            serde_json::to_value(&tools[0]).unwrap()["name"],
            "web_search"
        );
        assert_eq!(result.tool_choice, Some(json!({"type": "auto"})));
        let latest = result.messages.last().unwrap().content.to_string();
        assert!(latest.contains("Public web search is required"));
        assert!(latest.contains("look it up"));
    }

    #[test]
    fn test_translate_request_forces_web_search_for_location_qualified_weather() {
        // This is the same gateway request shape used by both the main
        // pi-mono session and default delegated pi-mono child sessions. The
        // server-side tool avoids giving either process a credential directly.
        let mut req = test_request(vec![user_message("What's the weather in NYC right now?")]);
        req.tools = Some(vec![ToolDefinition {
            tool_type: "function".to_string(),
            function: FunctionDefinition {
                name: "search_memories".to_string(),
                description: Some("Search Omi memories".to_string()),
                parameters: None,
            },
        }]);
        // A client may have requested one of its own functions, but a fresh
        // public lookup must retain a provider-compatible automatic choice so
        // the server-side web tool can run before any client tool.
        req.tool_choice = Some(json!({
            "type": "function",
            "function": {"name": "search_memories"}
        }));

        let result = translate_request_inner(&req, "claude-sonnet-4-6", true).unwrap();
        let tools = result.tools.unwrap();
        assert_eq!(
            serde_json::to_value(&tools[0]).unwrap()["name"],
            "web_search"
        );
        assert_eq!(
            serde_json::to_value(&tools[1]).unwrap()["name"],
            "search_memories"
        );
        assert_eq!(result.tool_choice, Some(json!({"type": "auto"})));
        assert!(result.requires_public_web);
        assert!(result
            .messages
            .last()
            .unwrap()
            .content
            .to_string()
            .contains("Public web search is required"));
    }

    #[test]
    fn test_pause_turn_continuation_preserves_raw_assistant_content_and_tools() {
        let req = test_request(vec![user_message(
            "Search the web for current weather in NYC",
        )]);
        let mut continuation = translate_request_inner(&req, "claude-sonnet-4-6", true).unwrap();
        let original_tools = serde_json::to_value(&continuation.tools).unwrap();
        let paused_content = json!([
            {
                "type": "server_tool_use",
                "id": "srvtoolu_123",
                "name": "web_search",
                "input": {"query": "NYC weather"}
            },
            {
                "type": "web_search_tool_result",
                "tool_use_id": "srvtoolu_123",
                "content": [{"type": "web_search_result", "title": "Weather"}]
            }
        ]);

        append_pause_turn_continuation(&mut continuation, paused_content.clone());

        assert_eq!(continuation.messages.last().unwrap().role, "assistant");
        assert_eq!(
            continuation.messages.last().unwrap().content,
            paused_content
        );
        assert_eq!(
            serde_json::to_value(&continuation.tools).unwrap(),
            original_tools
        );
        assert!(continuation.requires_public_web);
    }

    #[test]
    fn test_pause_turn_server_tool_response_decodes_and_preserves_raw_content() {
        let paused_content = json!([
            {
                "type": "server_tool_use",
                "id": "srvtoolu_123",
                "name": "web_search",
                "input": {"query": "NYC weather"}
            },
            {
                "type": "web_search_tool_result",
                "tool_use_id": "srvtoolu_123",
                "content": [{"type": "web_search_result", "title": "Weather"}]
            }
        ]);
        let raw_response = json!({
            "id": "msg_123",
            "type": "message",
            "model": "claude-sonnet-4-6",
            "role": "assistant",
            "content": paused_content,
            "stop_reason": "pause_turn",
            "usage": {"input_tokens": 12, "output_tokens": 4}
        });

        let response: AnthropicResponse = serde_json::from_value(raw_response.clone())
            .expect("pause_turn response with Anthropic server blocks must decode");
        assert_eq!(response.stop_reason.as_deref(), Some("pause_turn"));
        assert_eq!(response.content.len(), 2);

        let req = test_request(vec![user_message(
            "Search the web for current weather in NYC",
        )]);
        let mut continuation = translate_request_inner(&req, "claude-sonnet-4-6", true).unwrap();
        append_pause_turn_continuation(&mut continuation, raw_response["content"].clone());
        assert_eq!(
            continuation.messages.last().unwrap().content,
            raw_response["content"]
        );
    }

    #[test]
    fn test_translate_request_required_web_search_fails_closed_when_disabled() {
        let req = test_request(vec![user_message("Search the web for HumanPost")]);
        let error = translate_request_inner(&req, "claude-sonnet-4-6", false).unwrap_err();
        assert!(error.contains("required public web search is unavailable"));
    }

    #[test]
    fn test_translate_request_private_lookup_excludes_server_web_search() {
        let mut req = test_request(vec![user_message("Search my conversations for HumanPost")]);
        req.tools = Some(vec![ToolDefinition {
            tool_type: "function".to_string(),
            function: FunctionDefinition {
                name: "search_conversations".to_string(),
                description: Some("Search private conversations".to_string()),
                parameters: None,
            },
        }]);

        let result = translate_request_inner(&req, "claude-sonnet-4-6", true).unwrap();
        let tools = result.tools.unwrap();
        assert_eq!(tools.len(), 1);
        assert_eq!(
            serde_json::to_value(&tools[0]).unwrap()["name"],
            "search_conversations"
        );
        assert!(result.tool_choice.is_none());
    }

    #[test]
    fn test_translate_request_no_web_search_on_haiku() {
        // web_search_20260209 is unsupported on haiku — never inject there.
        let req = ChatCompletionRequest {
            model: "claude-haiku-4-5".to_string(),
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
                    name: "some_tool".to_string(),
                    description: None,
                    parameters: None,
                },
            }]),
            tool_choice: None,
        };
        let result = translate_request_inner(&req, "claude-haiku-4-5", true).unwrap();
        let tools = result.tools.unwrap();
        assert_eq!(tools.len(), 1);
        assert_eq!(
            serde_json::to_value(&tools[0]).unwrap()["name"],
            "some_tool"
        );
    }

    #[test]
    fn test_map_stop_reason_pause_turn_terminates() {
        assert_eq!(
            map_stop_reason(Some("pause_turn")),
            Some("stop".to_string())
        );
    }

    #[test]
    fn test_merge_stream_usage_prefers_final_nonzero() {
        let initial = AnthropicUsage {
            input_tokens: 100,
            output_tokens: 0,
            cache_creation_input_tokens: 50,
            cache_read_input_tokens: 20,
            server_tool_use: None,
        };
        // Web-search turn: final usage carries cumulative input + search count.
        let fin = AnthropicUsage {
            input_tokens: 5000,
            output_tokens: 300,
            cache_creation_input_tokens: 0,
            cache_read_input_tokens: 0,
            server_tool_use: Some(AnthropicServerToolUsage {
                web_search_requests: 2,
            }),
        };
        let merged = merge_stream_usage(Some(&initial), &fin);
        assert_eq!(merged.input_tokens, 5000); // final wins when nonzero
        assert_eq!(merged.output_tokens, 300);
        assert_eq!(merged.cache_creation_input_tokens, 50); // fallback to initial
        assert_eq!(merged.cache_read_input_tokens, 20); // fallback to initial
        assert_eq!(merged.server_tool_use.unwrap().web_search_requests, 2);

        // Plain turn: final has only output — initial fields survive.
        let fin_plain = AnthropicUsage {
            input_tokens: 0,
            output_tokens: 40,
            cache_creation_input_tokens: 0,
            cache_read_input_tokens: 0,
            server_tool_use: None,
        };
        let merged_plain = merge_stream_usage(Some(&initial), &fin_plain);
        assert_eq!(merged_plain.input_tokens, 100);
        assert_eq!(merged_plain.cache_read_input_tokens, 20);
        assert!(merged_plain.server_tool_use.is_none());
    }

    #[test]
    fn test_translate_request_no_web_search_without_client_tools() {
        // Tool-less requests (router classifier, summaries) must stay tool-free
        // even with web search enabled.
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
        let result = translate_request_inner(&req, "claude-sonnet-4-6", true).unwrap();
        assert!(result.tools.is_none());

        // Same for an explicitly empty tools array.
        let req_empty = ChatCompletionRequest {
            tools: Some(vec![]),
            ..req
        };
        let result = translate_request_inner(&req_empty, "claude-sonnet-4-6", true).unwrap();
        assert_eq!(result.tools.unwrap().len(), 0);
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
                server_tool_use: None,
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
        assert_eq!(openai.choices[0].finish_reason, Some("stop".to_string()));
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
                server_tool_use: None,
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
    fn test_drain_sse_events_splits_on_blank_line() {
        let mut buffer = b"event: a\ndata: {\"x\":1}\n\ndata: {\"y\":2}\n\ndata: par".to_vec();
        let events = drain_sse_events(&mut buffer);

        assert_eq!(events.len(), 2);
        assert!(events[0].contains("\"x\":1"));
        assert!(events[1].contains("\"y\":2"));
        assert_eq!(buffer, b"data: par");
    }

    #[test]
    fn test_drain_sse_events_preserves_char_split_across_chunks() {
        // "—" (U+2014) is 3 bytes; a network chunk can land in the middle of it.
        let event = "data: {\"text\":\"a—b\"}\n\n".as_bytes().to_vec();
        let split = 17; // inside the em dash's 3 bytes (16..19)
        let mut buffer = Vec::new();

        buffer.extend_from_slice(&event[..split]);
        assert!(drain_sse_events(&mut buffer).is_empty());

        buffer.extend_from_slice(&event[split..]);
        let events = drain_sse_events(&mut buffer);

        assert_eq!(events.len(), 1);
        assert!(events[0].contains("a—b"), "got {}", events[0]);
        assert!(!events[0].contains('\u{fffd}'));
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
        assert!(
            result.tools.is_none(),
            "tools should be stripped when tool_choice is 'none'"
        );
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
        assert!(
            result.is_err(),
            "unknown string tool_choice must return Err"
        );
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
        assert!(
            result.is_err(),
            "object without function.name must return Err"
        );
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
        assert!(
            result.is_err(),
            "non-function tool_choice object must return Err"
        );
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
        assert_eq!(
            result.max_tokens, 0,
            "max_tokens=0 should be respected (capped at min)"
        );
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
        assert_eq!(
            result.max_tokens, MAX_TOKENS_CAP,
            "max_tokens at exactly the cap should be preserved"
        );
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
        let tool_calls = chunk["choices"][0]["delta"]["tool_calls"]
            .as_array()
            .unwrap();
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
        let chunk = make_chunk(
            "id-2",
            2000,
            "omi-sonnet",
            delta,
            Some("stop".to_string()),
            None,
        );
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
            prompt_tokens_details: None,
        };
        let chunk = make_chunk(
            "id-3",
            3000,
            "omi-sonnet",
            delta,
            Some("stop".to_string()),
            Some(usage),
        );
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
