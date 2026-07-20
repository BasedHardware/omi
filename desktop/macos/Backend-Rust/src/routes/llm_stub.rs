// Deterministic LLM responses for hermetic desktop E2E (OMI_LLM_STUB=1).
//
// Returns OpenAI-compatible SSE from fixture files instead of calling upstream
// providers. Echoes any [[MARKER:...]] token found in the request body.

use axum::body::{Body, Bytes};
use axum::http::{header, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::Json;
use chrono::Local;
use futures::{stream, StreamExt};
use serde_json::{json, Value};
use std::env;
use std::time::Duration;

use crate::models::chat_completions::{
    ChatCompletionRequest, ChatCompletionResponse, Choice, FunctionCall, ResponseMessage, ToolCall,
};

const DEFAULT_FIXTURE: &str = include_str!("../../fixtures/llm/default_stream.sse");
const DEFAULT_ASSISTANT_TEXT: &str = "Hermetic LLM stub response.";
const EXACT_MEMORY_AGENT_REQUEST: &str =
    "Have an agent look through my memories today and surface one surprising insight.";

#[derive(Debug, Clone, PartialEq)]
enum StubDirective {
    Text(String),
    ToolCall { name: String, arguments: Value },
}

pub fn llm_stub_flag_is_truthy(value: &str) -> bool {
    matches!(value.trim(), "1" | "true" | "yes" | "on")
}

pub fn llm_stub_enabled() -> bool {
    env::var("OMI_LLM_STUB")
        .map(|value| llm_stub_flag_is_truthy(&value))
        .unwrap_or(false)
}

fn message_text(content: &Option<Value>) -> Option<String> {
    content.as_ref().and_then(|value| {
        if let Some(text) = value.as_str() {
            Some(text.to_string())
        } else if let Some(parts) = value.as_array() {
            Some(
                parts
                    .iter()
                    .filter_map(|part| part.get("text").and_then(|text| text.as_str()))
                    .collect::<Vec<_>>()
                    .join("\n"),
            )
        } else {
            None
        }
    })
}

/// Marker tokens from the latest user turn only — avoids echoing markers that
/// appear in prior user messages or assistant echoes included in history.
fn extract_latest_user_text(req: &ChatCompletionRequest) -> String {
    let text = req
        .messages
        .iter()
        .rev()
        .find(|message| message.role == "user")
        .and_then(|message| message_text(&message.content))
        .unwrap_or_default();

    // The desktop kernel deliberately wraps its immutable context projection and
    // the actual user input in one adapter message. Historical turns in that
    // projection are untrusted context, not a new instruction. Keep the hermetic
    // stub on the same boundary as a real model by routing only on the canonical
    // user-message suffix; otherwise an old "spawn a background agent" turn can
    // hijack every later deterministic probe.
    text.rsplit_once("\n\n# User Message\n")
        .map(|(_, user_text)| user_text.to_string())
        .unwrap_or(text)
}

fn latest_user_index(req: &ChatCompletionRequest) -> Option<usize> {
    req.messages
        .iter()
        .enumerate()
        .rev()
        .find_map(|(index, message)| (message.role == "user").then_some(index))
}

fn exposes_tool(req: &ChatCompletionRequest, name: &str) -> bool {
    req.tools
        .as_ref()
        .is_some_and(|tools| tools.iter().any(|tool| tool.function.name == name))
}

fn latest_tool_result_after_user(req: &ChatCompletionRequest) -> Option<(String, String)> {
    let user_index = latest_user_index(req)?;
    let mut tool_names_by_id: Vec<(&str, &str)> = Vec::new();
    let mut latest = None;
    for message in req.messages.iter().skip(user_index + 1) {
        if message.role == "assistant" {
            for tool_call in message.tool_calls.as_deref().unwrap_or_default() {
                tool_names_by_id.push((&tool_call.id, &tool_call.function.name));
            }
        } else if message.role == "tool" {
            let name = message
                .tool_call_id
                .as_deref()
                .and_then(|id| {
                    tool_names_by_id
                        .iter()
                        .rev()
                        .find_map(|(known_id, name)| (*known_id == id).then_some(*name))
                })
                .unwrap_or("unknown");
            latest = Some((
                name.to_string(),
                message_text(&message.content).unwrap_or_default(),
            ));
        }
    }
    latest
}

fn harness_tokens(text: &str) -> Vec<String> {
    text.split(|character: char| {
        !(character.is_ascii_alphanumeric() || character == '-' || character == '_')
    })
    .filter(|token| token.starts_with("GAUNTLET-") || token.starts_with("RESILIENCE-"))
    .map(str::to_string)
    .collect()
}

fn last_harness_token(
    req: &ChatCompletionRequest,
    predicate: impl Fn(&str) -> bool,
) -> Option<String> {
    req.messages.iter().rev().find_map(|message| {
        let text = message_text(&message.content)?;
        harness_tokens(&text)
            .into_iter()
            .rev()
            .find(|token| predicate(token))
    })
}

fn exact_reply_token(user_text: &str) -> Option<String> {
    let lowercase = user_text.to_ascii_lowercase();
    let marker = "reply with exactly";
    let start = lowercase.find(marker)? + marker.len();
    let suffix = user_text[start..].trim_start_matches([':', ' ', '\t']);
    suffix
        .split_whitespace()
        .next()
        .map(|token| {
            token.trim_matches(|character: char| {
                !character.is_ascii_alphanumeric() && character != '_'
            })
        })
        .filter(|token| !token.is_empty())
        .map(str::to_string)
}

fn quoted_title(user_text: &str) -> Option<String> {
    let lowercase = user_text.to_ascii_lowercase();
    let marker_start = lowercase.find("background agent titled")?;
    let suffix = &user_text[marker_start..];
    let quote_start = suffix.find('"')? + 1;
    let quote_end = suffix[quote_start..].find('"')? + quote_start;
    let title = suffix[quote_start..quote_end].trim();
    (!title.is_empty()).then(|| title.to_string())
}

fn first_chunk_delay(user_text: &str) -> Duration {
    if user_text
        .to_ascii_lowercase()
        .contains("take about twenty seconds")
    {
        Duration::from_millis(1_500)
    } else {
        Duration::ZERO
    }
}

fn memory_tool_arguments_for_date(date: &str) -> Value {
    json!({
        "limit": 50,
        "start_date": date,
        "end_date": date
    })
}

fn today_memory_tool_arguments() -> Value {
    memory_tool_arguments_for_date(&Local::now().format("%Y-%m-%d").to_string())
}

fn response_after_tool(req: &ChatCompletionRequest, name: &str, result: &str) -> String {
    match name {
        "get_memories" => {
            "One surprising insight is that your strongest themes become clearer when today's memories are reviewed together."
                .to_string()
        }
        "spawn_agent" => last_harness_token(req, |_| true)
            .map(|marker| format!("Started the background agent for {marker}."))
            .unwrap_or_else(|| "Started the requested background agent.".to_string()),
        "list_agent_sessions" => harness_tokens(result)
            .into_iter()
            .last()
            .or_else(|| last_harness_token(req, |_| true))
            .map(|marker| format!("The background agent for {marker} is active."))
            .unwrap_or_else(|| "The background agent is active.".to_string()),
        "execute_sql" => "0".to_string(),
        "get_daily_recap" => "Yesterday's activity recap is ready.".to_string(),
        _ => DEFAULT_ASSISTANT_TEXT.to_string(),
    }
}

fn stub_directive(req: &ChatCompletionRequest) -> StubDirective {
    let user_text = extract_latest_user_text(req);
    let normalized = user_text.to_ascii_lowercase();

    if let Some((name, result)) = latest_tool_result_after_user(req) {
        return StubDirective::Text(response_after_tool(req, &name, &result));
    }

    let memory_probe = user_text.trim() == EXACT_MEMORY_AGENT_REQUEST
        || (normalized.contains("look through my memories today")
            && normalized.contains("surprising insight"))
        || normalized.contains("call get_memories again for today");
    if memory_probe && exposes_tool(req, "get_memories") {
        return StubDirective::ToolCall {
            name: "get_memories".to_string(),
            arguments: today_memory_tool_arguments(),
        };
    }

    if (normalized.contains("use spawn_agent now")
        || normalized.contains("spawn a background agent"))
        && exposes_tool(req, "spawn_agent")
    {
        let mut arguments = json!({
            "objective": user_text,
            "visible": true
        });
        if let Some(title) = quoted_title(&user_text) {
            arguments["title"] = json!(title);
        }
        return StubDirective::ToolCall {
            name: "spawn_agent".to_string(),
            arguments,
        };
    }

    if normalized.contains("status of the background agent")
        && exposes_tool(req, "list_agent_sessions")
    {
        return StubDirective::ToolCall {
            name: "list_agent_sessions".to_string(),
            arguments: json!({}),
        };
    }

    if normalized.contains("use execute_sql to count the rows in the memories table")
        && exposes_tool(req, "execute_sql")
    {
        return StubDirective::ToolCall {
            name: "execute_sql".to_string(),
            arguments: json!({"query": "SELECT COUNT(*) AS count FROM memories"}),
        };
    }

    if normalized.contains("what did i do yesterday") && exposes_tool(req, "get_daily_recap") {
        return StubDirective::ToolCall {
            name: "get_daily_recap".to_string(),
            arguments: json!({"days_ago": 1}),
        };
    }

    if normalized.contains("single word probe only") {
        return StubDirective::Text("PROBE".to_string());
    }
    if let Some(token) = exact_reply_token(&user_text) {
        return StubDirective::Text(token);
    }
    if normalized.contains("earlier push-to-talk voice turn") {
        if let Some(marker) = last_harness_token(req, |token| token.ends_with("-PTT")) {
            return StubDirective::Text(marker);
        }
    }
    if normalized.contains("what was the last thing i asked you for") {
        if let Some(marker) = last_harness_token(req, |token| token.ends_with("-FLOAT")) {
            return StubDirective::Text(format!(
                "The last request was the background-agent task tagged {marker}."
            ));
        }
    }
    if let Some(marker) = harness_tokens(&user_text).into_iter().last() {
        return StubDirective::Text(format!("Stub saw marker: {marker}"));
    }
    if normalized.contains("zebulon quarkfinder") {
        return StubDirective::Text(
            "I don't know them yet—tell me a little about them.".to_string(),
        );
    }
    StubDirective::Text(stub_assistant_text(&user_text))
}

fn extract_markers(text: &str) -> Vec<String> {
    let mut markers = Vec::new();
    let mut rest = text;
    while let Some(start) = rest.find("[[MARKER:") {
        let after = &rest[start + 9..];
        if let Some(end) = after.find("]]") {
            let marker = after[..end].to_string();
            if !markers.iter().any(|existing| existing == &marker) {
                markers.push(marker);
            }
            rest = &after[end + 2..];
        } else {
            break;
        }
    }
    markers
}

fn stub_assistant_text(body: &str) -> String {
    let markers = extract_markers(body);
    if markers.is_empty() {
        return DEFAULT_ASSISTANT_TEXT.to_string();
    }
    markers
        .iter()
        .map(|marker| format!("Stub saw marker: {marker}"))
        .collect::<Vec<_>>()
        .join(" ")
}

fn fixture_lines(body: &str, default_fixture: &str) -> Vec<String> {
    let echoed = stub_assistant_text(body);
    if echoed == DEFAULT_ASSISTANT_TEXT {
        return default_fixture
            .lines()
            .map(|line| line.to_string())
            .filter(|line| !line.is_empty())
            .collect();
    }
    vec![
        format!(
            r#"data: {{"id":"chatcmpl-stub","object":"chat.completion.chunk","created":0,"model":"omi-stub","choices":[{{"index":0,"delta":{{"role":"assistant","content":{}}},"finish_reason":null}}]}}"#,
            serde_json::to_string(&echoed).unwrap_or_else(|_| "\"\"".to_string())
        ),
        r#"data: {"id":"chatcmpl-stub","object":"chat.completion.chunk","created":0,"model":"omi-stub","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}"#.to_string(),
        "data: [DONE]".to_string(),
    ]
}

fn text_stream_lines(text: &str) -> Vec<String> {
    vec![
        format!(
            "data: {}",
            json!({
                "id": "chatcmpl-stub",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": "omi-stub",
                "choices": [{
                    "index": 0,
                    "delta": {"role": "assistant", "content": text},
                    "finish_reason": Value::Null
                }]
            })
        ),
        format!(
            "data: {}",
            json!({
                "id": "chatcmpl-stub",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": "omi-stub",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]
            })
        ),
        "data: [DONE]".to_string(),
    ]
}

fn tool_call_stream_lines(name: &str, arguments: &Value) -> Vec<String> {
    let call_id = format!("call_omi_stub_{name}");
    vec![
        format!(
            "data: {}",
            json!({
                "id": "chatcmpl-stub",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": "omi-stub",
                "choices": [{
                    "index": 0,
                    "delta": {
                        "role": "assistant",
                        "tool_calls": [{
                            "index": 0,
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": arguments.to_string()
                            }
                        }]
                    },
                    "finish_reason": Value::Null
                }]
            })
        ),
        format!(
            "data: {}",
            json!({
                "id": "chatcmpl-stub",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": "omi-stub",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]
            })
        ),
        "data: [DONE]".to_string(),
    ]
}

