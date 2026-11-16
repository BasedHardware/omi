# A phone socket drop no longer ends a server-batch capture

Listen teardown finalized every batch-owned conversation as soon as its socket
closed. That rule was written for desktop, where close means stop. Once
`SERVER_BATCH_ONLY_MOBILE_PERCENT=100` (2026-11-02), every mobile capture was
batch-owned, so every phone or pendant socket drop finalized the capture. The
app reconnects seconds later with the same `client_conversation_id`, finds the
row completed, and rolls over to a new conversation. One 2-hour talk on
2026-11-16 became 15 conversations. In the 03:00-03:30Z sample, 110 of 290
connected users (38%) had at least one reconnect within 120 s.

Teardown now keeps the capture `in_progress` when all of these hold:

- the row is batch-owned (`config.server_batch.owned`) with `client_platform`
  `ios` or `android` and source `omi` or `phone`;
- the client sent no `finalization_reason`;
- `quiet_finalization.arm` confirmed a durable quiet check owns the row;
- after `resumable_after_drop` commits this socket's archive tail, the re-read row
  is still `in_progress` with committed audio (`config.server_batch.has_audio`).

The tail commit leaves `server_batch_audio_closed` unset, so a reconnect inside
the conversation timeout resumes the same row through the existing continuation
binding. New audio merges into the same monotonic bounds. If nobody comes back,
the quiet check admits `SERVER_RECOVERY`. The raw-only finalizer then registers
`record_pending` and completes the capture, the same unclosed-archive shape the
in-session silence timeout and `prepare()` rollover already produce.

Every other case keeps immediate finalization: desktop, web, multi-channel,
mobile sources without a quiet check, empty captures, an explicit client
reason, a refused or failed arm, or a row finalized meanwhile. The existing
`LISTEN_QUIET_FINALIZATION_ENABLED=false` also restores immediate finalization,
because a disabled quiet check never arms. No new flag or wire change.

Contract: [server batch-only capture](../../listen_pusher_pipeline.mdx#server-batch-only-capture-by-platform)
and [durable mono pendant/phone quiet checks](../../listen_pusher_pipeline.mdx#durable-mono-pendantphone-quiet-checks).
Tests: `backend/tests/unit/test_mobile_batch_disconnect.py`.
