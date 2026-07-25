# Chat-completions gateway

`chat_completions_routes` is the sole outward API. `routes/mod.rs` re-exports
it for `main.rs`; no caller imports an implementation module.

## Dependency direction

`route` owns HTTP dispatch and may call `request_translation`, `transport`, and
`streaming`. `streaming` owns OpenAI SSE output and may use `sse`, `transport`,
and the response/cost helpers in `request_translation`. `transport` owns
Anthropic HTTP, retries, and pause-turn continuation. `sse` owns byte framing
and OpenAI chunk serialization. `request_translation` owns Anthropic/OpenAI
shape conversion and its retrieval-policy injection points.

Provider translation must not reach SSE framing. Retrieval classification stays
in the sibling `routes::retrieval_policy` module; this package only owns the
chat-specific gate and injection call sites.

## Tests

The existing move-only unit suite lives under `tests/`, outside the
product-source line ratchet. The incremental-stream characterization tests feed
scripted raw byte chunks through the production translation closure, including
multi-byte UTF-8 splitting and premature EOF termination.
