# Mid-ladder storm gating: a retry chain waits out a concurrently-armed window

`firestore_transaction_contention operation=<label> attempt=5/5
outcome=exhausted` burned hardest when one hot label ran many concurrent
chains: the first chain to exhaust armed the store storm damper's window for
that label, but every sibling chain that was already walking its own
equal-jitter ladder kept re-striking the same hot document inside that window
on the short early rungs. Each sibling burned its whole remaining budget
against a collision the damper had already measured, and each burn raised one
more `outcome=exhausted` line — the lockstep burn the damper exists to
prevent, repeated by every chain that was mid-flight when the window armed.

Failure-Class: FC-mid-ladder-retry-collides-inside-the-concurrently-armed-storm-window

## What changed

- `run_with_transaction_contention_retry` accepts an optional
  `inter_attempt_gate`, a caller-owned callable read after every failed
  attempt that will be retried, with the 1-based number of the attempt that
  just failed. The seconds it returns are added to that rung's equal-jitter
  wait, so the chain's own remaining rungs land after a storm window a
  sibling armed mid-flight instead of colliding inside it.
- The gate never gates the first attempt — a chain that reached the
  transaction always gets one try, the same rule the wall-clock deadline
  follows. It is advisory only: a bool, a non-number, a non-finite value, a
  zero or negative answer, and a raising gate all collapse to `0.0` and leave
  the bare equal-jitter schedule byte-for-byte unchanged.
- Under a scoped deadline the gate wait joins the jitter in the
  never-past-deadline check, so the accepted wall-clock bound stays
  `deadline + one in-flight attempt`. Without a deadline the gate can add at
  most the gate's own bound (the damper cap, 4.0 s) per remaining rung.
- `FirestoreStore.run` passes the gate when the storm damper is active. The
  gate reads the label's residual through a non-sleeping damper
  `peek` — the retry helper owns every pre-attempt sleep, so the damper must
  not double-sleep a wait the chain's budget has not accounted for — and
  waits out any window a sibling armed for this label between two attempts,
  logged at INFO as `event=batch_store_backoff scope=mid_ladder` with the
  operation label, the failed attempt, and the waited milliseconds.
- From the third rung — two measured collisions on one chain, sustained
  wave evidence — the rung also spaces itself by a per-rung wave wait on
  the same capped ladder the damper arms after an exhaustion, indexed by
  the failed attempt, jittered by the damper's own generator, and never
  recorded on the shared state. Waiting until the whole budget burned to
  measure a wave left the first chain into a fresh storm no window to
  wait out: all five rungs collided inside the wave the chain itself was
  measuring, and only the exhaustion that ended the chain armed anything.
  The first two rungs keep their sub-second transient-collision recovery,
  so routine single-collision chains are byte-identical to the bare
  ladder, and exhaustion stamping and the `retry_after` laddering stay
  exhaustion-driven.
- The retry warning and deadline-exhausted lines carry the gate wait
  explicitly: `outcome=retry delay_ms=<jitter> gate_ms=<gate>` and
  `outcome=deadline_exhausted remaining_ms=... delay_ms=... gate_ms=...`.
  `gate_ms=0` on a chain no gate waited, so attribution survives in the log
  stream either way.
- Success clearing stays generation-guarded: the entry consult's generation
  is refreshed by every mid-ladder peek, so a sibling arming the window
  mid-chain still holds `note_success` honest — a success clears the ladder
  only if no arm happened since the latest consult or peek.

## What did not change

- The entry consult still sleeps out any window already armed before the
  chain starts, and the first attempt still runs ungated immediately after
  it; a pre-armed window is waited exactly once, at entry, never again at
  rung one.
- With the damper dormant (either contention kill switch off) the schedule is
  byte-for-byte the bare ladder: no gate, no peek, no extra wait.
- The damper's own arm/consult/clear contract is untouched; `peek` only reads
  the same state under the same lock.
- Labels, attempt budgets, caps and the exhaustion stamp
  (`FirestoreContentionExhausted.retry_after`) are unchanged: a storm shifts
  when the remaining rungs land, never how many attempts a chain has.

## Boundary notes

- The gate is read once per failed rung, after the exhaustion check — the
  final failed attempt raises without consulting the gate, so a dying chain
  never waits for a window it will never use.
- A raising gate fails open rather than aborting the retry chain it spaces;
  the store's own gate cannot raise (a locked dict read), and the helper
  defends against any future gate that can.

Failure-Class: FC-storm-window-arms-only-after-exhaustion
