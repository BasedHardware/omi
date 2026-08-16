# Conversation utilities

Shared conversation-domain helpers used by API routes, Pusher, sync workers,
and background processing.

## Boundaries

- `factory.py`, `location.py`, `search.py`, and `transcript_chunks.py` provide
  serialization, lookup, and read-model helpers; callers retain ownership of
  request authentication and response shaping.
- `process_conversation.py` is the synchronous enrichment coordinator. It
  persists the completed conversation and delegates expensive child work to the
  named executor lanes.
- `finalizer.py` is the durable handoff boundary for a persisted conversation.
  A caller must have already acquired a finalization-job lease before invoking
  it; it loads the conversation, performs enrichment through the postprocess
  bulkhead, and runs external integrations.
- Route- or worker-specific ownership, retries, queues, and leases belong
  outside this package: `database/conversation_finalization_jobs.py`,
  `services/conversation_finalization.py`, and their callers own those states.

## Data and credential safety

This package receives persisted conversation data only. Request-scoped BYOK
context may be propagated by a live Pusher caller into `finalizer.py`, but it
must never be written here, passed to durable task payloads, or logged.
