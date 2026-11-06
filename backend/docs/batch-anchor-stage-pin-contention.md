# Batch anchor stage pins: sibling policy staging without anchor-row contention

`event=batch_completion outcome=retry exception_type=FirestoreContentionExhausted` burns
because the pump publishes one owner's segments concurrently, and every sibling segment's
first policy-staging transition read-modify-wrote the same shared anchor job document
inside its own five-attempt transaction budget. N concurrent sibling transitions means N
transactions writing one document: N-1 abort, retry, and collide again until the budget
is exhausted and the whole transition is logged as a contention retry. The same collision
fed the blended pre-attribution `operation=batch_pipeline_store attempt=5/5
outcome=exhausted` storm. The anchor row exists so an owner's segments share one canonical
policy snapshot without rewriting 128 sibling rows per queue visit — not so that every
sibling transition carries the anchor in its write set.

Failure-Class: FC-concurrent-sibling-policy-staging-writes-the-shared-anchor-row-and-exhausts-the-transition-retry-budget

## What changed

- `stage_in_transaction` / `policy_in_transaction`
  (`database/batch_pipeline_policy.py`) accept `pins`: a sibling staging call now
  self-stages the resolved part on the calling job's own row and appends an
  `AnchorStagePin(segment_id, stage, part, source)` descriptor instead of writing the
  anchor row inside the transition transaction. The transition's write set is exactly one
  job document (the calling job's), so concurrently publishing siblings of the same owner
  can no longer collide on the anchor.
- `flush_anchor_stage_pins(store, pins)` lands each descriptor after the caller's
  transition commits, in its own single-document transaction under the static label
  `batch_anchor_stage_pin`. The pin is CAS: if the anchor already carries the part (a
  retried sibling body, a concurrent publisher, a partial stamp), the first writer wins
  and the attempt no-ops. Provenance rules are identical to the old in-transaction write:
  `policy_part_sources` is recorded only while the row has no recorded whole-unit policy.
- The pin is best-effort by contract. A contended, privacy-blocked or raced pin is
  deferred — logged as `event=batch_anchor_stage_pin outcome=deferred` — and re-emitted by
  the next staging touch, which converges on the anchor's part. The calling transition is
  already durable when the pin runs; a failed pin never fails the transition.
- Wired through every staging caller: scheduler `fail` and `_pull_shard` (including
  `_prefer_merge_head`), `load_stage_policy`, `load_job_policy`, silence disposition
  prepare, terminal-empty prepare and speech-redrive prepare.
- Callers that do not pass `pins` keep the previous in-transaction anchor write, so the
  canonical-snapshot invariant (one pinned part per owner, siblings copy and converge,
  recorded parts never re-resolve env) is preserved in both modes.

## Runbook

- `event=batch_anchor_stage_pin outcome=deferred exception_type=FirestoreContentionExhausted`
  means a canonical pin lost its race or hit the retry budget. It self-heals on the next
  staging touch of any sibling of that owner; alert only if it persists for one owner
  across many minutes.
- `operation=batch_anchor_stage_pin outcome=exhausted` in the retry-helper log means the
  anchor row itself is hot. That should settle after the first staging wave pins each
  owner's parts; a sustained storm points at an external writer of anchor rows.
- Transition labels (`batch_fail`, `batch_complete`, `batch_pull shard=...`) should no
  longer carry sibling anchors in their write sets; a `batch_completion outcome=retry`
  rate that does not decay after deploy points at a staging caller that was not migrated
  to `pins`.
