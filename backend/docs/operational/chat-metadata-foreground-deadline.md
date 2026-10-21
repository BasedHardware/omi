# Conversation metadata extraction — the foreground deadline the shared lane never declared

Date: 2026-10-20 · Scope: `utils/llm/model_config.py`
(`_FOREGROUND_TIMEOUT_FEATURES`), `utils/llm/chat.py`
(`retrieve_metadata_fields_from_transcript`, `_process_extracted_metadata`) ·
Guard tests: `tests/unit/test_chat_metadata_foreground_deadline.py`,
`tests/unit/test_memory_l1_foreground_deadline.py` (class guard)

## What happened

The GCP prod error feed (pusher container) carried this signature at
x52–69/30m through 2026-10-20/21 — the #2 live error family:

```
ERROR:utils.llm.chat:e Request timed out.
```

## What was broken

`retrieve_metadata_fields_from_transcript` (and its message/text siblings
through `_process_extracted_metadata`) build their client with
`get_llm('chat_extraction')` and no explicit deadline. The feature has no
entry in `_FOREGROUND_TIMEOUT_FEATURES`, so under the prod pusher's gateway
mode the client inherited the shared background gateway transport deadline —
15 s to first byte — while these functions feed the **whole** conversation
content (full transcript, or the entire external message/document body) into
one structured call that must extract people, topics, entities, and dates.
Long conversations cannot answer inside 15 s: the provider timeout raised,
the `except` arm logged `e Request timed out.` and returned empty metadata,
and `save_summary_vector` upserted a vector whose people/topics/entities/dates
filters were all empty. Every affected conversation silently lost its
search-filter metadata — no error surfaced to the user, and the empty filters
persisted until a later metadata update.

Sixth instance of the class `FC-foreground-call-inherits-background-deadline`
(conv_structure + daily_summary 2026-08-19; conv_app_result 2026-09-04;
memory_l1 2026-09-05; chat metadata extraction now).

## Why a new feature key instead of the shared one

`chat_extraction` also serves thirteen short interactive-chat prompts
(requires_context, is_omi_question, date-range resolution, topic extraction,
chunk summaries, …) whose answers arrive well inside the background deadline
and whose callers should stay bounded by it. Declaring the whole feature
foreground would loosen the deadline for every one of those prompts. The
metadata extractor is a distinct call shape (whole-content in, structured
filters out, runs in conversation finalization), so it gets its own
`chat_metadata_extraction` feature that resolves to the same Luna route on
managed traffic and the same BYOK `gpt-4o-mini` route under a BYOK key.

## The fix

One route entry — the deadline is a property of the call, not of each call
site:

```python
_FOREGROUND_TIMEOUT_FEATURES = frozenset({
    'conv_structure',
    'conv_app_result',
    'daily_summary',
    'memory_l1',
    'chat_metadata_extraction',   # sixth instance of the class, 2026-10-20
})
```

The two metadata call sites in `utils/llm/chat.py` now build
`get_llm('chat_metadata_extraction')`. Every construction branch (gateway,
BYOK-gateway, direct BYOK) threads the 60 s foreground deadline; a caller's
explicit `request_timeout` still wins. The generated gateway lane
`omi:auto:chat-metadata-extraction` pins `request_timeout_ms: 90000` so the
lane's server-side budget covers the client's 60 s deadline.

## Operator-visible after this lands

The `e Request timed out.` metadata signature should collapse toward zero on
the pusher feed. A conversation whose extraction still cannot finish inside
60 s keeps today's failure shape (the `except` arm logs and returns empty
metadata) — now a genuine provider-capacity signal rather than a mis-sized
client deadline.

## Regression coverage

`tests/unit/test_chat_metadata_foreground_deadline.py` loads the real
`utils/llm/chat.py` module fresh against stubbed dependencies and drives the
real production functions against a provider that answers slower than the
background deadline:

- the route declaration and the closed foreground family;
- every `get_llm` construction branch threads the foreground deadline for the
  new feature while `chat_extraction` keeps the background default;
- the transcript, message, and text extractors against the slow provider:
  metadata survives at 60 s, and the call feature is `chat_metadata_extraction`;
- control: restoring the background deadline reproduces the exact prod
  failure — `e Request timed out.` logged, empty filters returned.
