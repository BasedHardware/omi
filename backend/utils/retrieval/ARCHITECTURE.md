# Retrieval utilities

Agentic RAG and chat-tool retrieval for the backend. HTTP/WebSocket entry points
live in `backend/routers/`; persistence and vector search live in
`backend/database/`. This package owns tool schemas, tool implementations, and
the agent loop that calls them.

## Package map

- `agentic.py` — Claude-tool agent loop for chat (tool dispatch, streaming).
- `chat_scope.py` — hard-scope helpers for conversation / timeframe Ask (#4515);
  builds `chat_scope` from `PageContext` and intersects tool date bounds.
- `graph.py` / `hybrid.py` / `rag.py` — graph and hybrid retrieval helpers.
- `safety.py` / `tool_result_boundaries.py` — tool-output safety and size bounds.
- `tools/` — individual tool callables (conversations, memories, calendar, …).
- `tool_services/` — heavier service helpers backing those tools.

## Boundaries

- `chat_scope` is fail-closed for standard `/v2/messages` retrieval: when the
  client sends a conversation id and/or timezone-aware dates, conversation and
  search tools must not escape that window. Unsupported tools under
  conversation scope should refuse rather than search all memory.
- Claude Agent VM (`claudeAgentEnabled`) is intentionally out of scope for
  `chat_scope` until that path is wired.
- Callers own auth, rate limits, and response shaping; this package must not log
  raw user text or BYOK secrets.