/// Text from the latest user turn in a Gemini `contents` array — ignores model
/// turns and stale markers echoed in prior assistant replies.
fn extract_latest_gemini_user_text(body: &str) -> String {
    let Ok(value) = serde_json::from_str::<Value>(body) else {
        return String::new();
    };
    let Some(contents) = value.get("contents").and_then(|c| c.as_array()) else {
        return String::new();
    };
    for content in contents.iter().rev() {
        if content.get("role").and_then(|r| r.as_str()) == Some("model") {
            continue;
        }
        let mut texts = Vec::new();
        if let Some(parts) = content.get("parts").and_then(|p| p.as_array()) {
            for part in parts {
                if let Some(text) = part.get("text").and_then(|t| t.as_str()) {
                    texts.push(text.to_string());
                }
            }
        }
        if !texts.is_empty() {
            return texts.join("\n");
        }
    }
    String::new()
}

fn gemini_stream_lines(text: &str) -> Vec<String> {
    let chunk = json!({
        "candidates": [{
            "content": {
                "parts": [{"text": text}],
                "role": "model"
            }
        }]
    });
    let stop = json!({
        "candidates": [{
            "content": {
                "parts": [{"text": ""}],
                "role": "model"
            },
            "finishReason": "STOP"
        }]
    });
    vec![
        format!("data: {chunk}"),
        format!("data: {stop}"),
        "data: [DONE]".to_string(),
    ]
}

