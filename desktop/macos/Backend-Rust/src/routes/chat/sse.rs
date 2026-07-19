use axum::body::Bytes;
use serde_json::json;

use crate::models::chat_completions::*;

pub(super) fn sse_line(data: &serde_json::Value) -> Bytes {
    let json_str = serde_json::to_string(data).unwrap_or_default();
    Bytes::from(format!("data: {}\n\n", json_str))
}

/// The SSE events that terminate a stream which produced no terminal event of its own —
/// an upstream stall, a transport error, or an EOF before `message_stop`.
///
/// The OpenAI SSE contract this endpoint speaks ends at `finish_reason` + `data: [DONE]`. A body
/// that simply stops leaves the client with no terminal signal, so the assistant bubble spins
/// until the platform request timeout kills the socket. The error chunk is emitted only when no
/// `finish_reason` was sent, so a turn whose answer already completed is never contradicted after
/// the fact.
pub(super) fn stream_termination_chunks(sent_done: bool, sent_finish: bool) -> Vec<Bytes> {
    if sent_done {
        return Vec::new();
    }

    let mut chunks = Vec::new();
    if !sent_finish {
        chunks.push(sse_line(&json!({
            "error": {
                "message": "Upstream stream ended before the response completed",
                "type": "server_error",
                "code": 502
            }
        })));
    }
    chunks.push(Bytes::from_static(b"data: [DONE]\n\n"));
    chunks
}

/// Pull every complete SSE event block out of the raw byte buffer, leaving any
/// trailing partial event behind.
///
/// The buffer must stay bytes: network chunks split at arbitrary offsets, so
/// decoding a chunk before it is framed destroys any multi-byte character that
/// straddles the boundary. Event blocks always end on the ASCII "\n\n", so a
/// complete block is safe to decode.
pub(super) fn drain_sse_events(buffer: &mut Vec<u8>) -> Vec<String> {
    let mut events = Vec::new();
    while let Some(event_end) = buffer.windows(2).position(|w| w == b"\n\n") {
        events.push(String::from_utf8_lossy(&buffer[..event_end]).into_owned());
        buffer.drain(..event_end + 2);
    }
    events
}

pub(super) fn make_chunk(
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
