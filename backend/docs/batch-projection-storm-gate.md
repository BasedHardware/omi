# Projection lane storm gate

The projection lane's bounded Firestore contention retry
(``ProjectionStore.run``) fights the same hot ``jobs``/``results`` rows as
the batch-store operation labels. It already opted into the shared bounded
retry engine, but it passed no ``inter_attempt_gate``: a projection chain
entering a storm window the store lane (or a sibling pod) had armed for
those rows re-fired every rung inside it and re-derived the storm the fleet
had already measured — the same ``attempt=5/5 outcome=exhausted`` worker
signature the store lane's storm damper exists to prevent.

## Behavior

The projection chain now joins the process storm damper the same way every
batch-store entry does:

- Entry consult: before its first attempt, the chain waits out the
  ``batch_projection`` label's residual window (logged at INFO as
  ``event=batch_projection_backoff``). The first attempt is never gated.
- Mid-ladder spacing: every rung after a measured collision re-peeks the
  label's residual and adds it to the rung's equal-jitter wait (logged as
  ``scope=mid_ladder``); from the third failed rung the rung also spaces
  itself by the store damper's capped wave ladder.
- Exhaustion stamp: when the chain exhausts, the damper's applied window is
  stamped onto the raised ``FirestoreContentionExhausted.retry_after`` and
  the label's window is armed, so a caller scheduling its own re-offer lands
  after the window.
- Success clearing: a committed projection clears the ladder only when no
  concurrent arm bumped the generation since the entry consult.

The damper is resolved through the new read-only
``FirestoreStore.contention_storm_damper`` accessor, which returns ``None``
while either contention kill switch is off — a dormant damper leaves the
bare equal-jitter ladder byte-for-byte unchanged. Only a real
``FirestoreStore`` carries the damper contract; simulator and harness
primaries keep the legacy shape.

## Kill switches

``BATCH_PIPELINE_CONTENTION_RETRY_ENABLED`` and the storm-damper switch
resolve per call, exactly as they do for ``FirestoreStore.run``. The
projection retry itself stays opt-in per policy
(``projection_contention``) with the legacy
``SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED`` env fallback; the gate only
attaches when that retry path is active.

Failure-Class: FC-projection-contention-chain-collides-inside-armed-storm-window