pub fn stub_chat_completions_response(req: &ChatCompletionRequest) -> Response {
    let user_text = extract_latest_user_text(req);
    let directive = stub_directive(req);

    if !req.stream {
        let (content, tool_calls, finish_reason) = match directive {
            StubDirective::Text(text) => (Some(text), None, "stop"),
            StubDirective::ToolCall { name, arguments } => (
                None,
                Some(vec![ToolCall {
                    id: format!("call_omi_stub_{name}"),
                    call_type: "function".to_string(),
                    function: FunctionCall {
                        name,
                        arguments: arguments.to_string(),
                    },
                }]),
                "tool_calls",
            ),
        };
        let payload = ChatCompletionResponse {
            id: "chatcmpl-stub".to_string(),
            object: "chat.completion",
            created: 0,
            model: "omi-stub".to_string(),
            choices: vec![Choice {
                index: 0,
                message: ResponseMessage {
                    role: "assistant".to_string(),
                    content,
                    tool_calls,
                },
                finish_reason: Some(finish_reason.to_string()),
            }],
            usage: None,
        };
        return Json(payload).into_response();
    }

    let lines = match directive {
        StubDirective::Text(text) if text == stub_assistant_text(&user_text) => {
            fixture_lines(&user_text, DEFAULT_FIXTURE)
        }
        StubDirective::Text(text) => text_stream_lines(&text),
        StubDirective::ToolCall { name, arguments } => tool_call_stream_lines(&name, &arguments),
    };
    let delay = first_chunk_delay(&user_text);
    let stream = stream::iter(
        lines
            .into_iter()
            .enumerate()
            .map(|(index, line)| (index, Bytes::from(format!("{line}\n\n")))),
    )
    .then(move |(index, bytes)| async move {
        if index == 0 && !delay.is_zero() {
            tokio::time::sleep(delay).await;
        }
        Ok::<_, std::convert::Infallible>(bytes)
    });
    crate::routes::response_or_500(
        "llm_stub_chat_completions_stream",
        Response::builder()
            .status(StatusCode::OK)
            .header(header::CONTENT_TYPE, "text/event-stream")
            .header(header::CACHE_CONTROL, "no-cache"),
        Body::from_stream(stream),
    )
}

