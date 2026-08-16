# Replay Harness LLM Gateway Fake-Upstream Oracle

**LIFECYCLE: permanent** — a deterministic, advisory structural test for the
LLM gateway's real route and provider terminal path. Run it with:

```bash
npm run test:replay-llm-fake-upstream
```

The oracle starts a loopback-only OpenAI-compatible fake upstream and injects
that upstream only through FastAPI's test dependency override. It then drives
the real gateway router, route resolver, executor, and
`OpenAICompatibleChatCompletionProvider`. Normal provider construction and
routing remain unchanged outside this test process.

## Contract

The fake upstream proves only that:

1. the real provider adapter uses the expected chat-completions path;
2. a routed gateway request completes exactly one proxy-isolated, bounded local round trip;
3. gateway and upstream event ordering remains stable; and
4. an incoming request cannot choose or redirect the upstream target.

It intentionally does **not** establish OpenAI or Anthropic SSE fidelity,
provider conformance, production endpoint behavior, client compatibility, a
release gate, capture/replay, or Phase 0B.

## Data safety

The fake retains only endpoint path shape, event labels, request/response
schema keys, status/error classes, request count, and a bounded-timing result.
It never logs or persists prompt content, completions, token values, provider
bodies, header values, credentials, or identifiers.
