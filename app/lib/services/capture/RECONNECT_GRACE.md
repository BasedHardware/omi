# Pendant recording identity across a link loss

`SuspendReason.reconnect` retains the logical session key, client recording ID,
transport, account/device identity and user pause bit for 120 seconds. The
account is bound when the active recording is minted, not at disconnect. Only native
connection timeouts and remote termination qualify. iOS delivers stable tokens
instead of localized error prose; Android preserves HCI status and gives manual
intent precedence. Unknown reasons, pairing loss and adapter shutdown are fresh
starts. DeviceProvider forwards capture link loss before its UI debounce, so a
rapid reconnect cannot cancel that transition.

The disconnected phase is idle. Teardown still closes transport and finalizes
the phone WAL tail. A same-device start strictly before the deadline restores
identity through the ordinary physical start body, including WAL rebinding and
ingress setup. Orphan packets received after identity returns but before capture
starts still use the existing safety WAL path. Duplicate provider/recovery starts
join the existing owner instead of minting another recording. This is identity
continuity, never evidence that frames absent during the gap were recovered.
INV-CAP-1's retention and sync-fence guards remain authoritative.

Expiry is checked on every coordinator event; a cancellable lifetime-owned timer
also wakes the reducer at the deadline. Manual stop/finish/disconnect, device
switch, account reset/sign-out, source takeover and mode changes retire grace.
Mute/unmute during the gap changes its saved pause bit and local capture policy.
A reconnect during an Omi call becomes call suspension with a typed pending
resume observation; the event is emitted only after the call releases capture.
Historical silence recovery clears its old marker without minting through grace
or overriding a call that started during an awaited effect. Manual-disconnect
markers belong only to a connected episode, so an already-down action cannot
poison a later connection. Snapshot launch sanitization discards grace; process restart never
adopts an old recording ID.

`RecordingLifecycleTelemetry` emits the existing `Recording Observation` event
with stage `reconnect_resumed` or `reconnect_grace_expired_fresh`. These describe
client identity decisions, not audio recovery or server conversation adoption.
A resumed recording does not emit another Recording Requested/Started.

## Server continuation and release boundary

The retained ID reaches `client_conversation_id` in `/v4/listen`. The live
controller uses the durable continuation pointer with the origin ID, source and
device checks. Terminal, privacy, quiet/calendar/day/span and language fences
remain server decisions; the app does not reopen a terminal conversation.

`batch_live_v1` already supports eligible mobile drop recovery with
`LISTEN_BATCH_RECONNECT_ENABLED` unset/false: `resumable_after_drop` commits the
archive tail and keeps the row open when the durable quiet check owns it and
committed audio exists. `test_mobile_batch_disconnect.py` covers actual teardown
and same-ID reconnect at 35 seconds. Empty/uncommitted rows, terminal rows or an
unavailable quiet owner may still produce a new server conversation. Retaining
one client recording ID does not promise one server conversation in those cases.

The stronger producer-grace protocol is optional here and cannot safely be
switched on without its old-listener/socket drain gate. Its registry and ramp
are in `config/feature-flags.yaml`; Release owns activation by 2026-11-20 under
`backend/docs/listen_pusher_pipeline/changes/2026-11-16-batch-reconnect-grace.md`.
After that gate, the in-repo production inputs are
`backend/deploy/runtime_env/prod.overlay.yaml`: set
`LISTEN_BATCH_RECONNECT_ENABLED: {value: 'true', category: rollout}` on GKE
`backend-listen.env` and Cloud Run `backend-sync.env`, then compose the runtime
environment and deploy through Release's train. Default grace is already 120s.
Keep quiet finalization/reconciliation enabled. The documented false/drain/zero-
marked-row rollback gate applies. This client PR changes no backend environment.

PR #25500's inspected diff has no overlapping capture/device files. Its v3
projection consumes recording IDs and recording-piece time ranges, including
multiple pieces from the same recording. Longer recordings preserve that input
contract; this lane changes neither v3 folding nor its branch. Hardware retention,
v3 integration after merge, deployment and production amplification metrics are
separate acceptance layers, not established by local tests.