pub fn stub_gemini_proxy_response(body: &Bytes, action: &str) -> Response {
    let body_text = String::from_utf8_lossy(body);
    let user_text = extract_latest_gemini_user_text(&body_text);
    let echoed = stub_assistant_text(&user_text);
    if action == "streamGenerateContent" {
        let lines = gemini_stream_lines(&echoed);
        let stream = stream::iter(
            lines
                .into_iter()
                .map(|line| Ok::<_, std::convert::Infallible>(Bytes::from(format!("{line}\n\n")))),
        );
        return crate::routes::response_or_500(
            "llm_stub_gemini_stream",
            Response::builder()
                .status(StatusCode::OK)
                .header(header::CONTENT_TYPE, "text/event-stream"),
            Body::from_stream(stream),
        );
    }
    let payload: Value = json!({
        "candidates": [{
            "content": {
                "parts": [{"text": echoed}],
                "role": "model"
            },
            "finishReason": "STOP"
        }]
    });
    crate::routes::response_or_500(
        "llm_stub_gemini_json",
        Response::builder()
            .status(StatusCode::OK)
            .header(header::CONTENT_TYPE, "application/json"),
        Body::from(payload.to_string()),
    )
}

#[cfg(test)]
mod tests {
    // Tests may unwrap: the crate-level unwrap_used deny targets production
    // code; a test failing on unwrap is the test doing its job.
    #![allow(clippy::unwrap_used)]
    use super::*;
    use crate::models::chat_completions::{
        ChatCompletionRequest, ChatMessage, FunctionDefinition, ToolDefinition,
    };

