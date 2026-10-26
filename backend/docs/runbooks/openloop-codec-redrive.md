# Open-loop codec incident: safe sync redrive

The operator is `backend/scripts/openloop_redrive.py`. It defaults to a read-only
inventory under **ro-prod**, prints counts and closed reason tokens only, and
atomically appends per-job results/provenance to a **0600** private file beside
the input. The input must also be 0600 and outside the repository. No user API,
conversation read, transcript read, audio download, GCS copy or provider call is
part of planning. Apply belongs to the rollout lead, under **prod-operator**.

## Original sources, before reconstruction

Legacy `/v2/sync-local-files` jobs are Redis `sync_job` records, with a 24-hour
TTL, not Firestore job documents. `create_sync_job` retains identity, lane,
policy and status, but not the original request. `_compact_terminal_job` drops
Redis `partial_result`; terminal cleanup deletes its processed-path set.

| Field | Authoritative source used by the operator |
| --- | --- |
| `content_id` | Original custody/pending/active-owner/Cloud Tasks payload; cross-check Redis job and ledger key. Never compute a replacement from retained bytes. |
| `partial_result` | Original content ledger, including result references and fenced/enrichment receipts. |
| `processed_segment_ids` | Original content ledger. Keep the entire list. |
| Filenames, order, complete source set | Original payload `raw_blob_paths`; require every original staging object and its census generation. A bucket listing alone cannot prove the manifest. |
| Capture context | Original payload `source`, `should_lock`, `conversation_id`, `recording_session_id`, audio bounds, geolocation, device/platform, optional raw captures and capture-evidence claims, including explicit nulls. |
| Lane, capture trust/age, enqueue time, fence mode | Original payload, cross-checked against the Redis job. No laptop policy pinning or protocol downgrade. |
| Language | Admission does **not** store language in the task. The normal worker reads current transcription preferences; the tool never reads user profiles or invents an original language snapshot. |
| Policy | Original Redis admission policy; missing policy blocks. |
| Failed-segment phases and counts | Complete Redis terminal result errors/counts; a truncated or ambiguous outcome list blocks. |

Discovery checks `sync_redrive_required`, `sync_backfill_pending`, matching
`sync_backfill_sequencer.active_payload`, and the exact named Cloud Tasks in the
queues configured on traffic-bearing revisions. Conflicting original payloads
block. The dead-letter record is diagnosis metadata, not a payload. A scoped
ledger query by original job ID is only a discovery aid: normal claim release
removes that ID, so no match does **not** establish ledger absence. No unrelated
ledger scan is used. Attempts in legacy job metadata/logs do not retain a
second request manifest.

`database/jobstore` mirrors the **batch** store, is not this legacy admission
path, and its Postgres shadow refuses production. Its `jobs`/`results`/`docs`
tables are not an original-payload backup for this incident. No Postgres or
transcript data is read by the tool. Staging reconstruction is deliberately
blocked when original semantic fields are unavailable.

## Idempotency and refusal boundaries

The operation is keyed by the complete private `redrive_key` plus the original
`content_id`. A durable marker on that content ledger prevents a second dispatch,
including under a different operation key. Apply retains the **same job and
content identity**, acquires its original Redis run lock, compares the planned
ledger/checkpoints/usage markers transactionally, reclaims only an unowned
retryable ledger, and changes only execution state and the operator marker.
It preserves all successful checkpoints, admission policy and usage markers.
The queued job hydrates its partial result from that ledger.

A deterministic named task goes through `enqueue_sync_job_redrive` and the
ordinary production routing/OIDC/intake pipeline. The ordinary coordinator
computes segment IDs and skips durable successful siblings before STT. Content
identity continues to key usage accounting. No direct conversation writes or
separate usage implementation are introduced. A lost create acknowledgement
can only retry the same task name for 30 minutes; after that it blocks rather
than outliving Cloud Tasks' name tombstone. A worker-started or dispatched
operation is never reset for a second operator attempt.

Ready requires an existing, policy-pinned, direct Cloud Tasks job using the
active ledger fence, no run/UID owner, complete original payload, durable
checkpoints, and unchanged staging generations. Sequencer-owned, expired,
legacy-fence, conflicting, changed or incomplete jobs block. Apply rereads
metadata and verifies **every traffic-bearing revision** of backend-sync,
backend-sync-backfill and backend-integration reports an
`OMI_BACKEND_RELEASE_SHA` containing `87083b7b9c298c915de89ff6e8054eb94c4e7661`.
Unknown Git ancestry or rollout identity blocks. Dispatch URLs must match the
canonical Cloud Run services inspected by the guard.

`finalize_legacy` is a separate, pre-existing `bridge_receipt` failure class.
Its intake may already be persisted without a processed-segment checkpoint.
Re-transcribing that segment is unsafe; the tool emits
`finalize_receipt_replay_required` once its original payload/checkpoints can be
read. Receipt-only repair evidence is required before its canary can proceed.
A persistence-population job whose terminal errors also include finalize
failure is refused for the same reason. Terminal errors are truncated to ten
entries: if the retained outcomes cannot cover every failed segment,
`failure_manifest_incomplete` blocks the job. Its durable processed-ID set must
also cover every successful sibling; a missing marker blocks rather than
re-transcribing already-persisted work.

