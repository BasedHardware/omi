# Batch privacy write evidence and delayed erasure

SCA-3508 keeps the projection precheck in its own change. On the write side,
`bpp_tokenless_write_shadow` samples Redis candidates against a live walk without
changing the authorizing decision. The candidate's original Firestore snapshot
and walk start bound reuse to five minutes, including a clock margin. A
purpose-derived HMAC binds the proof to its database, owner and covered sources.
A postcommit owner marker invalidates outstanding evidence and prevents late
fills. Both new levers default to zero.

`bpp_tokenless_write_cache` can reuse a decision during scheduler probing and
when committing scheduling fields on a previously read, existing ready job
that independently requires live compute admission. A lease commit may also
update queue, control and GPU reservation metadata. Creating jobs, persisting
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

The same conversation reconciler polls at most four due intents per minute.
Each slice reads at most one page of 100 batch artifact receipts. Readback
includes cache and shadow outcomes, due queue age, durable completions, and
Firestore, Postgres and object-storage work from
`omi_batch_pipeline_privacy_post_window_operations_total`. Before widening
authorization, use six hours with evaluated samples and zero
`mismatch_outside_window` on
`omi_batch_pipeline_privacy_tokenless_write_shadow_total`. The 137M reads/day
scenario assumes much wider proven sink coverage and GPU connectivity.
