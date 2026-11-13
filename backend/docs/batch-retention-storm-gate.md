# Retention lane storm gate

The retention lane's bounded Firestore contention retry
(``run_retention_transaction``) drives both retention-phase transactions —
the completion sweep (``batch_retention``) and persist-phase artifact
registration (``batch_artifact_register``) — and both write the same hot
``jobs``/``results``/``intakes``/``artifacts`` rows the batch-store labels
storm on. The lane already rode the shared bounded retry engine, but it
passed no ``inter_attempt_gate`` and consulted no damper: a chain entering a
storm window the store lane (or a sibling pod) had armed for those rows
re-fired every rung inside it and re-derived the storm the fleet had already
measured — the same ``attempt=5/5 outcome=exhausted`` worker signature the
store lane's storm damper exists to prevent.

## Behavior

The retention chain now joins the process storm damper the same way every
batch-store entry and the projection lane do:

- Entry consult: before its first attempt, the chain waits out the label's
  residual window (logged at INFO as ``event=batch_retention_backoff`` or
  ``event=batch_artifact_register_backoff``). The first attempt is never
  gated.
- Mid-ladder spacing: every rung after a measured collision re-peeks the
  label's residual and adds it to the rung's equal-jitter wait (logged as
  ``scope=mid_ladder``); from the third failed rung the rung also spaces
  itself by the store damper's capped wave ladder.
- Exhaustion stamp: when the chain exhausts, the damper's applied window is
  stamped onto the raised ``FirestoreContentionExhausted.retry_after`` and
  the label's window is armed, so a caller scheduling its own re-offer lands
  after the window.
- Success clearing: a committed retention write clears the ladder only when
  no concurrent arm bumped the generation since the entry consult.

The damper is resolved per call through ``_store_storm_damper``, which reads
``FirestoreStore.contention_storm_damper`` and therefore returns ``None``
while either contention kill switch is off — a dormant damper leaves the
bare equal-jitter ladder byte-for-byte unchanged. Only a real
``FirestoreStore`` carries the damper contract; simulator and harness
primaries keep the legacy shape, and callers of the shared helper that pass
no store (tests, tools) keep it too.

## Kill switches

``BATCH_PIPELINE_CONTENTION_RETRY_ENABLED`` and
``BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED`` resolve per call through
the same accessor ``FirestoreStore.run`` uses, so one switch pair governs
every armed lane of the namespace. The retention helper itself stays
unconditional: without a damper in scope its retry schedule is exactly the
historical bare ladder, and the register path's
``contention_retry_enabled`` rollback branch is unchanged.

Failure-Class: FC-retention-contention-chain-collides-inside-armed-storm-window
