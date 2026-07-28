use axum::{
    body::{Body, Bytes},
    http::StatusCode,
    response::Response,
};
use futures::{Stream, StreamExt};
use serde_json::{json, Value};
use std::{sync::Arc, time::Duration};

use crate::auth::AuthUser;
use crate::models::chat_completions::*;
use crate::services::FirestoreService;
use crate::AppState;

use super::request_translation::{compute_cost, response_text_content};
use super::response_or_500;
use super::sse::{drain_sse_events, make_chunk, sse_line, stream_termination_chunks};
use super::transport::{
    accumulate_anthropic_usage, append_pause_turn_continuation,
    complete_anthropic_server_tool_turn, send_anthropic_with_retry,
};

/// How long a streaming turn may go without a single byte from Anthropic before we end it.
///
/// Streaming deliberately sets no total response timeout (a long answer is not a stuck one), so
/// this idle bound is the only thing that catches a stalled upstream. Anthropic emits `ping`
/// events every few seconds throughout a generation, so a gap this long means the stream is
/// dead, not slow.
const STREAM_IDLE_TIMEOUT: Duration = Duration::from_secs(60);

pub(super) struct StreamUsageContext {
    pub(super) uid: String,
    pub(super) upstream_model: String,
    pub(super) firestore: Option<Arc<FirestoreService>>,
}

#[derive(Clone)]
pub(super) struct StreamContinuationContext {
    pub(super) client: reqwest::Client,
    pub(super) api_key: String,
    pub(super) request: AnthropicRequest,
}

#[derive(Default)]
pub(super) struct StreamedContentBlocks {
    blocks: Vec<Option<Value>>,
    input_json: std::collections::HashMap<usize, String>,
}

impl StreamedContentBlocks {
    pub(super) fn start_block(&mut self, index: usize, block: Value) {
        if self.blocks.len() <= index {
            self.blocks.resize(index + 1, None);
        }
        self.blocks[index] = Some(block);
    }

    pub(super) fn append_delta(&mut self, index: usize, delta: &Value) {
        let Some(block) = self.blocks.get_mut(index).and_then(Option::as_mut) else {
            return;
        };
        match delta.get("type").and_then(Value::as_str) {
            Some("text_delta") => {
                if let Some(text) = delta.get("text").and_then(Value::as_str) {
                    append_string_field(block, "text", text);
                }
            }
            Some("thinking_delta") => {
                if let Some(thinking) = delta.get("thinking").and_then(Value::as_str) {
                    append_string_field(block, "thinking", thinking);
                }
            }
            // The signature is what makes a replayed thinking block valid. A
            // pause_turn continuation resends this assistant turn to Anthropic,
            // and a thinking block whose signature is missing or truncated is
            // rejected upstream — dropping it here would fail the very turn the
            // continuation exists to finish.
            Some("signature_delta") => {
                if let Some(signature) = delta.get("signature").and_then(Value::as_str) {
                    append_string_field(block, "signature", signature);
                }
            }
            Some("input_json_delta") => {
                if let Some(partial_json) = delta.get("partial_json").and_then(Value::as_str) {
                    self.input_json
                        .entry(index)
                        .or_default()
                        .push_str(partial_json);
                }
            }
            _ => {}
        }
    }

    pub(super) fn stop_block(&mut self, index: usize) {
        let Some(input) = self.input_json.remove(&index) else {
            return;
        };
        let parsed = serde_json::from_str(&input).unwrap_or(Value::String(input));
        if let Some(block) = self.blocks.get_mut(index).and_then(Option::as_mut) {
            block["input"] = parsed;
        }
    }

    pub(super) fn into_value(self) -> Value {
        Value::Array(self.blocks.into_iter().flatten().collect())
    }
}

