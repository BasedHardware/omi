# Replay Harness LLM Streaming Wire-Fidelity Oracle

**LIFECYCLE: permanent** — a deterministic, advisory structural protocol test
for the LLM gateway's OpenAI-compatible streaming path. Run it with:

```bash
npm run test:replay-llm-streaming-wire-fidelity
```

The oracle starts a loopback-only OpenAI-compatible fake upstream that sends
synthetic SSE frames across deliberately fragmented HTTP chunks. It drives the
real gateway router, resolver, executor,
`OpenAICompatibleChatCompletionProvider.stream_chat_completion`, and
`StreamingResponse`. A test-only dependency override selects the loopback
provider; production routing, provider construction, retries, schemas, and
deployment configuration remain unchanged.

## Contract

The oracle proves only that:

1. the provider request selects streaming and terminal usage;
2. the gateway responds with `text/event-stream`;
3. fragmented upstream SSE produces nonterminal client data frame(s), then one
   terminal usage/finish frame, then exactly one `[DONE]`; and
4. an inbound `upstream_url` is rejected before the provider path, within a
   bounded local deadline and with non-loopback socket egress denied.

## Residual boundary

This is not provider conformance, production endpoint behavior, client
compatibility, traffic capture/replay, a release gate, LC3 or timing
qualification, or Phase 0B. It neither changes nor replaces the Listen Pusher
or Sync Cloud Tasks gauntlets, and it makes no real provider calls.

## Data safety

The fake parses request and SSE envelopes only long enough to assert protocol
shape. It retains and prints only endpoint/frame labels and ordering, schema-key
sets, status/error classes, a timing bucket, and request count. It never logs
or persists prompt/completion/token values, SSE payloads, headers, credentials,
identifiers, or provider bodies.
