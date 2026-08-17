# Authorized Chat memory-context contract

Status: opt-in production adapter; no provider prompt or deployment activation

## Boundary

Chat generation depends on `ChatGenerationContextSource`. Chat itself imports no
PostgreSQL repository and does not inspect memory graph state. The PostgreSQL
adapter calls the canonical Firebase-authorized memory runtime, which owns the
locked authority revalidation, graph load, projection, rendering, citations,
and completeness envelope.

The Chat route passes its bearer credential ephemerally to the context source.
The supervisor does not place it in active generation state, message/event
records, provider source input, returned context, or errors. The PostgreSQL
runtime additionally compares the authorized graph owner with the account of
the admitted Chat generation before any render is released. This comparison
prevents a route/composition bug from injecting account A's memory into account
B's generation.

## Context shape

The provider-facing value is either:

```text
chat-generation-memory-context-v1 loaded
  canonical_page_json: exact ratified synthesized-memory page
```

or:

```text
chat-generation-memory-context-v1 unavailable
```

`loaded` preserves every synthesized item, opaque citation, optional
provenance coordinate, page window, completeness reason/frontier, and qualified
absence exactly. `unavailable` is not an empty memory set and must never be
interpreted as proof that the user has no relevant memory.

The first adapter reads one bounded first page (`limit: 25`). It does not chase
cursors or claim relevance. A continuation window therefore remains visible
to any future provider strategy instead of silently truncating into a complete
context.

## Availability and failure

Invalid credentials, account mismatch, revoked/stale authority, invalidated
reads, malformed canonical JSON, dependency exceptions, and hostile outcomes
all collapse to the same content-safe `unavailable` envelope. Context failure
alone does not fail Chat generation; the provider may answer without memory.
Attachment failure and durable Chat lifecycle behavior are unchanged.

## Activation boundary

`createPostgresFirebaseChatGenerationContextSource` is an injected adapter. It
does not register a route, start a listener, select a model, alter a prompt,
persist a token, or become a default. The local empty adapter remains the
default and also returns `unavailable`.

Actually placing loaded memory text into a production LLM prompt is a separate
strategy change. It requires a versioned prompt/context policy, bounded token
budget, paired evaluation (including repeats on the noisy read side), identity
regression checks, and rollout evidence. The present unit only makes that
future experiment explicit and authorization-correct.

## Nonclaims

- no query-bearing or semantic recall;
- no accepted/STM overlay;
- no change to subject admission, bystander privacy, compose voice, or identity
  authority;
- no approval/action authority stored in memory;
- no production Chat provider, listener, cohort, or native-client capture.
