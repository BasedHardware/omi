# Batch privacy write evidence and delayed erasure

SCA-3508 keeps the projection precheck in its own change. On the write side,
`bpp_tokenless_write_shadow` samples Redis candidates against a live walk without
changing the authorizing decision. The candidate's original Firestore snapshot
and walk start bound reuse to five minutes, including a clock margin. A
purpose-derived HMAC binds the proof to its database, owner and covered sources.
A postcommit owner marker invalidates outstanding evidence and prevents late
fills. The write cache, shadow, and audit levers all default to zero.

`bpp_tokenless_write_cache` can reuse a decision during scheduler probing and
when committing scheduling fields on a previously read, existing ready job
that independently requires live compute admission. A lease commit may also
update existing queue, control, GPU reservation and pull-claim rows within
their scheduler transitions. If the proof expires before the buffered writes
are enqueued, the transaction reads live authority. Creating jobs, persisting
results, PostgreSQL primary writes, provider calls, artifact IO and projection
all retain their certified paths. Removing the authorization lever restores
the phase-one read path. A separately named, optional worker-chart secret can
bind only this cache to the shared Redis. Missing bindings and Redis errors
fall through. Verify route and access before assuming GPU savings.

Deferred conversation deletes keep a separate ten-minute batch purge under the
existing transactional hold fences. The Firestore authority commit also arms a
delayed artifact scan for completed account wipes, protection changes, and
batch cloud-sync or conversation recording opt-outs. Playback-storage
permission still invalidates decisions. Its separate recording archive has its
own erasure path. Reversible batch policy events select only in-flight, pre-event
artifact receipts in the affected scope. A completed account must still have its
wipe marker and an absent user row. The runner waits for an outstanding upload
reservation, deletes a pinned object generation, erases the Firestore receipt
under its current revision, and durably redrives Postgres mirror reconciliation.
Receipts issued after the event survive. Existing obligations continue when
either authorization lever is off.

Native recording and partial continuation uploads stamp recording provenance
when they reserve an artifact before admission. Sync intake forwards the
provenance from its admission decision, including when it identifies a
non-recording upload. Admission also stores provenance on the job for later
uploads. A recording opt-out sweeps an in-flight receipt in scope when its
provenance is unknown. A conversation policy edit becomes eligible for erasure
only after the reconciler certifies the same native-recording denial as the
write authority at the policy commit. It persists that proof before waiting
for the upload window or a legal hold. When the current row has changed, it
uses the commit snapshot. An unavailable expired snapshot leaves durable
recovery debt.

Permanent receipt failures move to a dedicated retry row while the cursor
continues to other artifacts. After five attempts by default
(`BATCH_PRIVACY_LATE_SWEEP_PERMANENT_ATTEMPTS`, bounded to 1–20), the invalid
intent or receipt retry stays in `batch_privacy_late_sweeps` without a
`due_at`. Alert on
`omi_batch_pipeline_privacy_post_window_dead_letters_total` and verify the
original scope and storage identity before requeueing. Transient failures
retain their existing retry path. Post-commit Redis invalidation errors log
and increment the `invalidation_error` outcome while the acknowledged write
still returns its result.

The same conversation reconciler polls at most four due intents per minute.
Each slice reads at most one page of 100 batch artifact receipts. The planning
allocation is 250 Firestore reads per slice and 1,440,000 per day at four
slices a minute, including 576,000 possible artifact-page reads per day.
Configured Postgres reconciliation also rereads primary mirror keys. Readback
includes cache and shadow outcomes, due queue age, durable completions, and
Firestore, Postgres and object-storage work from
`omi_batch_pipeline_privacy_post_window_operations_total`. Before widening
authorization, use six hours with evaluated samples at each site and zero
`mismatch_outside_window` on
`omi_batch_pipeline_privacy_tokenless_write_shadow_total`. The 137M reads/day
scenario assumes much wider proven sink coverage and GPU connectivity.

For canary expansion, `bpp_tokenless_write_audit` samples enforced hits after
the transaction succeeds. The lever defaults to zero and accepts 0–100 basis
points. Set it to 100 (1%) for the canary. Audits use a fresh read-only snapshot capped at two seconds and
32 point reads on a two-slot executor with no queue.
`omi_batch_pipeline_privacy_tokenless_audit_total` counts completed comparisons
by `role` and `outcome=agree|disagree_within_window|disagree_beyond_window`.
`omi_batch_pipeline_privacy_tokenless_write_audit_total` counts the same outcomes
by `site=probe|lease`. The GPU worker exposes both metrics and the separate
`omi_batch_pipeline_privacy_tokenless_write_audit_incomplete_total` for failed or
dropped samples.

SCA-3891's guard selects `outcome=disagree_beyond_window` as its numerator and
sums all outcomes for the same role or site as its denominator. Set
`min_comparisons=1` for this slice so zero completed audits is `NO_DATA` and the
first beyond-window disagreement breaches the guard. Require evidence at each
site before expansion. The inverse is `bpp_tokenless_write_cache=0`. For the
integration canary, use this `signals.correctness` block with the reviewed
app cohort in the SCA-3891 cut spec.

```json
{
  "metric": "omi_batch_pipeline_privacy_tokenless_audit_total",
  "scope": "app",
  "labels": {"role": "integration", "outcome": "disagree_beyond_window"},
  "min_comparisons": 1,
  "blind_after_seconds": 1800,
  "coverage": {
    "metric": "omi_batch_pipeline_privacy_tokenless_audit_total",
    "scope": "app",
    "labels": {"role": "integration"}
  }
}
```

Include reads under
`job:batch_tokenless_write_audit_probe` and `job:batch_tokenless_write_audit_lease`
in the net savings readback.
