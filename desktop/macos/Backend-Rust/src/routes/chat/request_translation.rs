use serde_json::{json, Value};

use crate::models::chat_completions::*;

/// Default max_tokens when client doesn't specify one.
pub(super) const DEFAULT_MAX_TOKENS: u64 = 8192;

/// Maximum allowed max_tokens to prevent abuse.
pub(super) const MAX_TOKENS_CAP: u64 = 16384;

/// Floor for max_tokens on adaptive-thinking turns: `max_tokens` caps the
/// *total* output (thinking + answer), so a quality turn needs headroom for
/// the reasoning tokens or a hard question ends mid-answer.
pub(super) const THINKING_MIN_MAX_TOKENS: u64 = 16384;

/// Cap for adaptive-thinking turns. Higher than MAX_TOKENS_CAP because the
/// thinking budget shares the same ceiling; only streamed requests can use it
/// (non-streaming stays at MAX_TOKENS_CAP to avoid HTTP timeouts).
pub(super) const THINKING_MAX_TOKENS_CAP: u64 = 32768;

/// Per-turn reasoning-effort directive resolved from the
/// `x-omi-reasoning-effort` header (authoritative, written by the desktop app
/// per turn) or the OpenAI-compatible `reasoning_effort` body field.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub(super) enum ReasoningEffort {
    /// No directive — keep the historical behavior (no thinking field).
    #[default]
    Unspecified,
    /// Speed lane (PTT/voice): no thinking, low output effort.
    Fast,
    /// Quality lane (typed chat): adaptive thinking — the model itself decides
    /// how much reasoning each question deserves, including "think longer"
    /// requests embedded in the prompt.
    Adaptive,
}

impl ReasoningEffort {
    pub(super) fn parse(raw: &str) -> Option<Self> {
        match raw.trim().to_ascii_lowercase().as_str() {
            "fast" | "none" | "off" | "minimal" | "low" => Some(Self::Fast),
            "adaptive" | "quality" | "auto" | "medium" | "high" => Some(Self::Adaptive),
            _ => None,
        }
    }
}
/// Anthropic's direct server-side web search tool. Executed entirely upstream
/// by Anthropic — the OpenAI-side client never sees or executes it.
///
/// Keep this on the basic-search version while the gateway's response parser
/// owns only the direct `server_tool_use` + `web_search_tool_result` contract.
/// `web_search_20260209` defaults to code-execution callers and cannot safely
/// be selected as the direct tool this compatibility route requires.
const WEB_SEARCH_TOOL_TYPE: &str = "web_search_20250305";

/// Max web searches per request (matches the Python backend's agentic chat).
const WEB_SEARCH_MAX_USES: u32 = 5;

/// Anthropic web search pricing: $10 per 1,000 searches.
const WEB_SEARCH_COST_PER_REQUEST: f64 = 10.0 / 1_000.0;

// The agent runtime owns positive public-web routing. The gateway remains the
// authority that prevents an explicitly private or no-web turn from receiving
// the external server tool, including after a client tool result is replayed.
const EXPLICIT_WEB_REQUESTS: &[&str] = &[
    "search the web",
    "search web",
    "search the internet",
    "search online",
    "look it up online",
    "look this up online",
    "look that up online",
    "find it online",
    "find this online",
    "find that online",
    "google it",
    "google this",
    "google that",
    "browse the web",
    "web search",
    "internet search",
];
const EXPLICIT_WEB_PROHIBITIONS: &[&str] = &[
    "don't call web search",
    "do not call web search",
    "don't call the web search",
    "do not call the web search",
    "don't call internet search",
    "do not call internet search",
    "don't call the internet search",
    "do not call the internet search",
    "don't use web search",
    "do not use web search",
    "don't use the web search",
    "do not use the web search",
    "don't use internet search",
    "do not use internet search",
    "don't use the internet search",
    "do not use the internet search",
    "don't search the web",
    "do not search the web",
    "don't search the internet",
    "do not search the internet",
    "without web search",
];
const EXPLICIT_PRIVATE_CONTEXT: &[&str] = &[
    "my conversations",
    "our conversations",
    "my memories",
    "your memory of me",
    "my screen history",
    "my screen activity",
    "my calendar",
    "your calendar",
    "my email",
    "your email",
    "my files",
    "your files",
    "my tasks",
    "your tasks",
    "my action items",
    "my notes",
    "your notes",
    "what did i say",
    "what have i said",
    "what did i do",
    "when did i",
    "what was i doing",
    "what do you remember about me",
];
const CURRENT_USER_MESSAGE_DELIMITER: &str = "\n# User Message\n";

