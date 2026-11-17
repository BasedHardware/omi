# The drop hold is part of the reconnect protocol again

`9791f032ef5` dropped `listen_reconnect.enabled()` from the teardown branch that
holds a legacy (producer-less) mobile batch capture open after a socket drop.
The hold only has an exit when the reconnect protocol runs: a drained producer
lets the quiet check publish the close barrier. With `LISTEN_BATCH_RECONNECT_ENABLED`
unset, every mobile batch drop held its row open with no barrier.

This has been serving since the 2026-11-16 22:06Z backend-listen rollout (235baea).
The stranded row stays the canonical recording-session binding, and every
reconnect rolled into a new, empty `in_progress` generation about every 2 minutes.
Owner rows: 47/47 closed before the rollout, 0/153 after. Fleet: the
`batch_live_v1` `in_progress` share went from about 10% to 83-90% of finished
captures per hour.

The branch is gated on the switch again. With the protocol off, a drop
finalizes exactly as it did before the protocol shipped. The hold remains
available behind the switch.

Not in this change: closing the rows the storm already left (empty stubs and
stranded captures). That needs a recording-session-lease and storage-proof
fence, and is tracked separately.

Tests: `backend/tests/unit/test_mobile_batch_disconnect.py`.
Rollback: revert.