## Exact commands and canary checks

Run these from the reviewed task worktree. For a complete readiness plan, use
the approved runtime/network with its existing Redis bindings (`REDIS_DB_HOST`,
port/password as applicable); `--runtime-redis` issues GETs only. Without that
flag, otherwise eligible jobs report `runtime_probe_required`. Do not fetch
secrets or borrow another worktree's environment. Fetch current Git ancestry
before apply. The private output defaults to the input stem plus
`.redrive-results.json`; never print it or attach it to a PR.

```sh
PRIVATE_INPUT=/Volumes/Ephemeral/scratch/two-lane-lead/openloop-valueerror-jobs-2026-10-26.json
source ~/.local/bin/gcp-agent-env.sh ro-prod
OMI_ENV_STAGE=prod PYTHONPATH=backend backend/.venv/bin/python backend/scripts/openloop_redrive.py \
  --input "$PRIVATE_INPUT" --runtime-redis
```

Only the lead runs the following **prod-operator** commands, in order, after a
read-only plan reports ready. The present inventory is blocked; do not advance
past the finalize canary until receipt-only recovery is resolved.

```sh
git fetch origin main
source ~/.local/bin/gcp-agent-env.sh prod-operator
OMI_ENV_STAGE=prod PYTHONPATH=backend backend/.venv/bin/python backend/scripts/openloop_redrive.py \
  --input "$PRIVATE_INPUT" --runtime-redis --apply --population finalize_legacy --limit 5
# Check this step completely before continuing.
OMI_ENV_STAGE=prod PYTHONPATH=backend backend/.venv/bin/python backend/scripts/openloop_redrive.py \
  --input "$PRIVATE_INPUT" --runtime-redis --apply --population persistence_suspected_open_loop --limit 20
# Check this step completely before continuing.
OMI_ENV_STAGE=prod PYTHONPATH=backend backend/.venv/bin/python backend/scripts/openloop_redrive.py \
  --input "$PRIVATE_INPUT" --runtime-redis --apply --population finalize_legacy --limit 193
OMI_ENV_STAGE=prod PYTHONPATH=backend backend/.venv/bin/python backend/scripts/openloop_redrive.py \
  --input "$PRIVATE_INPUT" --runtime-redis --apply --population persistence_suspected_open_loop --limit 1089
```

Limits select a fixed prefix of the latest dry-run's ready population in input
order. Repeating a canary targets the same jobs and makes no new dispatches;
the larger limit includes that prefix, whose markers skip it. Apply stops at
the first changed precondition or uncertain dispatch. The same reviewed plan
can resume its own prepared marker; unrelated metadata changes require a fresh
dry run. A plan digest is a consistency check, not authorization.

After **each** canary, check privately under **ro-prod**: every selected job and
content ledger finalized successfully, expected result references exist, no
duplicate conversation/segment rows were added, prior successful siblings and
content-keyed usage were reused, and `value_error_reason=none` for the recovered
jobs. Check runtime logs/counters for new persistence/finalize errors. Replay
the identical canary command and verify zero new tasks, provider work, rows or
usage. An enqueue acknowledgement alone does not establish recovery. Stop
expansion on any failure or incomplete check; do not reset markers/checkpoints,
release ownership manually, or undo completed rows/usage. Stopping the operator
prevents further dispatches; accepted work follows normal worker ownership.

## Read-only census, 2026-10-26

The supplied file contains **1,282** rows: **1,089** persistence candidates and
**193** legacy-finalize candidates. Its actual header has **604 failed / 678
partial_failure**; the RCA's earlier 1,271-job window had 492 / 779.

The ro-prod dry run without a Redis probe reports **0 ready**, **1,282 blocked
`task_payload_read_denied`**. This tier lacks `cloudtasks.tasks.get`; no access
change or apply was attempted. All 1,282 custody and pending records were
absent; 132 dead-letter records contain metadata only. Ten candidates share a
UID with a sequencer owner, but none has a matching original active payload.
No ledger could be joined by the original job ID. The serving-commit guard did
not verify the whole rollout at census time; a subsequent ro-prod metadata
check verified the fix on all three services. Payload/checkpoint readiness is
still blocked. These findings do not prove that the original payload or ledger
no longer exists everywhere.

For the **four unknown-retention jobs**, the census supplies zero staging or
archive object names and no matching durable identity was found. Live GCS
bucket metadata (ro-prod, no downloads/copies) shows **zero lifecycle Delete
rules** on `syncing-local`; `omi-private-cloud-sync` deletes only `playback/`
after 30 days. Its `chunks/` rule changes storage class rather than deleting.
No source-prefix lifecycle deletion deadline is established. An exact earliest
deletion time for the four unlocated jobs is **unknown**, not an asserted
retention guarantee. A broad metadata-name search was stopped; it is not used
as evidence of object absence.
