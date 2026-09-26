# Memory L1 extraction — the foreground deadline the lane never declared

Date: 2026-09-05 · Scope: `utils/llm/model_config.py`
(`_FOREGROUND_TIMEOUT_FEATURES`) · Guard tests:
`tests/unit/test_memory_l1_foreground_deadline.py`,
`tests/unit/test_memory_l1_deadline_invariance.py`

## What happened

The GCP prod error feed (pusher container) carried this signature daily
across 2026-09-01..05 — 9–21 conversations per day, no retry, each one
silently losing its entire extracted-memory batch:

```
ERROR:utils.llm.working_observations:Error extracting memory L1 archive items: invoke_failed:APITimeoutError
```

## What was broken

`extract_l1_memory_archive_items_from_text` builds its client with
`get_llm('memory_l1')` and no explicit deadline. The feature had no entry
in `_FOREGROUND_TIMEOUT_FEATURES`, so under the prod pusher's
`OMI_LLM_GATEWAY_FEATURE_MODE=gateway` the client inherited the shared
background gateway transport deadline — 15 s to first byte — while the L1
extractor's single structured call reads the **whole** conversation
transcript (up to 32 candidate items with evidence quotes), the same shape
as its foreground siblings `conv_structure` / `conv_app_result` /
`daily_summary`, whose p90 first-byte latency sits well above 15 s.

Conversation finalization calls the extractor with `strict=True`, so the
timeout raised, the strict seam converted it to
`WorkingObservationExtractionError(stage='invoke')`, and the run dropped
that conversation's whole memory batch. Fifth instance of the class
`FC-foreground-call-inherits-background-deadline` (conv_structure +
daily_summary 2026-08-19; conv_app_result 2026-09-04 in c9c040bdc2, whose
message explicitly left the memory family un-audited; memory_l1 now).

## The fix

One route entry — the deadline is a property of the call, not of each call
site:

```python
_FOREGROUND_TIMEOUT_FEATURES = frozenset({
    'conv_structure',
    'conv_app_result',
    'daily_summary',
    'memory_l1',   # fifth instance of the class, 2026-09-05
})
```

Every `get_llm('memory_l1')` construction branch (gateway, direct,
BYOK-gateway, explicit override) now resolves the 60 s foreground deadline;
a caller's explicit `request_timeout` still wins.

## Operator-visible after this lands

The `invoke_failed:APITimeoutError` L1 signature should disappear from the
pusher feed. A conversation that still cannot finish extraction within 60 s
keeps today's behavior: the strict seam raises the typed
`WorkingObservationExtractionError`, finalization skips the replacement
write, and the ERROR line remains — now a genuine provider-capacity signal
rather than a mis-sized client deadline.

## Regression coverage

- Route declaration + the class guard (`_FOREGROUND_TIMEOUT_FEATURES`
  stays closed over its members; background lanes keep the default).
- Every `get_llm` construction branch threads the foreground deadline;
  explicit overrides win; `conv_folder` control stays default.
- The real extractor against a provider slower than the background
  deadline: strict and graceful batches survive at 60 s; restoring the 15 s
  deadline reproduces the exact incident (typed invoke failure chained to
  the provider timeout, empty batch, wrapper strict raise).
- Configuration axes — prompt prefix ± cache, belief-model flag (parser
  schema swaps, deadline does not), explicit client, BYOK branches — each
  pinned to the foreground deadline, with the incident reproduced on each
  axis as a control.
