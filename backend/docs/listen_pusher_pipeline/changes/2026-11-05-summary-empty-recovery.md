# Recover exhausted summaries after transcript changes

Exhausted first-summary debt now reopens when sync assignment, finalized-record replacement, shared live
append, or smart-merge absorption advances `sync_content_revision` with new transcript content. The shared
`summary_delivery.rearm_on_revision_change` transition clears
`empty_output_exhausted`, resets empty failures, and restores a due time inside
the transaction that writes the new transcript. This uses the existing content
revision and also handles previously exhausted rows without migration. Replays
without new speech remain blocked. Original acceptance time is preserved.

The conversation retains `summary_empty_rearms` across outbox regeneration.
Only two lifetime re-arms are allowed: three empty outputs per cycle, nine in
total. Exhausting the last cycle records `empty_output_lifetime_exhausted` on
both rows; further revisions cannot reopen it. Debt preparation, eligibility,
result persistence, and outbox admission recognize both terminal reasons.

Revision-writer audit: the shared transition runs in each transaction that
persists changed survivor speech (normal sync assignment, batch final-record
replacement, live segment append, and smart-merge absorb). Redirect-only bumps
in assignment, smart-merge donor tombstones, and merge-ancestry repointing
remain terminal. Minimal redrive copies the revision without advancing it.
Smart merge uses its already-read survivor snapshot before the write codec;
this keeps the counter, transcript revision, and deadline atomic. The
smart-merge query review pin is refreshed: the hook mutates the payload only,
and existing discarded-barrier query drivers still cover every query.

The existing bounded debt repair transaction uses the conversation's current
eligibility to reopen its exhausted enrichment outbox and reset that outbox's
empty counter. It keeps privacy, active-lease, age, manual-edit and ownership
fences. No new flag or retry loop is introduced.

Empty-output recording now distinguishes a stale outbox lease, an owned empty
result, exhaustion, and a changed conversation owner. Owner changes are recorded
on the outbox and deferred through existing custody scheduling in both handlers,
without consuming empty-output or callback-pending attempts. A replaced worker
cannot change the conversation or its summary.

Contract: [summary guarantee](../../listen_pusher_pipeline.mdx).
Hermetic coverage: `tests/unit/test_summary_empty_recovery.py`,
`tests/unit/test_conversation_smart_merge.py`, `tests/unit/test_lifecycle_state_table_writers.py`,
`tests/unit/test_enrichment_route.py`, and `tests/unit/test_sync_reprocess_coalesce.py`.
No production reads, writes, migration, merge, or deployment are part of this change.
