# Batch merge: plain ready-head drains commit through a revision-fenced narrow body

The blocked-head probe gate already skips drains that can only conclude
`blocked`. The remaining burn is the plain ready-head drain — the common
post-publication commit. It still opened the strict `batch_merge_commit`
transaction whose first act is the owner's pending query, and in production
every sibling lease heartbeat (each in-flight unit rewrites its own pending
row every 20 seconds) kept landing inside that transaction's query range:

    event=batch_merge outcome=retry exception_type=FirestoreContentionExhausted

x998 per 30-minute window at the 2026-11-05 sensor epoch, with the anonymous
`firestore_transaction_contention operation=batch_pipeline_store
attempt=5/5 outcome=exhausted` family (x2239) burning the same shared ladder.

## What changed

- `OrderedMerge.commit_next` commits the plain ready head through a narrow
  transaction that point-reads only {owner, head, result} — no transactional
  query at all. Ordering authority moves to a probed owner revision: every
  pending-set mutation (admission append, merge commit, terminal
  `quarantine_job`, recovery dispositions) already writes the owner revision,
  so a revision that still matches inside the transaction proves the probed
  head is exactly the strict body's candidate. Sibling heartbeats write
  neither the owner nor a settled ready row, so they can no longer abort the
  drain.
- Every fence mismatch, hold marker, release wake, shadow head and probe
  failure keeps the strict query transaction below as the authority; the
  narrow body reuses the strict body's commit tail verbatim (one shared
  `_append_committed_entry`), so the written entry, job transition and owner
  fence are byte-identical on every path that selects a ready candidate.
- One call-site contract: `BATCH_PIPELINE_MERGE_NARROW_COMMIT_ENABLED`
  (default on, flag-budgeted, kill switch restores the strict query for
  every drain). No store API, index, or durable schema changes: the narrow
  body uses only the existing `probe` and `head_pending` surfaces.
- The reviewed lifecycle inventory moves the merge result-log writer from
  the nested `OrderedMerge.commit_next.commit` closure to the shared
  `_append_committed_entry` tail (`tests/support/lifecycle_state_table.py`);
  the fields written and the states covered are unchanged.

## Contracts that do not change

- Strict capture order, the fresh bar, the bounded head wait, late-capture
  marking, the durable depth-cap hold marker, recovered release wakes and
  the privacy fence all behave exactly as before; the full parity suite
  drives every scenario through both modes and asserts identical entries
  and identical store state.
- The contention ladder, the storm damper and their kill switches are
  untouched. Owner-write races still abort and retry the narrow commit like
  any other transaction; only sibling-heartbeat aborts disappear.
- Labeled attribution: narrow attempts run under the same
  `batch_merge_commit` operation label, so exhaustion storms stay
  attributable on line one.

## Rollback

`BATCH_PIPELINE_MERGE_NARROW_COMMIT_ENABLED=false` restores the strict
query transaction for every drain; no durable state distinguishes narrow
commits from strict ones (same rows, same fields, same fences).

Failure-Class: FC-ready-head-merge-drains-join-sibling-heartbeat-abort-sets
