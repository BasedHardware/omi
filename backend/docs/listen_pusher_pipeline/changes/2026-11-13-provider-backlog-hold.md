# Provider backlog stays held; only fresh provider rows commit (2026-11-13)

## What happened

`2026-11-13-provider-merge-membership.md` shipped to `backend-integration` at 11:36Z. It worked as
written, and the "known effect" in it was far larger than expected:

- Every active provider owner started draining its own already-transcribed backlog. About 230,000
  rows an hour left `result_ready` (about 170,000 at catch-up depth 4, about 125,000 at depth 1).
- Projection runs one walker per owner and takes owners from one FIFO queue
  (`projection_drain.py`), with no class for fresh work. Thousands of backlog owners joined that
  queue. Of results committed 10-20 minutes earlier, 35% were still unprojected, and 45% of those
  whose capture was under an hour old; before the deploy it was about 0.2%.
- The owner drains ran in the serving process and took its CPU. `backend-integration` was already
  at its instance ceiling; enrichment and provider-STT requests completed fell by about half until
  the ceiling was raised.
- Fresh provider units admitted before the admission stamp reached `backend-sync` queued behind
  their owner's backlog, so few of them were delivered either.

## Change

`BATCH_PIPELINE_PROVIDER_BACKLOG_RELEASE_ENABLED` (off unless `true`). While it is off, the
ordered merge does not commit a provider-route catch-up row: one with no `fresh_capture` (admitted
before the stamp) or with `fresh_capture` false (admitted more than `FRESH_CAPTURE_LAG_SECONDS`
after capture). The row stays `result_ready` and `merge_pending`.

- An owner's fresh provider rows still commit, through the existing fresh-first path, ahead of the
  held backlog. The fresh probe now also runs when the catch-up depth hold is switched off.
- The hold writes no `merge_holds` marker and adds no owner to the in-memory re-offer set, so
  maintenance does not re-drain held owners.
- A recovered unit's own release is unchanged.
- GPU-route catch-up rows are unchanged.

With `BATCH_PIPELINE_PROVIDER_MERGE_MEMBERSHIP_ENABLED` on again, the result is: fresh provider
units are delivered, and the projection queue sees only the provider route's fresh volume.

## What is not delivered while it is off

- The backlog transcribed since 5 Nov.
- New provider uploads that arrive more than 10 minutes after capture (13% of provider admissions
  in an hour sampled on 2026-11-13). They were not being delivered before today either.

Both wait for the metered release: a job with its own rate setting that offers backlog rows at a
pace projection can absorb, after the projection owner queue gives fresh work its own class.
Staged results are deleted at 30 days, so that job has to run before 2026-12-05 for the oldest rows.

## Rollback

Set `BATCH_PIPELINE_PROVIDER_BACKLOG_RELEASE_ENABLED=true` to restore release paced only by the
catch-up depth hold (do this only with projection headroom). Set
`BATCH_PIPELINE_PROVIDER_MERGE_MEMBERSHIP_ENABLED=false` to stop provider merge membership entirely.

## After review (same day)

- The hold does not depend on `BATCH_PIPELINE_PROVIDER_MERGE_MEMBERSHIP_ENABLED`. Rows stamped `ready_at` while that switch was on kept committing through the head wait after it was set to `false` (3,435 day-old provider rows in a 2-minute window at 13:00Z).
- The fresh probe runs for a held or unready provider backlog head at any depth setting.
- While the fresh query backs off after `FailedPrecondition`, a held owner is not probed and nothing falls back to the plain order.
- A held head at the depth cap writes no `merge_holds` marker.
- Limit: a GPU-route catch-up row behind a held provider row of the same owner waits with it until the metered release.