    fn user_message(text: &str) -> ChatMessage {
        ChatMessage {
            role: "user".to_string(),
            content: Some(json!(text)),
            name: None,
            tool_calls: None,
            tool_call_id: None,
        }
    }

    fn tool_definition(name: &str) -> ToolDefinition {
        ToolDefinition {
            tool_type: "function".to_string(),
            function: FunctionDefinition {
                name: name.to_string(),
                description: None,
                parameters: None,
            },
        }
    }

    fn request(messages: Vec<ChatMessage>, tools: &[&str]) -> ChatCompletionRequest {
        ChatCompletionRequest {
            model: "omi-sonnet".to_string(),
            messages,
            stream: true,
            temperature: None,
            max_tokens: None,
            max_completion_tokens: None,
            tools: Some(tools.iter().map(|name| tool_definition(name)).collect()),
            tool_choice: None,
        }
    }

    #[test]
    fn stub_flag_truthy_values() {
        assert!(llm_stub_flag_is_truthy("1"));
        assert!(llm_stub_flag_is_truthy("true"));
        assert!(!llm_stub_flag_is_truthy("0"));
        assert!(!llm_stub_flag_is_truthy("false"));
    }

    #[test]
    fn fixture_echoes_marker_token() {
        let req = ChatCompletionRequest {
            model: "omi-sonnet".to_string(),
            messages: vec![ChatMessage {
                role: "user".to_string(),
                content: Some(json!("Please recall [[MARKER:desk-core-e2e]]")),
                name: None,
                tool_calls: None,
                tool_call_id: None,
            }],
            stream: true,
            temperature: None,
            max_tokens: None,
            max_completion_tokens: None,
            tools: None,
            tool_choice: None,
        };
        let lines = fixture_lines(&extract_latest_user_text(&req), DEFAULT_FIXTURE);
        assert!(lines.iter().any(|line| line.contains("desk-core-e2e")));
    }

