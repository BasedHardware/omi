# A lost v3 grouping pass says what it lost to

On 2026-11-25 about 7% of `/v1/conversations-v3/reconcile` passes were thrown away as
`raced reason=source_changed` and about 1.2% failed in `commit_projection` on a lock. Neither outcome
said which document it was or which code changed it, so the next fix could not be chosen by cause.

`database/conversations_v3_collisions.py` records that. Nothing about what a pass does changes.

- **Raced.** When a loaded document's revision moved and the pass is thrown away, one line and one
  counter step name the kind of document (`recording_row`, `open_conversation`, `conversation`,
  `missing`), the names of the top-level fields that differ, and the writer family those fields belong
  to (`summary`, `processing`, `live_title`, `user_edit`, `upload_attach`, `live_append`, `end`,
  `ownership`, `owes_a_pass` and so on). Field names only, never values.
- **Lock.** When the SDK re-runs the commit after a lock abort (`lock_retried`) or the commit gives up
  (`lock_failed`), the same record names every loaded document that was changed while the commit
  waited. When none was, it says `doc=unknown writer=no_visible_write`: the lock was held by a write
  that changed no value, by a transaction that only read these documents, or on a document the commit
  does not track.
- **The other side.** `mark_pending` counts what each mark changed (`armed`, `already_pending`,
  `skipped`, `failed`) and whether the mark itself met a lock (`clean`, `retried`, `failed`). A mark of
  a row that is already marked takes the row's lock and changes nothing, so the pass side cannot see
  it; a third of `mark_pending` writes in production were such writes on 2026-11-25.

Log lines: `event=v3_pass_collision outcome= lane= doc= writer= fields= phase= attempt= changed_ago=
waited= cause= more= trace_id=` and `event=v3_mark_pending_collision outcome= lock= attempts= seconds=
cause=`. A raced or retried line is INFO (10% kept in production: multiply by 10); a failed one is
WARNING (kept in full).

Counters: `omi_conversations_v3_pass_collision_total{outcome,doc,writer,lane}` and
`omi_conversations_v3_mark_pending_total{outcome,lock}`, both added to the backend-sync scrape keep rule
with `omi_conversations_v3_reconciles_total` as the denominator.

The live builder's commit is also metered (`database/conversations_v3_commit_cost.py`):
`omi_conversations_v3_builder_commit_total{outcome}` (`first_try`, `recovered`, `exhausted`, `error`) and the
extra attempts and re-read documents its lock retries cost
(`omi_conversations_v3_builder_commit_extra_attempts_total`, `..._extra_reads_total`), exported from
backend-sync. The share of `exhausted` is the share of passes left to the task queue's 30 s retry.

## Cost

When a pass loads a document it keeps one small token per top-level field (27 microseconds a document
on the local stack; about 3 ms for a 120-document pass). A commit that succeeds reads nothing more. A
commit that fails on a lock waits 0.25 s and reads the documents it had loaded once more, outside any
transaction: the documents of each failed commit once more, under 0.03% of reads at the failure share above.

## Rollout and rollback

No switch: the record is bookkeeping and cannot fail or change a commit (every report is guarded).
Rollback is a revert. No stored data changes; the `_v3_loaded_fields` key on a loaded row is never
written.

## Production readback

Share of thrown-away passes by cause, over an hour:
`sum by (doc, writer) (increase(omi_conversations_v3_pass_collision_total{outcome="raced"}[1h]))`.
Lock losses by cause: the same with `outcome=~"lock_.*"`. Share of marks that changed nothing and of
marks that met a lock: `sum by (outcome, lock) (increase(omi_conversations_v3_mark_pending_total[1h]))`.
For the field names, group `event=v3_pass_collision` lines on backend-sync by `doc`, `writer` and
`fields`.
