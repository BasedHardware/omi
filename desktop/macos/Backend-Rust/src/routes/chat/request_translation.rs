use serde_json::json;

use crate::fallback::{record_fallback, FallbackOutcome};
use crate::models::chat_completions::*;
use crate::routes::retrieval_policy::{
    caller_disabled_tools, prepend_latest_user_instruction, retrieval_policy, RetrievalSource,
    REQUIRED_WEB_SEARCH_INSTRUCTION,
};

/// Default max_tokens when client doesn't specify one.
pub(super) const DEFAULT_MAX_TOKENS: u64 = 8192;

/// Maximum allowed max_tokens to prevent abuse.
pub(super) const MAX_TOKENS_CAP: u64 = 16384;
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
pub(super) fn web_search_enabled() -> bool {
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

pub(super) fn compute_cost(usage: &AnthropicUsage, upstream_model: &str) -> f64 {
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
pub(super) fn translate_request(
    req: &ChatCompletionRequest,
    upstream_model: &str,
) -> Result<AnthropicRequest, String> {
    translate_request_inner(req, upstream_model, web_search_enabled())
}

pub(super) fn translate_request_inner(
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
    let wants_web_search =
        policy.requires(RetrievalSource::PublicWeb) && !caller_disabled_tools(req);
    if wants_web_search && !web_search_supported && policy.web_requirement_is_explicit() {
        return Err(
            "required public web search is unavailable for this model or deployment".to_string(),
        );
    }
    // A heuristic freshness/anaphoric guess is not a user demand. On a route
    // without web search (haiku, or the kill switch) answer the turn from model
    // knowledge instead of failing it — the forced-search instruction below also
    // bans private context, which would be wrong for a turn we merely guessed at.
    let force_web_search = wants_web_search && web_search_supported;
    if wants_web_search && !web_search_supported {
        record_fallback(
            "chat_retrieval",
            "forced_web_search",
            "model_knowledge",
            "capability_mismatch",
            FallbackOutcome::Degraded,
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
        // Use the typed system block produced by cached_system_block() above.
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

const OMI_CONTEXT_CACHE_BOUNDARY: &str = "<!-- OMI_CONTEXT_CACHE_V1 ";

/// Split the producer-owned desktop context-plan boundary. The static kernel
/// policy gets the cache breakpoint; the marker and any dynamic context after
/// it remain uncached so changed conversation context cannot poison the stable
/// cache. Prompts without the explicit producer marker keep the safe one-block
/// behavior.
fn cached_system_block(text: String) -> serde_json::Value {
    let Some(marker_offset) = text.find(OMI_CONTEXT_CACHE_BOUNDARY) else {
        return json!([{
            "type": "text",
            "text": text,
            "cache_control": ephemeral_cache_control()
        }]);
    };
    let (stable, dynamic) = text.split_at(marker_offset);
    if stable.trim().is_empty() {
        return json!([{
            "type": "text",
            "text": text,
            "cache_control": ephemeral_cache_control()
        }]);
    }
    json!([
        {
            "type": "text",
            "text": stable.trim_end(),
            "cache_control": ephemeral_cache_control()
        },
        {
            "type": "text",
            "text": dynamic
        }
    ])
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
pub(super) fn translate_tool_choice(
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

pub(super) fn extract_text_content(content: &Option<serde_json::Value>) -> String {
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

pub(super) fn translate_response(
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