    #[test]
    fn exact_memory_agent_initial_and_followup_each_require_get_memories() {
        let expected_memory_arguments = today_memory_tool_arguments();
        let initial = request(
            vec![user_message(EXACT_MEMORY_AGENT_REQUEST)],
            &["get_memories"],
        );
        assert_eq!(
            stub_directive(&initial),
            StubDirective::ToolCall {
                name: "get_memories".to_string(),
                arguments: expected_memory_arguments.clone(),
            }
        );

        let wrapped_initial = request(
            vec![user_message(&format!(
                "Objective:\n{EXACT_MEMORY_AGENT_REQUEST}\nUse the available Omi tools."
            ))],
            &["get_memories"],
        );
        assert!(matches!(
            stub_directive(&wrapped_initial),
            StubDirective::ToolCall { ref name, .. } if name == "get_memories"
        ));

        let followup = request(
            vec![
                user_message(EXACT_MEMORY_AGENT_REQUEST),
                ChatMessage {
                    role: "assistant".to_string(),
                    content: None,
                    name: None,
                    tool_calls: Some(vec![ToolCall {
                        id: "call-initial".to_string(),
                        call_type: "function".to_string(),
                        function: FunctionCall {
                            name: "get_memories".to_string(),
                            arguments: "{}".to_string(),
                        },
                    }]),
                    tool_call_id: None,
                },
                ChatMessage {
                    role: "tool".to_string(),
                    content: Some(json!("No memories found.")),
                    name: None,
                    tool_calls: None,
                    tool_call_id: Some("call-initial".to_string()),
                },
                ChatMessage {
                    role: "assistant".to_string(),
                    content: Some(json!("Initial insight.")),
                    name: None,
                    tool_calls: None,
                    tool_call_id: None,
                },
                user_message(
                    "Continue in this same agent session. Call get_memories again for today, then return one additional surprising insight.",
                ),
            ],
            &["get_memories"],
        );
        assert_eq!(
            stub_directive(&followup),
            StubDirective::ToolCall {
                name: "get_memories".to_string(),
                arguments: expected_memory_arguments,
            }
        );
    }

    #[test]
    fn memory_probe_bounds_get_memories_to_the_requested_day() {
        assert_eq!(
            memory_tool_arguments_for_date("2026-07-12"),
            json!({
                "limit": 50,
                "start_date": "2026-07-12",
                "end_date": "2026-07-12"
            })
        );
    }

    #[test]
    fn memory_tool_result_finishes_instead_of_looping() {
        let req = request(
            vec![
                user_message(EXACT_MEMORY_AGENT_REQUEST),
                ChatMessage {
                    role: "assistant".to_string(),
                    content: None,
                    name: None,
                    tool_calls: Some(vec![ToolCall {
                        id: "call-memory".to_string(),
                        call_type: "function".to_string(),
                        function: FunctionCall {
                            name: "get_memories".to_string(),
                            arguments: r#"{"limit":50}"#.to_string(),
                        },
                    }]),
                    tool_call_id: None,
                },
                ChatMessage {
                    role: "tool".to_string(),
                    content: Some(json!("No memories found.")),
                    name: None,
                    tool_calls: None,
                    tool_call_id: Some("call-memory".to_string()),
                },
            ],
            &["get_memories"],
        );

        let StubDirective::Text(text) = stub_directive(&req) else {
            panic!("tool result must terminate with assistant text");
        };
        assert!(text.contains("surprising insight"));
    }

    #[test]
    fn gauntlet_spawn_and_status_prompts_emit_real_control_tools() {
        let spawn = request(
            vec![user_message(
                "Use spawn_agent now to start a visible background agent titled \"Recall Page\". Objective: track marker GAUNTLET-SPAWN-ABC and wait silently.",
            )],
            &["spawn_agent"],
        );
        let StubDirective::ToolCall { name, arguments } = stub_directive(&spawn) else {
            panic!("spawn prompt must emit spawn_agent");
        };
        assert_eq!(name, "spawn_agent");
        assert_eq!(arguments["title"], "Recall Page");
        assert!(arguments["objective"]
            .as_str()
            .is_some_and(|objective| objective.contains("GAUNTLET-SPAWN-ABC")));

        let status = request(
            vec![user_message(
                "What is the status of the background agent you just started? Use list_agent_sessions.",
            )],
            &["list_agent_sessions"],
        );
        assert_eq!(
            stub_directive(&status),
            StubDirective::ToolCall {
                name: "list_agent_sessions".to_string(),
                arguments: json!({}),
            }
        );
    }

