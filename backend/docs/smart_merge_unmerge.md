# Administrative smart-merge undo and audit

`utils.conversations.smart_merge.unmerge_conversation(uid, donor_id, *,
force=False, dry_run=True)` is an admin module operation, with no public route.
From `backend/`, use the worktree's Python environment and backend import root:

```bash
PYTHONPATH=. .venv/bin/python scripts/smart_merge_unmerge.py --uid USER_ID --donor-id DONOR_ID
PYTHONPATH=. .venv/bin/python scripts/smart_merge_unmerge.py --uid USER_ID --donor-id DONOR_ID --apply
```

The default performs transactional reads and no writes or external effects.
Output contains only ids, counts and closed eligibility reasons. `--force`
overrides only the survivor's title/manual-speaker curation guard. Merge admission
forbids those fields, so their presence is treated as post-merge curation; legacy
rows do not retain title-edit timestamps. Empty user-set titles count too.

Admission requires a retained donor tombstone, its completed sync-bridge cleanup
receipt, a live completed survivor, no refresh owed or active refresh lease, and
a valid ledger suffix. Selecting the last donor restores one conversation.
Selecting a middle donor restores it and every later fragment as separate
conversations; every selected donor must pass admission. The transaction rereads
all rows, checks the preview's smart-merge and content revisions, removes segments
by original id (time windows for missing ids), truncates the ledger, recomputes
the end time, and advances both survivor revisions. Donors retain their original
content and audio and become visible with `smart_merge.role=unmerged`; that marker
prevents them becoming automatic donors again.

A persisted `smart_merge.unmerge_pending` receipt blocks new absorbs until the
follow-up completes. It coordinates a leased replay: remove only the donor's
copied audio filenames from the survivor; rebuild audio metadata/cache; refresh
the survivor using its existing lease/revision fence (including wholesale memory
replacement); process each donor with `SMART_UNMERGE` through the normal initial
processing path, bypassing first-open deferral and retaining the restored row.
Embedding, audio and search projection are explicitly rebuilt before each donor
receipt is checkpointed. The normal processing path also owns tasks, memories,
goals, folder assignment, integrations and webhooks. As on ordinary initial
processing, some external effects are background/best-effort; a crash before a
checkpoint can replay them. The receipt is a convergence protocol, not an
exactly-once guarantee across external systems. Repeating `--apply` resumes a
pending follow-up; after completion it returns `already_unmerged` without effects.
A crashed owner's lease expires after ten minutes.

Undo cannot recover earlier survivor tasks/events/apps, task completions, speaker
relabels, prior protection/private-sync flag values, or chat answers given while
merged. Current protection/sync settings stay in place. Regeneration reconstructs
derived content from the restored transcripts rather than restoring a snapshot.

## Audit ownership and retention

Every committed absorb atomically writes
`users/{uid}/smart_merge_audit/{donor_id}`. Its closed projection contains only
donor/survivor ids, score, threshold, question version, served model when supplied,
gap, merge time, mode, source and `expire_at = merged_at + 60 days`. It never stores
transcript, summary, prompt, title, speaker names or arbitrary decision fields.
Undo adds `unmerged_at` and `unmerge_actor=admin` in the same transaction; old
merges reconstruct this projection from the retained donor decision when needed.

The collection is a sibling of conversations and is excluded from conversation
and retained-donor cascades. Whole-account deletion still owns the user's entire
subtree. The existing deny-all `users/{uid}/{collectionId}/{document=**}` rules
already cover this server-owned collection. Access is by document id only: no
compound query or composite index is introduced. The generated Firestore index
registry currently declares no enabled TTL policies. `expire_at` records the
60-day retention boundary; enabling its collection-group TTL is an operator step
before relying on automatic expiry, and is not performed by this code change.

## Measurements

`smart_merge_unmerge_total{outcome}` uses only `ok`, `ineligible`, `dry_run`,
`error` (a completed no-op counts as `ok`).
`smart_merge_survivor_deleted_total{age_bucket}` measures successful user/source
deletes with a smart-merge ledger, using `lt_1h`, `lt_24h`, `lt_7d`, `gte_7d` since
the last merge. New survivors retain `last_merged_at`; legacy survivors read the
last retained donor timestamp before purging it. Measurement failures never
block deletion. Neither counter has a user, conversation or model-text label.
