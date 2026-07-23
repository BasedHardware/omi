use axum::{
    body::{Body, Bytes},
    http::StatusCode,
    response::Response,
};
use futures::{Stream, StreamExt};
use serde_json::json;
use std::{sync::Arc, time::Duration};

use crate::auth::AuthUser;
use crate::models::chat_completions::*;
use crate::request_deadline::RequestDeadline;
use crate::services::FirestoreService;
use crate::AppState;

use super::request_translation::{compute_cost, translate_response};
use super::response_or_500;
use super::sse::{drain_sse_events, make_chunk, sse_line, stream_termination_chunks};
use super::transport::{complete_anthropic_server_tool_turn, log_usage, send_anthropic_with_retry};

/// How long a streaming turn may go without SEMANTIC progress before we end it.
///
/// Streaming deliberately sets no total response timeout (a long answer is not a stuck one), so
/// this idle bound is the only thing that catches a stalled upstream after the first visible
/// event. Progress means a client-visible chunk (role, text delta, tool delta, finish) — raw
/// bytes and Anthropic `ping` events emit nothing downstream and do not reset this timer, so a
/// provider cannot ping indefinitely while the client sees nothing (#9835). Before the first
/// visible event the request budget governs instead. This is a policy clock, not part of the
/// request deadline.
const STREAM_IDLE_TIMEOUT: Duration = Duration::from_secs(60);

pub(super) struct StreamUsageContext {
    pub(super) uid: String,
    pub(super) upstream_model: String,
    pub(super) firestore: Option<Arc<FirestoreService>>,
}

/// Detached work spawned during a request must NEVER inherit the request
/// deadline: the usage write outlives the response and runs under its own
/// bounded background policy (#9835). This seam exists so that contract is
/// testable without a live Firestore.
pub(super) fn spawn_detached_usage_write<F>(write: F)
where
    F: std::future::Future<Output = ()> + Send + 'static,
{
    tokio::spawn(write);
}

