# 2026-11-17: legacy sync transcription deleted (plan C C9-C11)

Legacy sync has been dark in prod since 2026-11-04 (ramp revision 56). This change deletes the code that dark mode
already stopped serving; uploads keep the batch path they use today.

## Deleted

- `utils/sync/pipeline.py`, the legacy decode → VAD → STT → merge coordinator. Its cap-hold segment core
  (`process_segment`, VAD retrieval, staging helpers and the stale-job finalizer) moved verbatim to
  `utils/sync/legacy_segment_core.py`, with the minimal-redrive branches removed.
- The per-owner backfill sequencer (`utils/sync/uid_sequencer.py`, `database/sync_backfill_sequencer.py`,
  owner/staged prefetch, backfill cutover/order, `config/sync_owner_concurrency.py`), legacy redrive
  (`database/sync_redrive.py`, `redrive_policy`, `minimal_redrive`), retry hygiene and staging custody.
- The backfill pull worker (`utils/sync/worker_*.py`, `routers/sync_worker.py`, the `sync-backfill-worker`
  chart, image and deploy file), which never left dark.
- Routes `/v2/sync-backfill-sequencer/sweep` and `/wake`. `/v2/sync-jobs/run` now serves only `sync_reprocess` and
  `batch_final_pass` tasks and acknowledges (200 `legacy_retired`) anything else.
- The legacy admission branch, legacy job creation, Cloud Tasks enqueue and inline pipeline in
  `/v2/sync-local-files`. Content legacy already owns is still answered by the legacy-dark fence.
- The Phase 0A replay harness and its advisory workflow job.

## Contract changes

- `utils.sync.legacy_dark.current_mode()` always serves `dark`. Neither the `_ramp` document nor a read failure can
  select `on`; rollback is an image redeploy.
- Retired env: `SYNC_BACKFILL_UID_SEQUENCER`, `SYNC_BACKFILL_ORDER*`, `SYNC_BACKFILL_OWNER_CONCURRENCY*`,
  `SYNC_BACKFILL_OWNER_REPAIR_WINDOW_SECONDS`, `SYNC_BACKFILL_RETIRE_EXPIRED_AT_CLAIM`, `SYNC_BACKFILL_WORKER_*`,
  `SYNC_DURABLE_REDRIVE_GUARD`, `SYNC_LEGACY_COMPLETION_CONVERGENCE`, `SYNC_INLINE_BACKFILL_CONCURRENCY`,
  `SYNC_MINIMAL_REDRIVE_ENABLED`.

## Kept

Front door, status polling (including `database/sync_jobs.py`, dead letters and `completed_status` for jobs created
before the switch), playback, audio merge, batch RPC, cap-hold recovery and the `backend-sync` /
`backend-sync-backfill` services (C7 and the dream-agent rehome still route work to them).
