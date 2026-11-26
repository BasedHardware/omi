# v3 short tasks stop requesting JSON mode

Short v3 windows (20–299 words) extract action items through the `conv_action_items` gateway lane. That lane
declares no structured output, so its `response_format={'type': 'json_object'}` was rejected with 400
`capability_not_supported`.

Since the TestFlight re-enable on 2026-11-18 at 11:20Z, every such window failed twice and ended as a failed
tile with no notes. `process_conversation` mapped the 400 to a silent 500.

What changes:
- `short_tasks` sends no `response_format`. The prompt still asks for `{"action_items": [...]}`.
- `_action_items` decodes the first complete JSON value in the reply, tolerating fences and prose. An object
  must carry an `action_items` list, and a bare array is taken as the list.
- Anything else still raises, so the task retries as before.

Rows that failed during the outage keep `v3_process_pending=False` and recover through the per-conversation
Retry (`/v1/conversations/{id}/reprocess`). No bulk re-drive ships here.

Rollback: revert. `CONVERSATIONS_V3=off` remains the kill switch.

Follow-up: declare structured output for the `conv_action_items` lane in the gateway, then restore JSON mode.

Regression coverage: `backend/tests/unit/test_conversations_v3_context.py`.