/// Translate a completed `pause_turn` continuation into the OpenAI chunks the
/// streaming client is still waiting for.
///
/// A continuation answers in text *and* may decide to call a client-side tool:
/// web search is only ever exposed alongside the client's own tools
/// (`inject_web_search`), so "search, then act" is the ordinary shape of a
/// paused turn. Forwarding only the text would hand the client
/// `finish_reason: tool_calls` with nothing to run.
pub(super) fn continuation_delta_chunks(
    resp: &AnthropicResponse,
    stream_id: &str,
    created: i64,
    model: &str,
    first_tool_ordinal: u32,
) -> Vec<Value> {
    let mut chunks = Vec::new();

    if let Some(text) = response_text_content(resp) {
        chunks.push(make_chunk(
            stream_id,
            created,
            model,
            ChunkDelta {
                content: Some(text),
                ..ChunkDelta::default()
            },
            None,
            None,
        ));
    }

    let mut ordinal = first_tool_ordinal;
    for block in &resp.content {
        let AnthropicContentBlock::ToolUse { id, name, input } = block else {
            continue;
        };
        chunks.push(make_chunk(
            stream_id,
            created,
            model,
            ChunkDelta {
                tool_calls: Some(vec![ChunkToolCall {
                    index: ordinal,
                    id: Some(id.clone()),
                    call_type: Some("function".to_string()),
                    function: Some(ChunkFunctionCall {
                        name: Some(name.clone()),
                        arguments: Some(serde_json::to_string(input).unwrap_or_default()),
                    }),
                }]),
                ..ChunkDelta::default()
            },
            None,
            None,
        ));
        ordinal += 1;
    }

    chunks
}

/// Total the usage of a turn that paused: the streamed leg plus the continuation.
///
/// The paused leg is the leg that ran the server tool — it holds the output tokens
/// generated before the pause *and* the `web_search_requests` Anthropic bills per
/// request. Reporting only the continuation's usage drops both, so a paused turn is
/// billed as if its first half never happened. The non-streaming lane already sums
/// every leg (`accumulate_anthropic_usage`); the streaming splice totals the same way.
pub(super) fn paused_turn_total_usage(
    initial: Option<&AnthropicUsage>,
    streamed_final: Option<&AnthropicUsage>,
    continuation: &AnthropicUsage,
) -> AnthropicUsage {
    // `message_start` carries the input side, `message_delta` the output side, so the
    // streamed leg is only whole once the two are merged.
    let mut total = match streamed_final {
        Some(final_usage) => merge_stream_usage(initial, final_usage),
        None => initial.cloned().unwrap_or_default(),
    };
    accumulate_anthropic_usage(&mut total, continuation);
    total
}

