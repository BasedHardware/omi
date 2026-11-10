# The fleet storm window's publish floor: a broadcast never lowers a deeper window

`firestore_transaction_contention operation=<label> attempt=5/5
outcome=exhausted` kept re-arming even where the fleet window shipped,
because the publish path could silently destroy the measurement it was
broadcasting. The covered-window skip compares against THIS process's mirror
only, so a sibling pod whose mirror is cold — or whose mirror went stale
inside the one-second TTL while a deeper window landed behind it — wrote its
own shallow first-rung window (0.125-0.25 s) straight over the deeper pod's
measured window (up to the 4 s cap). Every adopter then slept the shallow
residual and re-entered the storm early, re-deriving exactly the
five-attempt exhausted chains the damper family exists to stop: the fleet's
damping collapsed to the shallowest sibling's rung at the moment the storm
was hottest.

Failure-Class: FC-fleet-window-publish-truncates-a-deeper-storm

## What changed

- A publish whose window is not already mirror-covered first refreshes the
  mirror with ONE bounded read of the live document (`armed_until`, the same
  budget and timeout the adopt read uses), and a window the fleet already
  covers is skipped instead of written — counted separately as
  `publish_floor_skips` so operators can tell the two skip reasons apart.
  The document deadline is therefore monotone under publishes: a broadcast
  can raise the fleet's measurement or leave it alone, never lower it.
- The floor read rides the exhaustion lane only. Publishes are proportional
  to exhaustions — the thing the damper family eliminates — so the extra
  read is one bounded call per arm, on a path that fires at most once per
  five-attempt chain. A publish that writes performs one read plus one
  merge-set; a floored publish performs one read and no write.
- The floor read warms the mirror, so the guard makes adoption strictly
  cheaper to reason about: after any publish (write, floor skip, or covered
  skip), the next adopt within the TTL answers from the mirror exactly as
  before.
- Every failure of the floor read fails open exactly like an adopt read: a
  read fault, a missing document and a malformed document all read as "no
  window" and the broadcast proceeds to its write, degrading to the
  pre-floor behavior. A Firestore blip can never turn the guard into a new
  failure mode.
- The unit conftest and both grid suites (boundary, schedule) pin the guard
  end to end: the seeded-residual x window matrices, the fault and
  malformed-document matrices, mirror states, cold sibling pods, the
  exhaustion lane's jitter x rung x floor matrix, arm-return parity (the
  floor never touches the local arithmetic or the stamped retry-after), the
  stale-mirror interplay over wall offsets, and re-publish decay.

## What did not change

- The damper's ladder shape, cap, jitter, label cap, generation guard,
  mid-ladder gate, per-rung wave waits, and the exhaustion stamping of
  `FirestoreContentionExhausted.retry_after` are untouched: the floor moves
  WHERE a broadcast may land, never the size of any window and never the
  arm's return value.
- The mirror-covered skip still short-circuits before any read; the floor
  read happens only when the mirror does not already cover the window.
- Dormant behavior is byte-identical: with either contention kill switch
  off there is no damper, no arm, no publish, and no floor read. An
  explicitly injected `storm_damper=` still carries no fleet window and
  never touches a document.
- Two namespaces still never share a window; unfit labels still fail open
  as no window on both lanes; the mirror bound, eviction and TTL are
  unchanged.

## Boundary notes

- The guard is advisory under true write concurrency: two pods publishing
  in the same instant can still interleave their read-write pairs, and the
  last writer wins. Narrowing that race further needs a transaction on
  exactly the hot storm document — the contention the family exists to
  remove — so the floor deliberately stays read-then-merge-set, fail-open,
  and bounded: it removes the common sequential truncation (a cold or
  stale sibling arriving after the deep measurement) without adding a new
  contention point.
- The write volume is unchanged or lower: every floored publish replaces a
  write with a read, so a lockstep burst now produces at most one write per
  covered window instead of one per sibling.
- A stale mirror inside the TTL no longer trusts its cached no-window: the
  floor read is what makes "the fleet already covers it" true against the
  live document, not against a snapshot a second old.

Failure-Class: FC-fleet-window-publish-truncates-a-deeper-storm
