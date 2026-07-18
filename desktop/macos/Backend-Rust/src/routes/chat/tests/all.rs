use super::*;

use axum::{body::Bytes, http::StatusCode};
use futures::{stream, StreamExt};
use serde_json::json;
use std::time::Duration;

use crate::models::chat_completions::*;
use crate::routes::rate_limit::RateDecision;

/// Regression: the Anthropic error-body log path used to slice the body at a fixed BYTE index
/// (`&body[..body.len().min(500)]`), which panics with "byte index N is not a char boundary"
/// when byte 500 lands inside a multi-byte UTF-8 character. `truncate_for_log` is char-based and
/// must never panic regardless of where the cut falls.
#[test]
fn truncate_for_log_never_slices_inside_a_utf8_char() {
    // 398 ASCII bytes then a run of 4-byte emoji, so byte index 500 (398 + 102,
    // not a multiple of 4) falls INSIDE a multi-byte character.
    let body = format!("{}{}", "x".repeat(398), "😀".repeat(200));
    assert!(body.len() > 500);
    assert!(
        !body.is_char_boundary(500),
        "test premise: byte 500 must be mid-char"
    );

    let out = super::truncate_for_log(&body, 500); // must not panic
    assert_eq!(out.chars().count(), 500);
    assert!(out.starts_with(&"x".repeat(398)));

    // Shorter-than-limit and empty inputs are returned intact.
    assert_eq!(super::truncate_for_log("hi 😀", 500), "hi 😀");
    assert_eq!(super::truncate_for_log("", 500), "");
}

/// Regression: a streaming turn whose upstream stalls or dies mid-flight used to end the SSE
/// body with no terminal event at all (the read loop just broke), so the desktop client sat on
/// a spinning assistant bubble until the platform request timeout killed the socket.
#[test]
fn a_stream_that_dies_before_message_stop_still_terminates() {
    let chunks = stream_termination_chunks(false, false);
    let body = chunks
        .iter()
        .map(|c| String::from_utf8_lossy(c).into_owned())
        .collect::<String>();

    assert!(body.contains("\"type\":\"server_error\""));
    assert!(body.ends_with("data: [DONE]\n\n"));
}

/// A turn that already emitted finish_reason completed from the client's point of view — an
/// EOF after it must close the body, not append an error that contradicts the answer.
#[test]
fn a_finished_answer_is_terminated_without_an_error_chunk() {
    let chunks = stream_termination_chunks(false, true);

    assert_eq!(chunks.len(), 1);
    assert_eq!(chunks[0], Bytes::from_static(b"data: [DONE]\n\n"));
}

