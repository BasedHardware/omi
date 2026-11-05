# Trigger lanes price their own bytes; custody capture keeps the budget

Shipped 2026-11-05. The per-socket audio byte budget (`BUFFERED_AUDIO_MAX_BYTES`,
20 MiB) stopped being one shared counter across the custody capture lane and the
fire-and-forget enrichment lanes.

## Root cause (prod evidence)

One `ByteBudget` priced three different consumers on every listen socket:

- the custody capture lane (the durable window buffer and the private-cloud
  chunk queue — bytes whose ACK the client is owed),
- the audio-app trigger lane (`trigger_audiobuffer` → `audio_bytes_queue`,
  drained by `trigger_realtime_audio_bytes` LLM app calls),
- the developer audio-webhook lane (`audiobuffer` → the same queue, drained by
  `send_audio_bytes_developer_webhook`, up to the 30s webhook timeout per
  item).

When an enrichment consumer stalled long enough, its queued bytes held the
shared reservation and the next trigger-lane flush hit the shared budget's
fail-closed edge: `extend_bounded` / `append_bounded` raised
`AudioBackpressure`, and the receive loop booked it as `Could not process
audio` + close 1011 + `application_failed` — a live recording killed
mid-stream because an enrichment lane was busy, forcing the client to
reconnect and replay.

The Loop S prod-log sensor's largest pusher signature (about 1,000
tracebacks per 30 minutes at `finish_receive`, 2026-11-05 window) is this
shutdown-tail pressure; the same shared-budget saturation is what fills it.
The failure reproduces deterministically in
`test_saturated_app_trigger_lane_keeps_the_session_and_every_custody_byte`:
on the pre-fix code the 21st trigger flush ends the session 1011 and loses
the stream; on the fixed code every frame commits custody and the session
ends clean.

## The change

- `routers/pusher.py` gives the enrichment lanes their own
  `trigger_budget = ByteBudget(BUFFERED_AUDIO_MAX_BYTES)`. Both trigger
  buffer reserves, both queue appends and the consumer's per-item release
  now price against it.
- `utils/pusher_protocol.py` adds an explicit `drop_on_full` policy to
  `append_bounded` and `extend_bounded`: the fire-and-forget degradation the
  outbox-disabled path always had (drop this input / evict the oldest queued
  item, release its reservation, count `pusher_queue_drops`), selected at
  the call site instead of the custody `AudioBackpressure` raise. Drops log
  a WARNING with the uid — never silent.
- Custody is untouched: capture-buffer reserves, the private-cloud chunk
  queue and `bound_private_pending` keep the strict fail-closed raise. A
  genuinely exhausted custody budget still ends the session 1011 with
  nothing acknowledged, and the producer replays.

Net effect: enrichment saturation now costs the lane its own oldest trigger
(a counted WARNING) instead of the user's recording. The transcripts and
speaker-sample lanes already degraded exactly this way; the audio trigger
lanes were the last consumers that could terminate the capture session.

Failure-Class: FC-enrichment-backpressure-terminates-custody-session

## Tests

`backend/tests/unit/test_pusher_trigger_budget_isolation.py` pins all three
surfaces: the protocol degradation (drop-oldest / drop-frame instead of the
custody raise; defaults unchanged when the flag is absent), the
handler-level saturation choreography on the durable custody harness (frames
streamed against a stalled trigger consumer — every frame still commits
custody and the session ends clean, where the previous code killed the
session at the overflow frame), and the guards that custody exhaustion still
fails closed and the two budgets are distinct objects that drain
independently.
