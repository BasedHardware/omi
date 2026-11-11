# Gate-level fleet adoption (the mid-ladder peek reads the fleet mirror)

The `x679/30m` `operation=batch_pipeline_store attempt=5/5 outcome=exhausted`
family is the loop's top production signature. The storm damper family
already spaces a chain's rungs out of a wave (`scope=mid_ladder`), spaces the
next entry of an exhausted label out of an armed window, adopts sibling pods'
windows on entry (`scope=fleet`), and carries one namespace spill across
sharded sibling labels on entry (`scope=spill`). Every one of those lanes
shared one blind spot: they act at ENTRY. A chain that entered before the
broadcast — the common case, because a storm arms exactly while chains are in
flight — never re-read the evidence. Its early rungs kept striking the hot
documents with only the bare equal-jitter schedule, and a chain could exhaust
(`attempt=5/5`) against a window its own pod's mirror already held.

## The change

`_ContentionStormDamper.peek(label, client=...)` — the mid-ladder gate's
read — adopts what the fleet has already measured, with the entry consult's
exact precedence:

1. The process's own residual for the label (unchanged, clamped at zero).
2. A sibling pod's armed window for the SAME label, read from the fleet
   mirror (`scope=gate_fleet`), wins whenever it is longer — never shortens
   the process's own wait.
3. When no window exists anywhere for the label, the namespace spill fills
   in (`scope=gate_spill`), capped by `SPILL_SHARE_CAP_SECONDS` (1.0 s) so a
   foreign label's deep window can never park the rung for the full damper
   cap.

The retry helper adds the residual to the rung's equal-jitter wait exactly as
before; the peek itself never sleeps. With no client in scope the read stays
process-local and free — the pre-fleet behavior, byte for byte. An injected
`storm_damper=` carries no fleet window and is honored verbatim.

## Why mid-flight adoption is safe and cheap

- Read amplification is bounded by the mirror TTLs: a chain's entry consulted
  the label document and the spill document at most one TTL (1 s) ago, so the
  common chain pays zero extra reads. A rung past the TTL re-reads once —
  and that re-read is the point: it picks up a window a sibling armed
  MID-FLIGHT, evidence no entry-time read can deliver.
- The wall-clock bound is untouched: under a scoped deadline the gate wait
  joins the never-past-deadline check in the retry helper, so the accepted
  bound stays `deadline + one in-flight attempt`. Without a deadline the
  gate can add at most the gate's own bound (the damper cap) per remaining
  rung, exactly as the retry helper's contract already states.
- Both lanes are advisory and fail-open: a read fault, an absent or malformed
  document, a hostile share cap, a non-finite residual — every one collapses
  to "no window" and leaves the bare schedule unchanged.
- The generation guard is untouched: `peek` still returns the process-local
  generation, and a success clears the ladder only when no arm happened
  since the latest consult or mid-ladder peek.

## Superseded contract

The gate was previously pinned "invisible to the fleet mirror" and "the
mid-ladder peek never reads the spill" — true when adoption was entry-only.
That isolation deliberately shipped the blind spot this change closes: a
fleet window armed after entry could not reach a chain already in flight,
and the chain re-derived the storm. The isolation pins move with this change
to the new contract: client-less peeks stay process-local and free; peeks
with a client adopt.

Failure-Class: FC-mid-ladder-retry-collides-inside-the-concurrently-armed-storm-window
