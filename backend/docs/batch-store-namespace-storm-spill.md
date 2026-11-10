# The namespace storm spill: a storm one label measured protects sibling labels

`firestore_transaction_contention operation=<label> attempt=5/5
outcome=exhausted` kept re-arming on the scheduler's sharded labels even
after the fleet storm window shipped, because the damper keys every window
by exactly one label. The pull and claim labels are composed per shard
(``batch_pull shard=scheduler_03``, ``batch_claim shard=scheduler_04``),
and those shards contend on the same backing rows — the same pending
projection index, the same hot claim documents. A storm measured on one
shard's label armed only that label's window, so every sibling shard label
still entered the hot rows cold: five colliding attempts per sibling label,
each independently re-deriving the exhaustion the fleet had already
measured. The per-label design was right about namespaces (two namespaces
never share a window) but left labels of ONE namespace strangers to each
other, exactly when they are re-striking the same documents.

Failure-Class: FC-sibling-label-rederives-a-storm-the-fleet-already-measured

## What changed

- ``arm`` now also raises a namespace-level spill document
  (``{namespace}_storm_dampers/namespace_storm_spill``) carrying the deepest
  window any label of the namespace has measured (``armed_until``, the
  raising ``label``, ``window_seconds``). The write is monotone: a live
  spill that already reaches as deep as this arm's window stands, and a
  shallower arm never lowers it — during a lockstep burst across sibling
  labels the spill is written once per ladder rung the storm actually
  grows, not once per sibling arm. The broadcast rides the exhaustion lane
  (publishes stay proportional to exhaustions), runs best-effort outside
  the damper lock, and every write fault is swallowed and counted.
- A label whose own process residual AND own fleet window are both zero
  adopts the spill on entry, capped by
  ``_FleetStormWindow.SPILL_SHARE_CAP_SECONDS`` (1 s): a foreign label's
  deep window spaces the sibling label's first attempt without ever parking
  an unrelated lane for the full damper cap. The label's own windows always
  win — the spill fills only where the entry would otherwise ride in cold.
  Adoption is logged at INFO as ``event=batch_store_backoff scope=spill``.
- The spill mirror caches like the per-label mirror: at most one spill read
  per process per second, a publish warms it, and every read fault, absent
  document and malformed payload fails open as "no spill" (cached for the
  TTL, counted separately). A hostile ``peek_spill`` answer or a hostile
  share cap collapses to no wait; adoption never arms anything on the
  adopting label, so the success-clearing generation guard is untouched.
- The mid-ladder gate stays label-scoped: ``peek`` never reads the spill,
  so a chain's own rungs are spaced exactly as before, and the exhaustion
  ``retry_after`` stamp callers schedule against is unchanged.
- The arm's write trail keeps the label document LAST: the spill broadcast
  runs first, so every operator surface and grid pin that reads the
  exhaustion lane's writes still sees the label's own window document as
  the final word.

## What did not change

- Namespace isolation: the spill document lives in the namespace's own
  ``{namespace}_storm_dampers`` collection; two namespaces still never
  share a window — or a spill.
- Dormant behavior is byte-identical: with either contention kill switch
  off there is no damper, no consult, no arm, no spill read and no spill
  write. An explicitly injected ``storm_damper=`` carries no fleet window
  and therefore no spill lane, exactly as before.
- The ladder shape, cap, jitter, label cap, generation guard, mid-ladder
  gate, per-rung wave waits, the publish floor and the exhaustion stamping
  of ``FirestoreContentionExhausted.retry_after`` are untouched: the spill
  moves WHEN a cold sibling label's first attempt may start, never the size
  of any window and never an arm's return value.

## Boundary notes

- The share cap is the deliberate bound on being wrong about affinity: if
  two labels do not actually contend on the same rows, the spill costs the
  sibling label at most one capped wait per entry during the neighbor's
  measured storm, and nothing at all once the spill document expires. If
  they do contend, the sibling label's five-attempt re-derivation — the
  exact ``outcome=exhausted`` burn the damper family exists to stop — is
  replaced by a single bounded wait.
- The spill read adds at most one document read per process per second on
  the entry path, only when no window of any kind covers the entry; the
  mirror — not the document — absorbs every repeat consult inside the TTL.
- The spill never shortens a wait: it only raises a cold entry from zero to
  the share-capped residual, and it never records state on the adopting
  label.
