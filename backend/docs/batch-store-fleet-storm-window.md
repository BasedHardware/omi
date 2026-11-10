# The storm window is fleet-shared: one document per label, not one process

`firestore_transaction_contention operation=<label> attempt=5/5
outcome=exhausted` kept burning at the top of the error index even after the
storm damper became process-shared, because the deployment is not one
process. A hot label exhausts on many pods at once, and every pod whose
damper is still cold re-derives the storm the fleet has already measured:
five colliding attempts per pod against the same hot documents, then a local
window that dies with the pod's own discovery. The process registry (the
previous fix) made the window true for every store instance in one process;
it said nothing about the pod next to it.

Failure-Class: FC-storm-window-never-leaves-the-process

## What changed

- The process-shared damper now carries the namespace's fleet window
  (`fleet_storm_window`), created alongside the damper in the same
  double-checked registry. An exhaustion's applied window is broadcast —
  best-effort, one merge-set with a bounded call budget, no SDK retry — to
  `{namespace}_storm_dampers/{doc_id}` with `armed_until` (wall clock) and
  `window_seconds`. The FIRST pod through a storm therefore spaces the whole
  fleet's next entries, not just its own process.
- An entry consult adopts sibling pods' windows: when the fleet's residual
  for the label outwaits the process's own, the entry sleeps it (logged at
  INFO as `event=batch_store_backoff scope=fleet`) instead of re-deriving
  the storm with a fresh five-attempt chain. The adopt is one document read
  per label per process per `CACHE_TTL_SECONDS` (the mirror answers
  everything else), and a publish warms the mirror so the publisher never
  re-reads its own broadcast.
- `consult` and `arm` take the store's client as a keyword-only argument
  and forward it to the mirror; every Firestore fault on either lane
  collapses to "no fleet window" (counted, cached as no-window for the TTL,
  never raised), so a Firestore blip degrades to exactly the process-local
  damping the registry already shipped.
- The unit conftest resets the fleet registry around every test, the same
  seam the damper registry uses.

## What did not change

- The damper's ladder shape, cap, jitter, label cap, generation guard,
  mid-ladder gate, per-rung wave waits, and the exhaustion stamping of
  `FirestoreContentionExhausted.retry_after` are untouched: sharing moves
  WHERE the windows live, never their size or arithmetic.
- The mid-ladder gate stays process-local: a chain's deep rungs space
  themselves out of the process's own window and its own measured aborts,
  never out of a sibling pod's window — the entry adopt is the fleet
  boundary.
- Dormant behavior is byte-identical: with either contention kill switch
  off there is no damper, no consult, no adopt, and no broadcast. There is
  no separate fleet switch — the mirror is carried by the process-shared
  damper and lives and dies with the storm damper lever, exactly like the
  registry.
- An explicitly injected `storm_damper=` carries no fleet window, verbatim:
  tests own their damper identity, and a foreign damper must not publish
  into or adopt from the process's fleet view.
- Non-transactional read paths (`probe`, `due`, `oldest`,
  `service_frontier_hint`) never touch the lane.

## Boundary notes

- The lane is bounded by construction: windows inherit the damper cap (4 s),
  so a stale document reads as no window within seconds; the mirror holds at
  most `MAX_CACHED_LABELS` labels with oldest-entry eviction; unfit labels
  (anything outside the validated operation grammar's document-id alphabet)
  fail open as no window on both lanes; and the write volume is
  proportional to exhaustions — the thing the damper family eliminates —
  with a covered-window skip so a lockstep burst cannot turn one storm into
  a write storm on the same document.
- Two namespaces never share a window: mirrors and documents are keyed by
  namespace, and a prod store has never damped a dev store.
- The documents decay by wall clock and are never deleted; a label whose
  storms stop simply stops being written, and its document reads as expired.

Failure-Class: FC-storm-window-never-leaves-the-process
