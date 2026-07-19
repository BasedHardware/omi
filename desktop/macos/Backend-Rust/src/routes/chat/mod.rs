//! OpenAI-compatible chat-completions gateway.
//!
//! The route is deliberately split by provider boundary. See `ARCHITECTURE.md`
//! for the allowed dependency directions and the single public entry point.

#![deny(dead_code, unreachable_pub)]

use axum::{body::Body, response::Response};

mod request_translation;
mod route;
mod sse;
mod streaming;
mod transport;

pub(crate) use route::chat_completions_routes;

pub(super) fn response_or_500(builder: axum::http::response::Builder, body: Body) -> Response {
    crate::routes::response_or_500("chat_completions", builder, body)
}

/// Truncate `s` to at most `max_chars` characters for logging without ever
/// slicing inside a UTF-8 sequence. A byte-index slice (`&s[..500]`) panics with
/// "byte index N is not a char boundary" when the cut lands mid-multibyte-char,
/// which is reachable on the Anthropic error-body log path (upstream/BYOK error
/// responses can echo non-ASCII content). Char-based truncation cannot panic.
fn truncate_for_log(s: &str, max_chars: usize) -> String {
    s.chars().take(max_chars).collect()
}

// The moved legacy suite deliberately retains its assertions while the
// production modules stay below the product-source line ratchet.
#[cfg(test)]
use request_translation::*;
#[cfg(test)]
use route::*;
#[cfg(test)]
use sse::*;
#[cfg(test)]
use streaming::*;
#[cfg(test)]
use transport::*;

#[cfg(test)]
#[path = "tests/all.rs"]
mod tests;
