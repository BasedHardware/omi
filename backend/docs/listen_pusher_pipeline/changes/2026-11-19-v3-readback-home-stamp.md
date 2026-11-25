# 2026-11-19: multi-batch v3 projection readback ignores the Home commit stamp

## Why

`home_feed_writer.augment_home_writes` runs at the Firestore Commit boundary. It stamps a fresh random
`home_source_version` on every conversation write, plus `home_content_invalidated` when the write
touches transcript fields.

`database/conversations_v3.commit_projection` splits a large projection into batches. After each
non-final batch it reads its own writes back:

- Derived rows: it compared every written field with the stored document. A row rebuilt from a prior
  carries the prior's `home_source_version`, so the hook's fresh stamp made every rewritten row look
  externally changed and the readback raised `source_changed`.
- Recordings: the readback treated the same stamp as a change to every recording.

So every reconcile pass for an owner whose projection needed more than one batch did the following:

1. Committed batch 0.
2. Raced on the readback.
3. Answered `raced` and woke again a minute later.

The final batch never landed, so the owner never cleared its pending markers or its builder park. One
product owner rewrote the same 151 documents about every 70 seconds. The rewrites bumped each row's
`update_time`, so in-flight notes kept losing their persist fence and ended `attempts_exhausted`.

## What changed

- `database.home_feed_fields.COMMIT_STAMPED_FIELDS` (moved out of `home_feed_writer` by #25739) names the fields the hook stamps. Both readbacks ignore
  them. Any other change between batches still conflicts.
- Speech appended to a recording is still treated as moved, not as a conflict.
- A readback conflict now logs `v3 projection readback changed kind=<derived_row|recording> batch=<i>
  fields=[...]`. It logs field names only.
- `tests/unit/test_conversations_v3_commit_readback.py` emulates the hook and covers:
  - a commit that splits into at least two batches reaches the final batch;
  - an external change to a row, or to a protected recording field, still conflicts;
  - live speech is still moved;
  - the stamped-field set equals what `augment_home_writes` adds, for both write shapes.

## Rollout

No flag. Deploying unwedges affected owners on their next pass. Rows that already ended
`attempts_exhausted` remain `summary_retryable`.
