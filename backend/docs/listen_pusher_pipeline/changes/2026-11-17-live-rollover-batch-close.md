# A live rollover seals and cleans the generation it displaces

`close_batch_archive` published the archive-close barrier only when
`host.state.active` was not `True`, and `process_conversation` refused empty
cleanup under the same condition. Both guards protect the generation the socket
is still writing, but a rollover finalizes a generation the session has already
left while the socket stays live. The displaced row therefore kept
`server_batch_audio_received` without `server_batch_audio_closed`, and no later
actor could seal it: the quiet check only closes rows whose
`listen_batch_producer` phase is drained, and `LISTEN_BATCH_RECONNECT_ENABLED`
is off in prod, so no row ever carries a producer.

The row then became unprovable-empty. `tombstone_and_delete_empty_conversation`
requires `server_batch_audio_received is False` for a closed empty batch row, so
the finalizer's no-audio branch retried `server batch empty cleanup fenced`
forever. Because the first such row stays `in_progress`, it also stays the
canonical binding for the phone's `client_conversation_id`; every reconnect
conflicts with it, rolls over, and leaves another empty generation. On
2026-11-16 the owner's device produced one every 121-122 s from 22:13Z.

Rollover call sites now pass `displaced=True`:

- `close_batch_archive` seals a displaced generation even while the session is
  live. When the session already moved on, it commits only that generation's
  own packs through `LiveAudioArchive.finish_recording` instead of flushing a
  continuing successor.
- `process_conversation` may clean a displaced generation's empty row while the
  session is live. The live capture target keeps the original refusal.

`close_server_batch_audio` also clears `server_batch_audio_received` when it
seals an archive that never committed an original-audio window. A sealed
archive with no retained window is provably empty, so the existing empty-cleanup
fence admits it and the recording-session binding is released.

The quiet check is the only actor left once a legacy socket is gone, and it
published the barrier only for rows whose `listen_batch_producer` phase was
drained. With `LISTEN_BATCH_RECONNECT_ENABLED` off no row carries a producer, so
a producer-less capture with no committed window is now sealed at its quiet
deadline, before the check can retire as `no_content`. A producer-less row with
committed audio keeps its barrier for the batch handoff, as before.

Tests: `backend/tests/unit/test_live_rollover_batch_close.py`.

## The drop hold is part of the reconnect protocol again

The storm's trigger was `9791f032ef5`, which dropped `listen_reconnect.enabled()`
from the teardown branch that holds a legacy (producer-less) capture open after a
mobile socket drop. That hold only has an exit when the reconnect protocol runs:
with `LISTEN_BATCH_RECONNECT_ENABLED` unset, every mobile batch drop since the
2026-11-16 22:06Z listen rollout held its row open with no close barrier, which
stranded the recording-session binding. Owner rows: 47/47 closed before the
rollout, 0/153 after. The branch is gated on the switch again, so with the
protocol off a drop finalizes as it did before the protocol shipped (the
pre-22:06Z serving behavior). The hold remains available behind the switch.

## Stale recovery can close rows left by the storm

`recover_stale_in_progress` runs on a live socket, so `process_conversation`
refused every server-batch row it claimed ("still live") and nothing ever
recovered the stubs or the stranded capture they rolled over from. Stale
recovery now passes its cutoff; a claimed row that is not this socket's capture
target, has no producer, is `in_progress`, finished before the cutoff (one hour)
and has no committed window after it (`server_batch_audio_end` absent or older)
is treated as displaced. An empty stub is sealed with
`server_batch_audio_received=False` and deleted by the existing empty-cleanup
transaction; a stranded capture with committed audio is sealed and scheduled for
normal finalization. Rows with a producer, rows still receiving windows, and the
socket's own capture target are untouched. Recovery is the existing bounded
page (ten rows per reconnect, one claim per minute per user).

Rollback: revert this change; `STALE_IN_PROGRESS_RECOVERY_ENABLED=false` stops
the stale page entirely without a deploy of new code.
