# The drop hold is part of the reconnect protocol again

#25460 made a mobile batch socket drop hold a legacy (producer-less) capture
open when it has committed audio and a quiet check owns it. `72a09f9db9b`
gated that hold on `LISTEN_BATCH_RECONNECT_ENABLED`, and `9791f032ef5` removed
the gate again. Both changes reached prod together in the 2026-11-16 22:06Z
backend-listen rollout (235baea), with the switch unset.

The quiet check can only finalize a held capture once its recording-session
lease expires. A reconnecting phone keeps renewing that lease, so the held row
was never sealed. It stayed the canonical recording-session binding, and every
reconnect conflicted with it and rolled into a new empty `in_progress`
generation (no committed window) about every 2 minutes.

- Owner rows: 47/47 closed before the rollout, 0/153 after.
- Fleet: the `batch_live_v1` `in_progress` share went from about 10% of
  finished captures per hour to 83-90%.
- Stock, finished 22:00Z-11:00Z: 43,989 rows, of which 610 have committed
  audio (the held rows) and the rest are rollover stubs.

The hold is gated on the switch again. With the switch off, a drop finalizes
the capture as it did before #25460. The tradeoff returns too: a long
recording whose phone socket drops is split into several conversations. The
hold remains available behind the switch, together with the reconnect
protocol that gives it an exit.

This change stops new held rows, and with them new rollover stubs. It does not
close rows the storm already left: the held captures with committed audio and
the empty stubs. Their exit needs a durable writer-drain proof and a policy
decision, and is tracked separately.

Tests: `backend/tests/unit/test_mobile_batch_disconnect.py`. Rollback: revert.