    #[test]
    fn gauntlet_status_tool_result_returns_marker_and_terminal_text() {
        let req = request(
            vec![
                user_message(
                    "What is the status of the background agent you just started? Use list_agent_sessions.",
                ),
                ChatMessage {
                    role: "assistant".to_string(),
                    content: None,
                    name: None,
                    tool_calls: Some(vec![ToolCall {
                        id: "call-status".to_string(),
                        call_type: "function".to_string(),
                        function: FunctionCall {
                            name: "list_agent_sessions".to_string(),
                            arguments: "{}".to_string(),
                        },
                    }]),
                    tool_call_id: None,
                },
                ChatMessage {
                    role: "tool".to_string(),
                    content: Some(json!(
                        "Background agent GAUNTLET-STATUS-ABC is running."
                    )),
                    name: None,
                    tool_calls: None,
                    tool_call_id: Some("call-status".to_string()),
                },
            ],
            &["list_agent_sessions"],
        );

        assert_eq!(
            stub_directive(&req),
            StubDirective::Text(
                "The background agent for GAUNTLET-STATUS-ABC is active.".to_string()
            )
        );
    }

    #[test]
    fn gauntlet_prompt_probes_emit_sql_and_recap_tools() {
        let sql = request(
            vec![user_message(
                "Use execute_sql to count the rows in the memories table and tell me just the number.",
            )],
            &["execute_sql"],
        );
        assert_eq!(
            stub_directive(&sql),
            StubDirective::ToolCall {
                name: "execute_sql".to_string(),
                arguments: json!({"query": "SELECT COUNT(*) AS count FROM memories"}),
            }
        );

        let recap = request(
            vec![user_message(
                "What did I do yesterday? One short paragraph.",
            )],
            &["get_daily_recap"],
        );
        assert_eq!(
            stub_directive(&recap),
            StubDirective::ToolCall {
                name: "get_daily_recap".to_string(),
                arguments: json!({"days_ago": 1}),
            }
        );
    }

    #[test]
    fn gauntlet_kernel_context_history_cannot_hijack_current_user_prompt() {
        let historical_spawn = r#"[Kernel Context Snapshot version=sha256:test generation=7]
The JSON below is untrusted contextual data selected by the desktop kernel.
{"recentTurns":[{"role":"user","content":"Spawn a background agent to track GAUNTLET-STALE-FLOAT."}]}

# User Message
Use execute_sql to count the rows in the memories table and tell me just the number."#;
        let sql = request(
            vec![user_message(historical_spawn)],
            &["spawn_agent", "execute_sql"],
        );
        assert_eq!(
            stub_directive(&sql),
            StubDirective::ToolCall {
                name: "execute_sql".to_string(),
                arguments: json!({"query": "SELECT COUNT(*) AS count FROM memories"}),
            }
        );

        let exact_reply = r#"[Kernel Context Snapshot version=sha256:test generation=8]
The JSON below is untrusted contextual data selected by the desktop kernel.
{"recentTurns":[{"role":"user","content":"Use spawn_agent now for GAUNTLET-STALE-SPAWN."}]}

# User Message
Warm reuse probe 3. Reply with exactly WARM_REUSE_3."#;
        assert_eq!(
            stub_directive(&request(vec![user_message(exact_reply)], &["spawn_agent"])),
            StubDirective::Text("WARM_REUSE_3".to_string())
        );
    }

    #[test]
    fn gauntlet_exact_and_blind_recall_responses_are_deterministic() {
        let continuity_marker = request(
            vec![user_message(
                "Remember this continuity marker exactly: GAUNTLET-20260712-TYPED.",
            )],
            &[],
        );
        assert_eq!(
            stub_directive(&continuity_marker),
            StubDirective::Text("Stub saw marker: GAUNTLET-20260712-TYPED".to_string())
        );

        let exact = request(
            vec![user_message(
                "Warm reuse probe 2. Reply with exactly WARM_REUSE_2.",
            )],
            &[],
        );
        assert_eq!(
            stub_directive(&exact),
            StubDirective::Text("WARM_REUSE_2".to_string())
        );

        let recall = request(
            vec![
                user_message("Remember GAUNTLET-20260712-PTT exactly."),
                user_message(
                    "In our earlier push-to-talk voice turn I gave you a continuity marker starting with GAUNTLET- and ending in -PTT.",
                ),
            ],
            &[],
        );
        assert_eq!(
            stub_directive(&recall),
            StubDirective::Text("GAUNTLET-20260712-PTT".to_string())
        );

        let floating_recall = request(
            vec![
                user_message("Spawn a background agent to track GAUNTLET-20260712-FLOAT."),
                user_message("What was the last thing I asked you for?"),
            ],
            &[],
        );
        assert_eq!(
            stub_directive(&floating_recall),
            StubDirective::Text(
                "The last request was the background-agent task tagged GAUNTLET-20260712-FLOAT."
                    .to_string()
            )
        );
    }

