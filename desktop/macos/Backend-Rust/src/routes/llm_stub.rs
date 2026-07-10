// Deterministic LLM responses for hermetic desktop E2E (OMI_LLM_STUB=1).
//
// Returns OpenAI-compatible SSE from fixture files instead of calling upstream
// providers. Echoes any [[MARKER:...]] token found in the request body.

use axum::body::{Body, Bytes};
use axum::http::{header, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::Json;
use futures::stream;
use serde_json::{json, Value};
use std::env;

use crate::models::chat_completions::{
    ChatCompletionRequest, ChatCompletionResponse, Choice, ResponseMessage,
};

const DEFAULT_FIXTURE: &str = include_str!("../../fixtures/llm/default_stream.sse");
const DEFAULT_ASSISTANT_TEXT: &str = "Hermetic LLM stub response.";

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
    req.messages
        .iter()
        .rev()
        .find(|message| message.role == "user")
        .and_then(|message| message_text(&message.content))
        .unwrap_or_default()
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
    let echoed = stub_assistant_text(&user_text);

    if !req.stream {
        let payload = ChatCompletionResponse {
            id: "chatcmpl-stub".to_string(),
            object: "chat.completion",
            created: 0,
            model: "omi-stub".to_string(),
            choices: vec![Choice {
                index: 0,
                message: ResponseMessage {
                    role: "assistant".to_string(),
                    content: Some(echoed),
                    tool_calls: None,
                },
                finish_reason: Some("stop".to_string()),
            }],
            usage: None,
        };
        return Json(payload).into_response();
    }

    let lines = fixture_lines(&user_text, DEFAULT_FIXTURE);
    let stream = stream::iter(
        lines
            .into_iter()
            .map(|line| Ok::<_, std::convert::Infallible>(Bytes::from(format!("{line}\n\n")))),
    );
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
    use super::*;
    use crate::models::chat_completions::{ChatCompletionRequest, ChatMessage};

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
