# External-integration conversation structuring — the last unguarded foreground lane

Date: 2026-10-21 · Scope: `utils/llm/model_config.py`
(`_FOREGROUND_TIMEOUT_FEATURES`), `llm_gateway/config/generated_route_overrides.yaml`
(`external_structure` lane budget) ·
Guard tests: `tests/unit/test_external_structure_foreground_deadline.py`,
`tests/unit/test_memory_l1_foreground_deadline.py` and
`tests/unit/test_chat_metadata_foreground_deadline.py` (family pins)

## What happened

The GCP prod error feed (pusher container) carried this signature at
x16/30m through 2026-10-20/21:

```
ERROR:utils.llm.gateway_error_contract:Conversation processing failed: TimeoutError
```

## What was broken

External integrations and the developer create-from-text endpoint
(`POST /v1/dev/user/conversations`) finalize a user-submitted capture through
`_get_structured`. For a `message`-source or `other`-source conversation that
path calls `get_message_structure` / `summarize_experience_text`, which build
`get_llm('external_structure')` with no explicit deadline and feed the **whole**
external text — the full imported message or document — into one structured
call (title, overview, action items, events). The feature had no entry in
`_FOREGROUND_TIMEOUT_FEATURES`, so the client inherited the shared background
gateway transport deadline: 15 s to first response byte, sized for cheap
background calls. A whole-text structured answer cannot reliably arrive inside
that window, so the provider raised `TimeoutError`, the `_get_structured` except
boundary mapped it to
`conversation_processing_http_exception`, and the caller got:

```
ERROR:utils.llm.gateway_error_contract:Conversation processing failed: TimeoutError
HTTPException: 500: Error processing conversation, please try again later
```

Every affected request lost the whole capture: no conversation, no title, no
summary, no action items. The developer-API shape of the same failure is the
`status=500` return on `POST /v1/dev/user/conversations`.

Seventh instance of the class
`FC-foreground-call-inherits-background-deadline` (conv_structure +
daily_summary 2026-08-19; conv_app_result 2026-09-04; memory_l1 2026-09-05;
chat metadata extraction 2026-10-20; external_structure now).

## Why the feature itself joins the set (no new key)

`chat_extraction` needed a dedicated `chat_metadata_extraction` key because the
shared lane also serves thirteen short interactive-chat prompts that must keep
the background deadline. `external_structure` has exactly two call sites — the
two whole-content structuring functions above — and nothing else. There is no
short-call member to protect, so the feature itself declares the foreground
deadline; a caller's explicit `request_timeout` still wins.

## The fix

One route entry plus one lane-budget line:

```python
_FOREGROUND_TIMEOUT_FEATURES = frozenset({
    'conv_structure',
    'conv_app_result',
    'daily_summary',
    'memory_l1',
    'chat_metadata_extraction',
    'external_structure',   # seventh instance of the class, 2026-10-21
})
```

Every construction branch (managed gateway, BYOK-gateway, direct BYOK) threads
the 60 s foreground deadline through `feature_request_timeout`. The generated
lane `omi:auto:external-structure` pins `request_timeout_ms: 90000` so the
lane's server-side budget covers the client's 60 s deadline instead of aborting
server-side at 30 s with the deadline technically "declared".

## Operator-visible after this lands

The `Conversation processing failed: TimeoutError` signature should collapse
toward zero on the pusher feed, and developer-API creates from long external
text stop returning 500. A capture whose structuring still cannot finish inside
60 s keeps today's failure shape (the caller's 500 and the client's retry) —
now a genuine provider-capacity signal rather than a mis-sized client deadline.
Longer-running consumers of the same feature — the daily-summary batch lanes
use `daily_summary`/`daily_summary_simple`, not this feature — are unaffected;
no other caller of `external_structure` exists (pinned by
`test_external_structure_is_only_used_by_the_two_whole_content_structurers`).

## Regression coverage

`tests/unit/test_external_structure_foreground_deadline.py` loads the real
`utils/llm/external_integrations.py` module fresh against stubbed dependencies
and drives the real production structurers against a provider that needs 25 s:
both functions succeed under the 60 s foreground deadline, and restoring the
15 s background deadline reproduces the exact prod failure —
`Conversation processing failed: TimeoutError` and the caller's
`HTTPException(500, "Error processing conversation, please try again later")`
through the real `_get_structured` boundary. Family pins in the sibling suites
(and in this module) fail if any member ever loses the deadline declaration.