    #[test]
    fn gauntlet_race_hold_delays_only_the_first_local_stub_chunk() {
        assert_eq!(
            first_chunk_delay(
                "Resilience race hold. Take about twenty seconds to reply with exactly: RACE_HOLD_DONE"
            ),
            Duration::from_millis(1_500)
        );
        assert_eq!(first_chunk_delay("ordinary prompt"), Duration::ZERO);
    }

    #[test]
    fn tool_call_stream_is_openai_compatible() {
        let lines = tool_call_stream_lines("get_memories", &json!({"limit": 50}));
        assert!(lines[0].contains(r#""finish_reason":null"#));
        assert!(lines[0].contains(r#""name":"get_memories""#));
        assert!(lines[0].contains(r#"\"limit\":50"#));
        assert!(lines[1].contains(r#""finish_reason":"tool_calls""#));
        assert_eq!(lines[2], "data: [DONE]");
    }

    #[test]
    fn fixture_echoes_marker_from_latest_user_message_only() {
        let req = ChatCompletionRequest {
            model: "omi-sonnet".to_string(),
            messages: vec![
                ChatMessage {
                    role: "user".to_string(),
                    content: Some(json!("Old turn [[MARKER:stale-marker]]")),
                    name: None,
                    tool_calls: None,
                    tool_call_id: None,
                },
                ChatMessage {
                    role: "assistant".to_string(),
                    content: Some(json!("Stub saw marker: stale-marker")),
                    name: None,
                    tool_calls: None,
                    tool_call_id: None,
                },
                ChatMessage {
                    role: "user".to_string(),
                    content: Some(json!(
                        "Latest [[MARKER:chat-hermetic]] and again [[MARKER:chat-hermetic]]"
                    )),
                    name: None,
                    tool_calls: None,
                    tool_call_id: None,
                },
            ],
            stream: true,
            temperature: None,
            max_tokens: None,
            max_completion_tokens: None,
            tools: None,
            tool_choice: None,
        };
        let lines = fixture_lines(&extract_latest_user_text(&req), DEFAULT_FIXTURE);
        let payload = lines.join("\n");
        assert!(!payload.contains("stale-marker"));
        assert_eq!(payload.matches("chat-hermetic").count(), 1);
        assert!(payload.contains("Stub saw marker: chat-hermetic"));
    }

    #[test]
    fn gemini_echoes_marker_from_latest_user_content_only() {
        let body = r#"{"contents":[
            {"role":"user","parts":[{"text":"Old [[MARKER:stale-marker]]"}]},
            {"role":"model","parts":[{"text":"Stub saw marker: stale-marker"}]},
            {"role":"user","parts":[{"text":"Latest [[MARKER:gemini-latest]]"}]}
        ]}"#;
        let echoed = stub_assistant_text(&extract_latest_gemini_user_text(body));
        assert!(!echoed.contains("stale-marker"));
        assert!(echoed.contains("Stub saw marker: gemini-latest"));
    }

    #[tokio::test]
    async fn gemini_non_stream_echoes_markers() {
        let body = Bytes::from(r#"{"contents":[{"parts":[{"text":"[[MARKER:gemini-test]]"}]}]}"#);
        let response = stub_gemini_proxy_response(&body, "generateContent");
        assert_eq!(response.status(), StatusCode::OK);
        let body_bytes = axum::body::to_bytes(response.into_body(), usize::MAX)
            .await
            .unwrap();
        let body_text = String::from_utf8(body_bytes.to_vec()).unwrap();
        assert!(body_text.contains("Stub saw marker: gemini-test"));
    }
}