fn web_search_tool_def() -> AnthropicToolDef {
    AnthropicToolDef::Server(json!({
        "type": WEB_SEARCH_TOOL_TYPE,
        "name": "web_search",
        "max_uses": WEB_SEARCH_MAX_USES,
        // Make the parser contract explicit. The basic tool supports direct
        // execution and returns the server-tool blocks handled below.
        "allowed_callers": ["direct"],
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
    translate_request_inner(
        req,
        upstream_model,
        web_search_enabled(),
        ReasoningEffort::Unspecified,
    )
}

pub(super) fn translate_request_inner(
    req: &ChatCompletionRequest,
    upstream_model: &str,
    enable_web_search: bool,
    reasoning_effort: ReasoningEffort,
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

    // Web search is a normal tool on supported public agentic turns, keeping
    // streaming incremental rather than pre-routing into a buffered path. The
    // current user instruction is still a hard privacy boundary: an explicit
    // private or no-web turn must not receive this external server tool, even
    // when this request resumes after a client tool result.
    let web_search_supported = enable_web_search && !upstream_model.starts_with("claude-haiku");
    let client_tools = req.tools.as_deref().unwrap_or(&[]);
    let public_web_prohibited = public_web_is_prohibited(&req.messages);
    let inject_web_search =
        web_search_supported && !public_web_prohibited && !client_tools.is_empty();
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

    tracing::info!(
        event = "retrieval_policy",
        web_search_exposed = inject_web_search,
        public_web_prohibited,
        "chat_retrieval_policy"
    );

    // Effort → Anthropic knobs. Haiku (router/synthesis) never thinks — the
    // effort/output_config surface isn't supported there.
    //
    // Tool-loop continuations must NOT think: a continuation request replays
    // the assistant tool_use turn, but the OpenAI-format history cannot carry
    // Anthropic thinking/signature blocks, and a thinking-enabled request
    // whose assistant tool_use turn lacks its thinking block is rejected
    // upstream. With thinking omitted the same history is valid, so thinking
    // applies only to the first model call of a user turn (the request whose
    // final non-system message is the user's).
    let model_supports_effort = !upstream_model.starts_with("claude-haiku");
    let tail_is_user = req
        .messages
        .iter()
        .rev()
        .find(|m| m.role != "system" && m.role != "developer")
        .is_some_and(|m| m.role == "user");
    let use_adaptive_thinking =
        reasoning_effort == ReasoningEffort::Adaptive && model_supports_effort && tail_is_user;

    let max_tokens = if use_adaptive_thinking {
        let cap = if req.stream {
            THINKING_MAX_TOKENS_CAP
        } else {
            MAX_TOKENS_CAP
        };
        req.max_completion_tokens
            .or(req.max_tokens)
            .unwrap_or(DEFAULT_MAX_TOKENS)
            .max(THINKING_MIN_MAX_TOKENS)
            .min(cap)
    } else {
        req.max_completion_tokens
            .or(req.max_tokens)
            .unwrap_or(DEFAULT_MAX_TOKENS)
            .min(MAX_TOKENS_CAP)
    };

    // Translate tool_choice from OpenAI format to Anthropic format.
    // When tool_choice is "none", strip tools entirely — Anthropic has no "none"
    // and would auto-use tools if they're present in the request. Otherwise the
    // client's choice passes through; with no explicit choice Anthropic defaults
    // to `auto`, allowing the model to choose web_search when appropriate.
    let is_tool_choice_none = matches!(
        &req.tool_choice,
        Some(serde_json::Value::String(s)) if s == "none"
    );
    let anthropic_tool_choice = translate_tool_choice(&req.tool_choice)?;

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

    // Adaptive thinking lets the model itself pick its reasoning depth per
    // question (Sonnet 4.6+). Thinking rejects a custom temperature, so drop
    // it on quality turns. Fast (PTT) turns keep thinking off and pin output
    // effort low so voice answers stay quick and terse.
    let thinking = use_adaptive_thinking.then(|| json!({ "type": "adaptive" }));
    let output_config = (reasoning_effort == ReasoningEffort::Fast && model_supports_effort)
        .then(|| json!({ "effort": "low" }));
    let temperature = if use_adaptive_thinking {
        None
    } else {
        req.temperature
    };

    Ok(AnthropicRequest {
        model: upstream_model.to_string(),
        max_tokens,
        messages: anthropic_messages,
        // Use the typed system block produced by cached_system_block() above.
        system,
        temperature,
        stream: req.stream,
        thinking,
        output_config,
        tools: if is_tool_choice_none {
            None
        } else {
            anthropic_tools
        },
        tool_choice: anthropic_tool_choice,
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

fn public_web_is_prohibited(messages: &[ChatMessage]) -> bool {
    // A tool-result continuation ends in `tool`, but must retain the privacy
    // policy selected by the fresh user instruction that began the turn.
    let Some(latest_user) = messages.iter().rev().find(|message| message.role == "user") else {
        return false;
    };
    let rendered_prompt = extract_text_content(&latest_user.content);
    let instruction = rendered_prompt
        .rsplit_once(CURRENT_USER_MESSAGE_DELIMITER)
        .map_or(rendered_prompt.as_str(), |(_, current)| current);
    let instruction = strip_public_web_routing_instruction(instruction);
    let normalized = normalize_policy_text(instruction);
    if normalized.is_empty() {
        return false;
    }

    let explicitly_mentions_web = contains_policy_phrase(&normalized, EXPLICIT_WEB_REQUESTS);
    let explicit_private_context = contains_policy_phrase(&normalized, EXPLICIT_PRIVATE_CONTEXT);
    (explicitly_mentions_web && explicitly_prohibits_public_web(&normalized))
        || (explicit_private_context && !explicitly_mentions_web)
}

fn strip_public_web_routing_instruction(text: &str) -> &str {
    const OPEN: &str = "<omi_retrieval_policy>";
    const CLOSE: &str = "</omi_retrieval_policy>";

    let trimmed = text.trim_start();
    if !trimmed.starts_with(OPEN) {
        return text;
    }
    trimmed
        .split_once(CLOSE)
        .map_or(text, |(_, remainder)| remainder.trim_start())
}

fn normalize_policy_text(text: &str) -> String {
    text.trim()
        .trim_matches(|ch: char| !ch.is_alphanumeric())
        .replace(['\u{2018}', '\u{2019}'], "'")
        .to_ascii_lowercase()
}

fn contains_policy_phrase(text: &str, phrases: &[&str]) -> bool {
    phrases.iter().any(|phrase| text.contains(phrase))
}

fn explicitly_prohibits_public_web(text: &str) -> bool {
    EXPLICIT_WEB_PROHIBITIONS.iter().any(|phrase| {
        text.match_indices(phrase).any(|(start, _)| {
            let suffix = text[start + phrase.len()..].trim_start();
            !["result", "results"].iter().any(|noun| {
                suffix
                    .strip_prefix(noun)
                    .is_some_and(|tail| tail.chars().next().is_none_or(|ch| !ch.is_alphanumeric()))
            })
        })
    })
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
            AnthropicContentBlock::Thinking { .. } | AnthropicContentBlock::RedactedThinking {} => {
                // Reasoning blocks are never part of the OpenAI `content`
                // field — the answer text follows in its own text block.
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

pub(super) fn response_text_content(resp: &AnthropicResponse) -> Option<String> {
    let text = resp
        .content
        .iter()
        .filter_map(|block| match block {
            AnthropicContentBlock::Text { text } => Some(text.as_str()),
            AnthropicContentBlock::ToolUse { .. }
            | AnthropicContentBlock::ServerToolUse { .. }
            | AnthropicContentBlock::WebSearchToolResult {}
            | AnthropicContentBlock::Thinking { .. }
            | AnthropicContentBlock::RedactedThinking {} => None,
        })
        .collect::<Vec<_>>()
        .join("");

    (!text.is_empty()).then_some(text)
}

pub(super) fn should_record_web_search_fallback(
    req: &ChatCompletionRequest,
    web_search_supported: bool,
) -> bool {
    !web_search_supported
        && !public_web_is_prohibited(&req.messages)
        && req.tools.as_ref().is_some_and(|tools| !tools.is_empty())
}

pub(super) fn server_tool_available_from(tools: &Option<Vec<AnthropicToolDef>>) -> &'static str {
    if tools.as_ref().is_some_and(|defs| {
        defs.iter().any(|def| match def {
            AnthropicToolDef::Server(value) => value
                .get("name")
                .and_then(Value::as_str)
                .is_some_and(|name| name == "web_search"),
            AnthropicToolDef::Custom(_) => false,
        })
    }) {
        "anthropic_web_search"
    } else {
        "model_knowledge"
    }
}