pub(super) async fn handle_server_tool_streaming(
    client: &reqwest::Client,
    api_key: &str,
    anthropic_req: &AnthropicRequest,
    route: &ModelRoute,
    user: &AuthUser,
    state: &AppState,
    is_byok: bool,
    deadline: &RequestDeadline,
) -> Result<Response, StatusCode> {
    // Public-web pause-turn synthesis is pre-first-visible-byte work: the whole
    // turn stays inside the request budget.
    let anthropic_resp =
        match complete_anthropic_server_tool_turn(client, api_key, anthropic_req, deadline).await {
            Ok(resp) => resp,
            Err(error) => return error.into_response_or_status(),
        };

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
            reasoning_content: None,
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
                reasoning_content: None,
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
            reasoning_content: None,
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

/// Convert Anthropic's framed bytes into the OpenAI-compatible SSE sequence.
///
/// This intentionally retains the existing stateful closure as one unit. The
/// generic byte stream is a narrow test seam: production supplies reqwest's
/// stream, while characterization tests can reproduce arbitrary network splits.
pub(super) fn translate_anthropic_sse_stream<S, E>(
    byte_stream: S,
    public_model: String,
    usage_context: StreamUsageContext,
    deadline: RequestDeadline,
) -> impl Stream<Item = Result<Bytes, std::io::Error>>
where
    S: Stream<Item = Result<Bytes, E>>,
    E: std::fmt::Display,
{
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
        // Terminal state of the turn, so a stream that dies mid-flight still ends the SSE body.
        let mut sent_finish = false;
        let mut sent_done = false;
        // Until the first client-visible chunk, the request budget governs the
        // wait — raw bytes and pings do not extend it. Afterwards the semantic
        // idle timer governs, reset only by visible chunks.
        let mut first_visible_at: Option<tokio::time::Instant> = None;
        loop {
            let wait = match first_visible_at {
                None => deadline.remaining(),
                Some(last_visible) => {
                    STREAM_IDLE_TIMEOUT.saturating_sub(last_visible.elapsed())
                }
            };
            let next = match tokio::time::timeout(wait, byte_stream.next()).await {
                Ok(next) => next,
                Err(_) if first_visible_at.is_none() => {
                    // The budget ran out before the first visible event — a
                    // ping-only or silent upstream. HTTP 200 is already on the
                    // wire, so the typed timeout is a terminal SSE error event.
                    tracing::error!(
                        "chat_completions: budget exhausted before first visible event for user {}",
                        usage_context.uid
                    );
                    let err_chunk = json!({
                        "error": {
                            "message": "The stream produced no visible output within the chat deadline budget. Please retry.",
                            "type": "upstream_timeout",
                            "code": 504
                        }
                    });
                    yield Ok(sse_line(&err_chunk));
                    yield Ok(Bytes::from_static(b"data: [DONE]\n\n"));
                    sent_done = true;
                    break;
                }
                Err(_) => {
                    tracing::error!(
                        "chat_completions: no semantic progress from Anthropic for {}s, ending stalled turn for user {}",
                        STREAM_IDLE_TIMEOUT.as_secs(),
                        usage_context.uid
                    );
                    break;
                }
            };

            let Some(chunk_result) = next else { break };

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
                                    reasoning_content: None,
                                    tool_calls: None,
                                },
                                None,
                                None,
                            );
                            yield Ok::<Bytes, std::io::Error>(sse_line(&chunk_val));
                            first_visible_at = Some(tokio::time::Instant::now());
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
                                        reasoning_content: None,
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
                                first_visible_at = Some(tokio::time::Instant::now());
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
                            AnthropicContentBlock::Thinking { .. }
                            | AnthropicContentBlock::RedactedThinking {} => {
                                // thinking_start — reasoning text arrives via
                                // thinking deltas; nothing to open here.
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
                                        reasoning_content: None,
                                        tool_calls: None,
                                    },
                                    None,
                                    None,
                                );
                                yield Ok(sse_line(&chunk_val));
                                first_visible_at = Some(tokio::time::Instant::now());
                            }
                            AnthropicDelta::CitationsDelta {} => {
                                // Web-search citation metadata — no OpenAI equivalent.
                            }
                            AnthropicDelta::ThinkingDelta { thinking } => {
                                let chunk_val = make_chunk(
                                    &stream_id,
                                    created,
                                    &model,
                                    ChunkDelta {
                                        reasoning_content: Some(thinking),
                                        ..ChunkDelta::default()
                                    },
                                    None,
                                    None,
                                );
                                yield Ok(sse_line(&chunk_val));
                            }
                            AnthropicDelta::SignatureDelta {} => {
                                // Thinking-block signature — internal; dropped.
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
                                            reasoning_content: None,
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
                                    first_visible_at = Some(tokio::time::Instant::now());
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
                                reasoning_content: None,
                                tool_calls: None,
                            },
                            finish,
                            None,
                        );
                        yield Ok(sse_line(&chunk_val));
                        sent_finish = true;
                        first_visible_at = Some(tokio::time::Instant::now());

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
                        sent_done = true;

                        // Logging context is absent for BYOK. Keeping this at
                        // the stream boundary makes the byte translator
                        // hermetic without changing server-key accounting.
                        if let (Some(fu), Some(firestore)) =
                            (final_usage.as_ref(), usage_context.firestore.as_ref())
                        {
                            let merged = merge_stream_usage(initial_usage.as_ref(), fu);
                            let cost = compute_cost(&merged, &usage_context.upstream_model);
                            let uid_clone = usage_context.uid.clone();
                            let fs = firestore.clone();
                            spawn_detached_usage_write(async move {
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
                        sent_done = true;
                    }
                }
            }
        }

        // The loop above exits on a stall, a transport error, or an upstream EOF. Any of those
        // can happen after a partial answer and before `message_stop`, so terminate the SSE body
        // ourselves — otherwise the client never sees finish_reason or [DONE] and keeps waiting.
        for chunk in stream_termination_chunks(sent_done, sent_finish) {
            yield Ok(chunk);
        }
    };

    translated_stream
}

pub(super) async fn handle_streaming(
    client: &reqwest::Client,
    api_key: &str,
    anthropic_req: &AnthropicRequest,
    route: &ModelRoute,
    user: &AuthUser,
    state: &AppState,
    is_byok: bool,
    deadline: &RequestDeadline,
) -> Result<Response, StatusCode> {
    let upstream_resp =
        match send_anthropic_with_retry(client, api_key, anthropic_req, true, deadline).await {
            Ok(resp) => resp,
            Err(error) => return error.into_response_or_status(),
        };

    let status = upstream_resp.status();
    if !status.is_success() {
        let body = upstream_resp.text().await.unwrap_or_default();
        tracing::warn!(
            "chat_completions: Anthropic stream returned {} for user {}: {}",
            status,
            user.uid,
            super::truncate_for_log(&body, 500)
        );
        return Ok(response_or_500(
            Response::builder()
                .status(StatusCode::from_u16(status.as_u16()).unwrap_or(StatusCode::BAD_GATEWAY))
                .header("content-type", "application/json"),
            Body::from(body),
        ));
    }

    let usage_context = StreamUsageContext {
        uid: user.uid.clone(),
        upstream_model: route.upstream_model.to_string(),
        firestore: (!is_byok).then(|| state.firestore.clone()),
    };
    let translated_stream = translate_anthropic_sse_stream(
        upstream_resp.bytes_stream(),
        route.public_model.to_string(),
        usage_context,
        *deadline,
    );
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
