// Chat completions models — OpenAI-compatible request/response types
// for POST /v2/chat/completions. Translates between Anthropic Messages API
// and OpenAI chat completions format.

use serde::{Deserialize, Serialize};

// ── Request types (OpenAI-compatible inbound) ──────────────────────────────

#[derive(Debug, Clone, Deserialize)]
pub struct ChatCompletionRequest {
    pub model: String,
    pub messages: Vec<ChatMessage>,
    #[serde(default)]
    pub stream: bool,
    #[serde(default)]
    pub temperature: Option<f64>,
    #[serde(default)]
    pub max_tokens: Option<u64>,
    // OpenAI renamed `max_tokens` to `max_completion_tokens` for reasoning
    // models. Pi's openai-completions client sends this field instead of
    // `max_tokens`. Accept both and prefer `max_completion_tokens` when set.
    #[serde(default)]
    pub max_completion_tokens: Option<u64>,
    #[serde(default)]
    pub tools: Option<Vec<ToolDefinition>>,
    #[serde(default)]
    pub tool_choice: Option<serde_json::Value>,
    // OpenAI reasoning-effort knob. Accepted for compatibility with clients
    // that send it in the body; the desktop app sends the authoritative value
    // via the `x-omi-reasoning-effort` header (see routes/chat/route.rs).
    #[serde(default)]
    pub reasoning_effort: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ChatMessage {
    pub role: String,
    #[serde(default)]
    pub content: Option<serde_json::Value>,
    #[serde(default)]
    pub name: Option<String>,
    #[serde(default)]
    pub tool_calls: Option<Vec<ToolCall>>,
    #[serde(default)]
    pub tool_call_id: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ToolDefinition {
    #[serde(rename = "type")]
    pub tool_type: String,
    pub function: FunctionDefinition,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct FunctionDefinition {
    pub name: String,
    #[serde(default)]
    pub description: Option<String>,
    #[serde(default)]
    pub parameters: Option<serde_json::Value>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ToolCall {
    pub id: String,
    #[serde(rename = "type")]
    pub call_type: String,
    pub function: FunctionCall,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct FunctionCall {
    pub name: String,
    pub arguments: String,
}

// ── Response types (OpenAI-compatible outbound) ─────────────────────────────

#[derive(Debug, Clone, Serialize)]
pub struct ChatCompletionResponse {
    pub id: String,
    pub object: &'static str,
    pub created: i64,
    pub model: String,
    pub choices: Vec<Choice>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub usage: Option<Usage>,
}

#[derive(Debug, Clone, Serialize)]
pub struct Choice {
    pub index: u32,
    pub message: ResponseMessage,
    pub finish_reason: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ResponseMessage {
    pub role: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub content: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tool_calls: Option<Vec<ToolCall>>,
}

#[derive(Debug, Clone, Serialize)]
pub struct Usage {
    pub prompt_tokens: i64,
    pub completion_tokens: i64,
    pub total_tokens: i64,
    // OpenAI-standard cached-token reporting. Populated from Anthropic's
    // cache_read_input_tokens so prompt-cache hits propagate through pi-mono
    // (usage.cacheRead) to the Swift query trace. Omitted when zero.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub prompt_tokens_details: Option<PromptTokensDetails>,
}

#[derive(Debug, Clone, Serialize)]
pub struct PromptTokensDetails {
    pub cached_tokens: i64,
}

// ── Streaming chunk types ───────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize)]
pub struct ChatCompletionChunk {
    pub id: String,
    pub object: &'static str,
    pub created: i64,
    pub model: String,
    pub choices: Vec<ChunkChoice>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub usage: Option<Usage>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ChunkChoice {
    pub index: u32,
    pub delta: ChunkDelta,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub finish_reason: Option<String>,
}

#[derive(Debug, Clone, Default, Serialize)]
pub struct ChunkDelta {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub role: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub content: Option<String>,
    /// Streamed adaptive-thinking text (OpenAI-compatible reasoning field,
    /// as popularized by DeepSeek/OpenRouter). Clients that don't understand
    /// it ignore the field; the answer still arrives via `content`.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reasoning_content: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tool_calls: Option<Vec<ChunkToolCall>>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ChunkToolCall {
    pub index: u32,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none", rename = "type")]
    pub call_type: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub function: Option<ChunkFunctionCall>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ChunkFunctionCall {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub arguments: Option<String>,
}

// ── Anthropic API types (internal, for upstream translation) ────────────────

#[derive(Debug, Clone, Serialize)]
pub struct AnthropicRequest {
    pub model: String,
    pub max_tokens: u64,
    pub messages: Vec<AnthropicMessage>,
    /// System prompt as array-of-content-blocks with optional cache_control.
    /// Produced by `cached_system_block()` which handles sentinel splitting
    /// so volatile live context (dates, times) is excluded from the cached prefix.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub system: Option<serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub temperature: Option<f64>,
    pub stream: bool,
    /// Adaptive thinking config (`{"type": "adaptive"}`) — set on quality
    /// (typed-chat) turns so the model decides how much to reason per query.
    /// Omitted entirely on speed (PTT) turns.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub thinking: Option<serde_json::Value>,
    /// Output-level effort control (`{"effort": "low"}`) — set on speed (PTT)
    /// turns to keep voice answers fast and terse.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub output_config: Option<serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tools: Option<Vec<AnthropicToolDef>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tool_choice: Option<serde_json::Value>,
    /// Gateway-owned execution metadata. A public-web turn may use Anthropic's
    /// long-running server tool and therefore needs internal pause-turn
    /// continuation before an OpenAI-compatible response is emitted.
    #[serde(skip)]
    pub requires_public_web: bool,
}

/// A tool definition in an Anthropic request: either a client-executed custom
/// tool (translated from the OpenAI request) or an Anthropic server-side tool
/// (e.g. web_search) that Anthropic executes during generation without any
/// client round-trip.
#[derive(Debug, Clone, Serialize)]
#[serde(untagged)]
pub enum AnthropicToolDef {
    Custom(AnthropicTool),
    Server(serde_json::Value),
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AnthropicMessage {
    pub role: String,
    pub content: serde_json::Value,
}

/// Anthropic content block type (system prompt blocks are always "text").
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum AnthropicContentBlockType {
    Text,
}

/// Anthropic cache control type (currently only "ephemeral" is supported).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum AnthropicCacheControlType {
    Ephemeral,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct AnthropicSystemContentBlock {
    #[serde(rename = "type")]
    pub block_type: AnthropicContentBlockType,
    pub text: String,
    pub cache_control: AnthropicCacheControl,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct AnthropicCacheControl {
    #[serde(rename = "type")]
    pub cache_type: AnthropicCacheControlType,
}

#[derive(Debug, Clone, Serialize)]
pub struct AnthropicTool {
    pub name: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    pub input_schema: serde_json::Value,
}

#[derive(Debug, Clone, Deserialize)]
#[allow(dead_code)] // wire-format DTO: several fields are deserialized but not read
pub struct AnthropicResponse {
    pub id: String,
    #[serde(rename = "type")]
    pub response_type: String,
    pub model: String,
    pub role: String,
    pub content: Vec<AnthropicContentBlock>,
    pub stop_reason: Option<String>,
    pub usage: AnthropicUsage,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(tag = "type")]
pub enum AnthropicContentBlock {
    #[serde(rename = "text")]
    Text { text: String },
    #[serde(rename = "tool_use")]
    ToolUse {
        id: String,
        name: String,
        input: serde_json::Value,
    },
    /// Server-side tool invocation (e.g. web_search) — executed by Anthropic
    /// during generation. Never surfaced to the OpenAI client.
    #[serde(rename = "server_tool_use")]
    ServerToolUse {
        #[allow(dead_code)] // deserialized but not surfaced to the OpenAI client
        id: String,
        name: String,
    },
    /// Result of a server-side web search — consumed by the model upstream.
    /// Never surfaced to the OpenAI client.
    #[serde(rename = "web_search_tool_result")]
    WebSearchToolResult {},
    /// Adaptive-thinking reasoning block. Streamed thinking text is forwarded
    /// as OpenAI `reasoning_content` deltas; the non-streaming block is not
    /// included in the OpenAI `content` field.
    #[serde(rename = "thinking")]
    Thinking {
        #[serde(default)]
        #[allow(dead_code)] // deserialized but not surfaced in non-streaming translation
        thinking: String,
    },
    /// Redacted thinking — opaque; never surfaced.
    #[serde(rename = "redacted_thinking")]
    RedactedThinking {},
}

#[derive(Debug, Clone, Deserialize, Default)]
pub struct AnthropicUsage {
    #[serde(default)]
    pub input_tokens: i64,
    #[serde(default)]
    pub output_tokens: i64,
    #[serde(default)]
    pub cache_creation_input_tokens: i64,
    #[serde(default)]
    pub cache_read_input_tokens: i64,
    /// Server-side tool usage (web search request count) — billed per request,
    /// so it must survive into cost computation.
    #[serde(default)]
    pub server_tool_use: Option<AnthropicServerToolUsage>,
}

#[derive(Debug, Clone, Deserialize, Default)]
pub struct AnthropicServerToolUsage {
    #[serde(default)]
    pub web_search_requests: i64,
}

// ── Anthropic streaming event types ─────────────────────────────────────────

#[derive(Debug, Clone, Deserialize)]
#[serde(tag = "type")]
pub enum AnthropicStreamEvent {
    #[serde(rename = "message_start")]
    MessageStart { message: AnthropicStreamMessage },
    #[serde(rename = "content_block_start")]
    ContentBlockStart {
        index: usize,
        content_block: AnthropicContentBlock,
    },
    #[serde(rename = "content_block_delta")]
    ContentBlockDelta { index: usize, delta: AnthropicDelta },
    #[serde(rename = "content_block_stop")]
    ContentBlockStop {
        #[allow(dead_code)] // deserialized but not read
        index: usize,
    },
    #[serde(rename = "message_delta")]
    MessageDelta {
        delta: AnthropicMessageDelta,
        usage: Option<AnthropicUsage>,
    },
    #[serde(rename = "message_stop")]
    MessageStop {},
    #[serde(rename = "ping")]
    Ping {},
    #[serde(rename = "error")]
    Error { error: AnthropicStreamError },
}

#[derive(Debug, Clone, Deserialize)]
pub struct AnthropicStreamMessage {
    pub id: String,
    #[allow(dead_code)] // deserialized but not read
    pub model: String,
    #[serde(default)]
    pub usage: AnthropicUsage,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(tag = "type")]
pub enum AnthropicDelta {
    #[serde(rename = "text_delta")]
    TextDelta { text: String },
    #[serde(rename = "input_json_delta")]
    InputJsonDelta { partial_json: String },
    /// Citation metadata attached to text generated from web search results.
    /// Dropped in translation — the OpenAI chunk format has no citation slot.
    #[serde(rename = "citations_delta")]
    CitationsDelta {},
    /// Adaptive-thinking reasoning text — forwarded as OpenAI
    /// `reasoning_content` so clients that render reasoning can show it.
    #[serde(rename = "thinking_delta")]
    ThinkingDelta { thinking: String },
    /// Thinking-block integrity signature — internal to Anthropic; dropped.
    #[serde(rename = "signature_delta")]
    SignatureDelta {},
}

#[derive(Debug, Clone, Deserialize)]
pub struct AnthropicMessageDelta {
    pub stop_reason: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct AnthropicStreamError {
    pub message: String,
}

// ── Provider routing ────────────────────────────────────────────────────────

#[derive(Debug, Clone)]
pub struct ModelRoute {
    pub public_model: &'static str,
    pub upstream_model: &'static str,
}

/// Model allowlist — maps public model names to upstream provider models.
/// All models resolve to Claude 4.6 (sonnet/opus).
pub const MODEL_ROUTES: &[ModelRoute] = &[
    ModelRoute {
        public_model: "omi-sonnet",
        upstream_model: "claude-sonnet-4-6",
    },
    ModelRoute {
        public_model: "omi-opus",
        upstream_model: "claude-opus-4-6",
    },
    // Pass-through aliases used by onboarding chat and other app components
    ModelRoute {
        public_model: "claude-opus-4-6",
        upstream_model: "claude-opus-4-6",
    },
    ModelRoute {
        public_model: "claude-sonnet-4-6",
        upstream_model: "claude-sonnet-4-6",
    },
    // Legacy dated IDs — redirect to 4.6
    ModelRoute {
        public_model: "claude-opus-4-20250514",
        upstream_model: "claude-opus-4-6",
    },
    ModelRoute {
        public_model: "claude-sonnet-4-20250514",
        upstream_model: "claude-sonnet-4-6",
    },
    // Haiku 4.5 — used by the AgentPill router classifier and ModelQoS
    // synthesis paths. Without these entries every call 400s and the
    // floating-bar router silently falls back to chat, so agent pills never
    // spawn from natural-language prompts.
    ModelRoute {
        public_model: "claude-haiku-4-5-20251001",
        upstream_model: "claude-haiku-4-5",
    },
    ModelRoute {
        public_model: "claude-haiku-4-5",
        upstream_model: "claude-haiku-4-5",
    },
];

pub fn resolve_model(model: &str) -> Option<&'static ModelRoute> {
    MODEL_ROUTES.iter().find(|r| r.public_model == model)
}

// ── Translation helpers ─────────────────────────────────────────────────────

pub fn map_stop_reason(anthropic_reason: Option<&str>) -> Option<String> {
    anthropic_reason.map(|r| match r {
        "end_turn" => "stop".to_string(),
        "max_tokens" => "length".to_string(),
        "tool_use" => "tool_calls".to_string(),
        "stop_sequence" => "stop".to_string(),
        // Defensive fallback only: public-web turns are resumed at the gateway
        // before translation. Keep an OpenAI-compatible value if a future
        // non-public stream unexpectedly reaches this mapping.
        "pause_turn" => "stop".to_string(),
        other => other.to_string(),
    })
}

/// Merge stream usage: message_start carries the input/cache token counts,
/// but on server-tool turns (web search) the final message_delta usage is
/// cumulative across search iterations — prefer its nonzero fields so cost
/// doesn't undercount searched turns. output and server_tool_use are only
/// authoritative in the final usage.
pub fn merge_stream_usage(
    initial: Option<&AnthropicUsage>,
    final_usage: &AnthropicUsage,
) -> AnthropicUsage {
    let pick = |final_v: i64, initial_v: i64| if final_v > 0 { final_v } else { initial_v };
    AnthropicUsage {
        input_tokens: pick(
            final_usage.input_tokens,
            initial.map_or(0, |u| u.input_tokens),
        ),
        output_tokens: final_usage.output_tokens,
        cache_creation_input_tokens: pick(
            final_usage.cache_creation_input_tokens,
            initial.map_or(0, |u| u.cache_creation_input_tokens),
        ),
        cache_read_input_tokens: pick(
            final_usage.cache_read_input_tokens,
            initial.map_or(0, |u| u.cache_read_input_tokens),
        ),
        server_tool_use: final_usage.server_tool_use.clone(),
    }
}

pub fn anthropic_usage_to_openai(usage: &AnthropicUsage) -> Usage {
    let prompt_tokens =
        usage.input_tokens + usage.cache_creation_input_tokens + usage.cache_read_input_tokens;
    let completion_tokens = usage.output_tokens;
    let prompt_tokens_details = if usage.cache_read_input_tokens > 0 {
        Some(PromptTokensDetails {
            cached_tokens: usage.cache_read_input_tokens,
        })
    } else {
        None
    };
    Usage {
        prompt_tokens,
        completion_tokens,
        total_tokens: prompt_tokens + completion_tokens,
        prompt_tokens_details,
    }
}
