# Mobile batch reconnect is on in prod

`LISTEN_BATCH_RECONNECT_ENABLED` was unset on both prod readers and listen, so
every phone or pendant socket drop finalized its server-batch capture. The app
reconnects seconds later with the same `client_conversation_id`, finds the row
completed, and rolls over to a new conversation. One 2-hour talk on 2026-11-16
became 15 conversations; 38% of connected users reconnected within 120 s in the
03:00-03:30Z sample.

This change sets the switch to `true` on GKE `backend-listen.env` and Cloud Run
`backend-sync.env` in `backend/deploy/runtime_env/prod.overlay.yaml`. It is the
activation step the 2026-11-17 re-gate deferred
([2026-11-17-drop-hold-regate.md](2026-11-17-drop-hold-regate.md)) and the
protocol described in
[2026-11-16-batch-reconnect-grace.md](2026-11-16-batch-reconnect-grace.md).

## Why the Nov 16 failure mode cannot recur

The Nov 16 hold had no exit: a reconnecting phone kept renewing the
recording-session lease, and the quiet check only seals a row whose lease has
expired, so the held row never got its close barrier. The reconnect protocol
adds a fenced producer. On teardown the producer drains its immutable packs,
**releases the recording-session lease** (`listen_batch_reconnect.disconnect`
sets `lease_expires_at = now`) and persists `deadline_at` at most 120 s out. The
quiet check's deadline is `min(quiet deadline, producer deadline)`, so a held row
seals at the deadline even if nobody returns. A same-origin, same-device
reconnect before the deadline claims the same row and continues it; a different
device, an expired deadline or a terminal reason starts a new conversation and
the old row still seals on its own deadline.

## Activation gate (read 2026-11-23T16:30Z, ro-prod)

- `prod-omi-backend-listen`: 41/41 Ready, all pods on one ReplicaSet
  (`64b69b96d7`) running `gcr.io/based-hardware/backend:96f0631`
  (`96f06315ca`, SCA-3646). Oldest pod 2026-11-22T02:43Z; no terminating pods.
  The re-gate `f0e10705d68d` is an ancestor of that commit.
- `backend-sync`: `backend-sync-17cb670-45066531375-1` at 100%, image
  `17cb670`; `f0e10705d68d` is an ancestor.
- `LISTEN_QUIET_FINALIZATION_ENABLED=true` on both; the quiet-check reconciler
  and finalization handler are enabled.
- No `LISTEN_BATCH_RECONNECT_ENABLED` on either surface before this change.
- Deploy lock free, no active deploy hold. Listen rolls are frozen 13:00-22:00Z
  (peak), so the roll starts in the 22:00Z-11:30Z window.

## Rollback

Set `LISTEN_BATCH_RECONNECT_ENABLED: {value: 'false', category: rollout}` on
`backend-listen` and `backend-sync` in one config train. With the switch off a
drop finalizes immediately again (the pre-2026-11-16 behaviour), and any drained
hold is ended and re-armed due now by the quiet check. Do not roll back a live
marked producer to old code; the drain gate in
[2026-11-16-batch-reconnect-grace.md](2026-11-16-batch-reconnect-grace.md)
applies.

## Readback

After the roll, compare 24 h of mobile batch captures against the 24 h before
the change: conversations per recording-hour (or the split rate for reconnects
within 120 s), and held `in_progress` rows without committed audio. The clean
metric is in the flag registry ramp: chapters per hour per active recording,
finalization lag bounded by grace plus reconciler, zero drained `in_progress`
rows older than grace plus reconciler, and exactly one batch obligation per
finalized generation.

Contract: [mobile server-batch reconnect grace](../../listen_pusher_pipeline.mdx#mobile-server-batch-reconnect-grace).
Tests: `backend/tests/unit/test_mobile_batch_disconnect.py`,
`backend/tests/unit/test_listen_batch_reconnect_grace.py`.
