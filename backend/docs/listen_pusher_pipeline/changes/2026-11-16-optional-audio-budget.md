# Optional audio never back-pressures capture (2026-11-16)

## Change and reason

[PR #25541](https://github.com/BasedHardware/omi/pull/25541). Production on
2026-11-16 closed about 180 live pusher sockets an hour with 1011 (`Could not
process audio: audio custody capacity exhausted`). The optional `audio_bytes`
queue (audio-bytes apps and the developer audio webhook) shared the 20 MB
per-connection `audio_budget` with durable capture custody, and a full optional
queue raised `AudioBackpressure` out of the receive loop. One affected account
had a developer audio webhook with an invalid URL, and its call was split
because the live stream closed twice. Main's interim version (50ac51ce18c)
waited up to `WS_RECEIVE_TIMEOUT` (300 s) for queue capacity instead, which
stalls the receive loop and custody behind an optional consumer.

Now optional audio is best-effort and isolated:

- App and webhook buffers and queued `audio_bytes` items are charged to their
  own `OPTIONAL_AUDIO_MAX_BYTES` (8 MB) per-connection budget. Custody keeps the
  full 20 MB `audio_budget` and its existing backpressure contract.
- `append_optional` evicts the oldest queued optional item when the queue is
  full. It never waits and never raises.
- `extend_optional` evicts stale queued items before dropping new optional
  data. It never raises.
- Drops are counted in `pusher_queue_drops{queue="audio_bytes"}` and
  `{queue="audio_app_buffer"|"audio_webhook_buffer"}`.
- Optional buffers flush at `optional_flush_bytes`: the configured interval,
  capped at a quarter of the optional budget. A long user-configured webhook
  interval (for example 120 s at 48 kHz) therefore still delivers rather than
  stranding a partial buffer.

No wire, payload, Firestore or custody contract changes. Optional consumers may
now miss audio under a slow or dead consumer, which is the intended
best-effort contract.

## Rollout and rollback

No flag; rollback is a revert. It ships with the next pusher image. Pusher
deploys have been blocked since 2026-11-10 because the dev CI deployer cannot
create the collector Role (`charts/pusher/templates/collector-rbac.yaml`); that
grant is an open approval.

## Verification and production acceptance

- Unit: `tests/unit/test_pusher_runtime_protocol.py` (eviction, budget, never
  raises, 48 kHz long interval delivers, custody never shares the optional
  budget) and `tests/unit/test_pusher_gap_recovery.py` (a blocked optional
  consumer neither stalls the receive loop nor closes the socket).
- Production: listen-side `Pusher audio_bytes Connection closed: received 1011`
  and pusher `audio custody capacity exhausted` fall to about 0 after the roll,
  while `pusher_queue_drops{queue="audio_bytes"}` becomes nonzero only for
  slow consumers.