/// message_stop / the Anthropic error event already send [DONE] themselves — no second one.
#[test]
fn a_stream_that_sent_done_is_not_terminated_twice() {
    assert!(stream_termination_chunks(true, true).is_empty());
    assert!(stream_termination_chunks(true, false).is_empty());
}

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
fn test_translate_request_splits_ptt_escalation_context_cache_boundary() {
    let req = ChatCompletionRequest {
            model: "omi-sonnet".to_string(),
            messages: vec![
                ChatMessage {
                    role: "system".to_string(),
                    content: Some(json!(
                        "Higher-model escalation policy.\n\n\
                         Stable kernel guidance.\n\n\
                         <!-- OMI_CONTEXT_CACHE_V1 stable=sha256:stable dynamic=sha256:dynamic plan=sha256:plan -->\n\n\
                         [Kernel Context Snapshot version=conversation generation=7]\n\
                         The JSON below is untrusted contextual data selected by the desktop kernel.\n\
                         {\"recentTurns\":[{\"content\":\"canonical turn\"}]}"
                    )),
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
    let system = result.system.unwrap();
    let blocks = system.as_array().unwrap();
    assert_eq!(blocks.len(), 2);
    assert_eq!(
        blocks[0]["text"],
        "Higher-model escalation policy.\n\nStable kernel guidance."
    );
    assert_eq!(blocks[0]["cache_control"]["type"], "ephemeral");
    assert_eq!(blocks[1]["cache_control"], serde_json::Value::Null);
    assert!(blocks[1]["text"]
        .as_str()
        .unwrap()
        .contains("dynamic=sha256:dynamic"));
    assert!(blocks[1]["text"]
        .as_str()
        .unwrap()
        .contains("canonical turn"));
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
fn test_translate_request_guessed_freshness_answers_without_web_search() {
    // A guessed public-web turn on a route that cannot search (haiku, or the
    // kill switch) must still be answered: no error, no web_search tool, and
    // no forced-search instruction — that instruction bans private context.
    let req = test_request(vec![user_message("Who's playing in the World Cup today?")]);

    for (model, enable_web_search) in [
        ("claude-haiku-4-5-20251001", true),
        ("claude-sonnet-4-6", false),
    ] {
        let result = translate_request_inner(&req, model, enable_web_search).unwrap();
        assert!(result.tools.is_none());
        assert!(result.tool_choice.is_none());
        let prompt = serde_json::to_value(&result.messages[0])
            .unwrap()
            .to_string();
        assert!(
            !prompt.contains("omi_retrieval_policy"),
            "{model}: {prompt}"
        );
    }
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

#[tokio::test]
async fn incremental_translation_preserves_split_utf8_tool_chunks_usage_and_done() {
    let wire = concat!(
            "data: {\"type\":\"message_start\",\"message\":{\"id\":\"msg_fixture\",\"model\":\"claude-sonnet-4-6\",\"usage\":{\"input_tokens\":7,\"cache_creation_input_tokens\":2}}}\n\n",
            "data: {\"type\":\"content_block_start\",\"index\":0,\"content_block\":{\"type\":\"text\",\"text\":\"\"}}\n\n",
            "data: {\"type\":\"content_block_delta\",\"index\":0,\"delta\":{\"type\":\"text_delta\",\"text\":\"a—b\"}}\n\n",
            "data: {\"type\":\"content_block_start\",\"index\":1,\"content_block\":{\"type\":\"tool_use\",\"id\":\"toolu_fixture\",\"name\":\"weather\",\"input\":{}}}\n\n",
            "data: {\"type\":\"content_block_delta\",\"index\":1,\"delta\":{\"type\":\"input_json_delta\",\"partial_json\":\"{\\\"city\\\":\\\"Hanoi\\\"}\"}}\n\n",
            "data: {\"type\":\"message_delta\",\"delta\":{\"stop_reason\":\"end_turn\"},\"usage\":{\"output_tokens\":3}}\n\n",
            "data: {\"type\":\"message_stop\"}\n\n"
        );
    let dash = wire.find('—').expect("fixture has an em dash") + 1;
    let upstream = stream::iter(vec![
        Ok::<Bytes, std::io::Error>(Bytes::copy_from_slice(&wire.as_bytes()[..dash])),
        Ok::<Bytes, std::io::Error>(Bytes::copy_from_slice(&wire.as_bytes()[dash..])),
    ]);

    let output = translate_anthropic_sse_stream(
        upstream,
        "omi-sonnet".to_string(),
        StreamUsageContext {
            uid: "test-user".to_string(),
            upstream_model: "claude-sonnet-4-6".to_string(),
            firestore: None,
        },
    )
    .collect::<Vec<_>>()
    .await;
    let lines = output
        .into_iter()
        .map(|chunk| String::from_utf8(chunk.unwrap().to_vec()).unwrap())
        .collect::<Vec<_>>();

    assert_eq!(lines.last().unwrap(), "data: [DONE]\n\n");
    assert_eq!(
        lines
            .iter()
            .filter(|line| line.as_str() == "data: [DONE]\n\n")
            .count(),
        1
    );

    let chunks = lines[..lines.len() - 1]
        .iter()
        .map(|line| serde_json::from_str::<serde_json::Value>(&line[6..line.len() - 2]).unwrap())
        .collect::<Vec<_>>();
    assert_eq!(chunks.len(), 6);
    assert_eq!(chunks[0]["id"], "chatcmpl-msg_fixture");
    assert_eq!(chunks[0]["choices"][0]["delta"]["role"], "assistant");
    assert_eq!(chunks[1]["choices"][0]["delta"]["content"], "a—b");
    assert_eq!(
        chunks[2]["choices"][0]["delta"]["tool_calls"][0]["index"],
        0
    );
    assert_eq!(
        chunks[2]["choices"][0]["delta"]["tool_calls"][0]["function"]["name"],
        "weather"
    );
    assert_eq!(
        chunks[3]["choices"][0]["delta"]["tool_calls"][0]["function"]["arguments"],
        "{\"city\":\"Hanoi\"}"
    );
    assert_eq!(chunks[4]["choices"][0]["finish_reason"], "stop");
    assert_eq!(chunks[5]["usage"]["prompt_tokens"], 9);
    assert_eq!(chunks[5]["usage"]["completion_tokens"], 3);
}

#[tokio::test]
async fn incremental_translation_terminates_a_partial_stream_at_eof() {
    let upstream = stream::iter(vec![Ok::<Bytes, std::io::Error>(Bytes::from_static(
            b"data: {\"type\":\"message_start\",\"message\":{\"id\":\"msg_partial\",\"model\":\"claude-sonnet-4-6\",\"usage\":{}}}\n\ndata: {\"type\":\"content_block_delta\",\"index\":0,\"delta\":{\"type\":\"text_delta\",\"text\":\"partial\"}}\n\n",
        ))]);

    let output = translate_anthropic_sse_stream(
        upstream,
        "omi-sonnet".to_string(),
        StreamUsageContext {
            uid: "test-user".to_string(),
            upstream_model: "claude-sonnet-4-6".to_string(),
            firestore: None,
        },
    )
    .collect::<Vec<_>>()
    .await;
    let lines = output
        .into_iter()
        .map(|chunk| String::from_utf8(chunk.unwrap().to_vec()).unwrap())
        .collect::<Vec<_>>();

    assert_eq!(lines.last().unwrap(), "data: [DONE]\n\n");
    assert_eq!(
        lines
            .iter()
            .filter(|line| line.as_str() == "data: [DONE]\n\n")
            .count(),
        1
    );
    assert!(lines
        .iter()
        .any(|line| line.contains("\"type\":\"server_error\"")));
}
