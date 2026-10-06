# Sync backfill UID sequencer environment boundary

The legacy `sync_backfill_sequencer` and `sync_backfill_pending` collections are production-only. `OMI_ENV_STAGE=prod` plus the rollout flag enables the sequencer. Every registry read and write rejects a non-production stage, including owner leases, pending scans, claim, begin, renew, finish, defer, and redrive. Sweep and wake are inert in dev. A sequenced or legacy backfill Cloud Task delivered to dev is ACKed as `foreign_stage` before reading the sync fence, a job, a run lock, or the registry. Dev admission still uses direct dispatch, but the non-prod backfill handler ACKs those deliveries; do not resume the dev queues until the rollout checks below are complete.

Sync routes require an explicit `OMI_ENV_STAGE` of `prod`, `dev`, `local`, or `offline`. A missing or unknown value logs `event=sync_runtime_stage outcome=invalid_config` and returns HTTP 503 before admission, worker delivery, sweep, or wake runs. Cloud Tasks retains the delivery for retry while configuration is corrected. The same strict check runs before any sync Redis key or Firestore collection name is chosen. This route-level gate keeps the rest of the shared backend available during a sync-stage configuration error.

Prod retains the existing Firestore collections and Redis names for jobs, run locks, epochs, backfill slots, direct reservations, and the existing quiet deadline. Non-prod sync Redis keys receive a stage prefix. Non-prod sync content ledgers and dead letters use stage-suffixed collections; prod keeps its current paths. This keeps live prod state readable during the prod mixed-revision window.

Rollout order:

1. Merge this PR. Keep the dev `sync-jobs` and `sync-backfill` queues and the dev sequencer Scheduler job paused while old dev revisions can serve requests.
2. Deploy the new code to dev `backend-sync` and `backend-sync-backfill` at **100% traffic**.
3. Verify no old dev revision serves traffic and no in-flight request remains on an old revision. Old code can still touch the shared prod registry until it is retired.
4. Only then resume the dev queues. Keep the dev sequencer Scheduler job paused: the sequencer is prod-only. Roll out prod after the dev retirement check.

This code does not change queues, Scheduler, traffic, or deploy state.

The old `quiet_remaining()` wrote a 30-minute deadline for **all UIDs** whenever its global mode key was anything other than `on`, including missing. The observed shared deadlines and exact 30-minute resumptions follow from that branch. The old mode key has no TTL. Only `note_direct_admission()` writes `off`; available aggregates show no corresponding dev uploads. Redis eviction/reset or an unobserved direct admission cannot be distinguished from the supplied aggregates. The new guard never reads or writes the mode key and never creates a global deadline. It honors an already-written prod quiet deadline until it expires and then waits only for a direct job registered for the same UID. A missing or evicted mode key is inert.

## Recovery

The roughly 1,240 dev-side `sync_staged_audio_expired` failures are *candidates*, not confirmed recoverable jobs. Dev attempted to download from its own staged-audio bucket, so that failure does not prove the prod object was absent. It also does not prove prod objects still exist: the bucket has a one-day lifecycle. We have not queried prod object metadata. The aggregate count alone lacks job IDs, UIDs, payloads, and blob paths. Claimed pending docs and finished owners no longer retain the payload. An operator must assemble a JSONL manifest from correlated dev failure logs and retained task metadata; do not put audio or transcript content in it.

Each line contains `job_id`, `uid`, `failure_origin: "dev"`, `origin_evidence: "dev_log"` (or `"job_marker"` for new jobs), `failure_code: "sync_staged_audio_expired"`, and the original Cloud Tasks `payload` with all worker fields. If the old Redis job has expired, also include `failure_at` from the dev log. The script checks the old Redis job when present and checks **only object existence metadata** for each prod staged path. It excludes genuine prod failures, content mismatches, missing objects, and jobs for which the origin cannot be proven. It does not download any bytes. New failures have `failure_stage` on the Redis job and durable dead letter. Historical failures lack that marker and require correlated dev log evidence.

From `backend/`, with separately authorized production credentials and a reviewed manifest:

```bash
OMI_ENV_STAGE=prod .venv/bin/python scripts/recover_dev_failed_sync_backfill.py --manifest /secure/path/dev-failed-sync.jsonl
```

The command above is a **dry run**. A later authorized recovery adds `--apply`. Apply creates a deterministic fresh job ID, claims the content ledger only if retryable, registers through the prod UID sequencer, and kicks it. If an attempt stopped after a step, rerunning checks the existing job and completes the remaining steps. A completed or busy content claim is skipped. The old terminal job is never rewritten. Review dry-run output, prod object retention, client re-upload status, and the new job's dispatch before any apply. Neither command was run against prod as part of this change.