fn append_string_field(block: &mut Value, key: &str, suffix: &str) {
    if let Some(current) = block.get_mut(key).and_then(|value| value.as_str()) {
        let mut combined = current.to_string();
        combined.push_str(suffix);
        block[key] = Value::String(combined);
    } else {
        block[key] = Value::String(suffix.to_string());
    }
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
    continuation_context: Option<StreamContinuationContext>,
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
        let mut streamed_content = StreamedContentBlocks::default();
        let mut pause_turn_continuation: Option<StreamContinuationContext> = None;

        // Collect raw bytes and split into SSE events
        let mut byte_stream = std::pin::pin!(byte_stream);
        // Terminal state of the turn, so a stream that dies mid-flight still ends the SSE body.
        let mut sent_finish = false;
        let mut sent_done = false;
        loop {
            let next = match tokio::time::timeout(STREAM_IDLE_TIMEOUT, byte_stream.next()).await {
                Ok(next) => next,
                Err(_) => {
                    tracing::error!(
                        "chat_completions: no bytes from Anthropic for {}s, ending stalled turn for user {}",
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

                let raw_event: Value = match serde_json::from_str(data) {
                    Ok(value) => value,
                    Err(_) => continue,
                };
                if let Some(block) = raw_event.get("content_block").cloned() {
                    if let Some(index) = raw_event.get("index").and_then(Value::as_u64) {
                        streamed_content.start_block(index as usize, block);
                    }
                }
                if let Some(delta) = raw_event.get("delta") {
                    if let Some(index) = raw_event.get("index").and_then(Value::as_u64) {
                        streamed_content.append_delta(index as usize, delta);
                    }
                }

                let event: AnthropicStreamEvent = match serde_json::from_value(raw_event) {
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
                                }
                            }
                        }
                    }

                    AnthropicStreamEvent::ContentBlockStop { index } => {
                        streamed_content.stop_block(index);
                    }

                    AnthropicStreamEvent::MessageDelta { delta, usage } => {
                        if let Some(u) = usage {
                            final_usage = Some(u);
                        }

                        if delta.stop_reason.as_deref() == Some("pause_turn") {
                            pause_turn_continuation = continuation_context.clone();
                            tracing::info!(
                                "chat_completions: continuing paused Anthropic server-tool stream"
                            );
                            break;
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
                        sent_done = true;
                    }
                }
            }
            if pause_turn_continuation.is_some() {
                break;
            }
        }

        if let Some(mut continuation) = pause_turn_continuation {
            append_pause_turn_continuation(&mut continuation.request, streamed_content.into_value());
            match complete_anthropic_server_tool_turn(
                &continuation.client,
                &continuation.api_key,
                &continuation.request,
            )
            .await
            {
                Ok(anthropic_resp) => {
                    for chunk_val in continuation_delta_chunks(
                        &anthropic_resp,
                        &stream_id,
                        created,
                        &model,
                        next_tool_ordinal,
                    ) {
                        yield Ok(sse_line(&chunk_val));
                    }
                    let finish = map_stop_reason(anthropic_resp.stop_reason.as_deref());
                    let chunk_val = make_chunk(
                        &stream_id,
                        created,
                        &model,
                        ChunkDelta::default(),
                        finish,
                        None,
                    );
                    yield Ok(sse_line(&chunk_val));

                    let merged = paused_turn_total_usage(
                        initial_usage.as_ref(),
                        final_usage.as_ref(),
                        &anthropic_resp.usage,
                    );
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

                    if let Some(firestore) = usage_context.firestore.as_ref() {
                        let cost = compute_cost(&merged, &usage_context.upstream_model);
                        let uid_clone = usage_context.uid.clone();
                        let fs = firestore.clone();
                        tokio::spawn(async move {
                            if let Err(e) = fs
                                .record_llm_usage(
                                    &uid_clone,
                                    merged.input_tokens,
                                    merged.output_tokens,
                                    merged.cache_read_input_tokens,
                                    merged.cache_creation_input_tokens,
                                    merged.input_tokens
                                        + merged.cache_creation_input_tokens
                                        + merged.cache_read_input_tokens
                                        + merged.output_tokens,
                                    cost,
                                    "omi",
                                )
                                .await
                            {
                                tracing::error!("chat_completions: usage log failed: {}", e);
                            }
                        });
                    }
                    yield Ok(Bytes::from_static(b"data: [DONE]\n\n"));
                }
                Err(status) => {
                    tracing::error!(
                        "chat_completions: paused stream continuation failed with {}",
                        status
                    );
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
        } else {
            // The loop above exits on a stall, a transport error, or an upstream EOF. Any of those
            // can happen after a partial answer and before `message_stop`, so terminate the SSE body
            // ourselves — otherwise the client never sees finish_reason or [DONE] and keeps waiting.
            for chunk in stream_termination_chunks(sent_done, sent_finish) {
                yield Ok(chunk);
            }
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
) -> Result<Response, StatusCode> {
    let upstream_resp = send_anthropic_with_retry(client, api_key, anthropic_req, true).await?;

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
    let continuation_context = anthropic_req
        .tools
        .as_ref()
        .is_some_and(|defs| {
            defs.iter().any(|def| match def {
                AnthropicToolDef::Server(value) => value
                    .get("name")
                    .and_then(Value::as_str)
                    .is_some_and(|name| name == "web_search"),
                AnthropicToolDef::Custom(_) => false,
            })
        })
        .then(|| StreamContinuationContext {
            client: client.clone(),
            api_key: api_key.to_string(),
            request: anthropic_req.clone(),
        });
    let translated_stream = translate_anthropic_sse_stream(
        upstream_resp.bytes_stream(),
        route.public_model.to_string(),
        usage_context,
        continuation_context,
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
