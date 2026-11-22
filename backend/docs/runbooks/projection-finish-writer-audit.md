# Projection finish writer evidence

Source audit for SCA-2024 and PR #25225, 2026-11-13. Writer implementation
audited at `a64189c891a4632b0d82422b1b843b5343aa8579`. This is code evidence,
not a claim that the new binary is deployed on the 37 listen pods or that GMP
has been verified. No production access, writes, deployment, or flag changes
were performed for this audit. All production rolls belong to the rollout lead.

## Backend-listen: request paths and flags

The canonical async flag is `BATCH_PIPELINE_ASYNC_PROJECTION_ENABLED`
(`config/policy/stages.py:95`); “ASYNC_PROJECTION” in the rollout discussion is
shorthand. The listen chart explicitly sets that flag true and
`BATCH_PIPELINE_SERVING_ENABLED=false`
(`charts/backend-listen/prod_omi_backend_listen_values.yaml:181,225`).

The image launches `main:app` (`Dockerfile:63`). Startup calls
`start_serving_from_env` (`main.py:247`). With the projection pump also off,
serving=false makes that function return without starting its recurring task
(`utils/batch_pipeline/serving.py:405`). **This does not disable request-driven
projection.** `serving_for_stage` constructs a `Projector` without checking the
serving flag (`serving.py:374`).

Router exposure is controlled separately by `OMI_ROLE`; its default is `all`
(`app_roles.py:156`). The listen values file does not set OMI_ROLE. The following
is the conservative request-reachability inventory for that default, not a claim
that ingress or OIDC permits each path on the running pods. If a deployment
selects realtime-only routing, worker RPCs below are not mounted there.

| Request | Reachable batch-result transition | Clock evidence |
|---|---|---|
| WebSocket `/v4/listen`, `/v4/web/listen` | No direct persisted/ready result transition. Both enter the listen session (`routers/transcribe.py:191,246`); listen modules contain no batch-result state writer or Projector/ProjectionStore construction. Conversation capture, transcript persistence and recording registration are distinct from batch-result projection; dispatched tasks execute at their configured worker target. | No direct finish-state write to stamp. Shared conversation assignment only invokes a batch receipt when an explicit `after_assign` callback is supplied (`database/conversations.py:4605,4706`); the batch callbacks are supplied by `Projector` (`projection.py:852,1036`), not by these WebSocket handlers. |
| POST `/v2/batch-pipeline/reconcile` | `reconcile_async` -> `Serving.reconcile` -> maintenance/release and `Projector.sweep`; may persist and ready results, including follow-ups. | All writer sites in the next table. Serving=false is not checked by this handler. |
| GET `/v2/batch-pipeline/metrics` | Unless pump/read-only-metrics mode selects refresh only, calls `reconcile_async(periodic=True)`, which can execute the same writers. | `routers/batch_pipeline.py:292`; same shared writers. A metrics request must not be assumed read-only from serving=false alone. |
| POST `/v2/batch-pipeline/recover-quarantine` | On recovered/reconciled outcome, owner reconciliation -> `project_owner`, then async follow-ups. If the owner-only switch is off, reconciliation may also sweep. | `routers/batch_pipeline.py:183`; `serving.py:130,146,178,196`; shared session/store writers. |
| POST `/v2/batch-pipeline/provider-stt/run` | Settled-unit hook -> `wake_owner_merge` -> `_drain_owner` -> `drain_settled_async` -> `_reconcile_owner` -> `project_owner` and follow-ups, when membership/owner-chain gates admit it. | `routers/batch_provider_stt.py:68,76,92,110`; same session/store writers. |
| POST `/v2/batch-pipeline/complete` | `Serving.complete` -> `drain_owner` -> `OrderedMerge.commit_next`; creates pending results, not persisted/ready. | `serving.py:111,119`; `utils/batch_pipeline/merge.py:371`. Later projection uses shared writers. |
| Other private batch RPCs | Pull/heartbeat/fail/authorize/GPU-idle do not run projection. Redrive/requeue changes scheduling/recovery state. Shadow-project uses a discarded planning transaction, not a serving receipt commit. Shadow-recover handles shadow recovery, not a persisted/ready serving receipt. | `routers/batch_pipeline.py`; `utils/batch_pipeline/shadow_projection.py`; complete source census below. |

These are all direct production callers of `serving_for_stage`: the private
batch router, provider-STT router, and serving module itself. The only production
`Projector` construction sites are `serving_for_stage` and the operator projection
repair script. The only `ProjectionStore` construction outside Projector is the
staging redrive script's release path. This closes the request-side entrypoint
inventory without assuming a disabled periodic loop disables writers.

## Persisted/ready writer closure

Paths below are relative to `backend/`. `projection_finish_state_fields` returns
due-now plus step=0 for persisted/ready **without reading any flag**, and deletes
the clock on other state transitions. The whole-document helper
`projection_finish_entry_fields` likewise stamps finish states without a flag
and emits no delete sentinel (`database/batch_pipeline_projection_finish.py:26,40`).
Thus backend-listen's async policy and disabled serving loop cannot suppress a
clock on a transition executed by the new code.

| Writer / state transition | Same-write clock evidence |
|---|---|
| `ProjectionSession.persist`: ordinary assignment, supersession, multipart summary and ordinary receipt | `database/batch_pipeline_projection_session.py:505,517` spread `projection_finish_state_fields` next to the state assignment; the receipt can be persisted or ready. |
| `ProjectionSession.write_receipt`: ordinary ready acknowledgment and multipart completion | `batch_pipeline_projection_session.py:99,124` use the shared helper. The quarantined summary branch at 116 retires the clock. |
| `ProjectionStore.ready` and deleted-output settlement | `database/batch_pipeline_projection.py:195,224` delegate to `session.write_receipt`; no alternate unclocked ready write. |
| `ProjectionStore.hold_for_quarantine`: already-settled sibling wake | `batch_pipeline_projection.py:514` writes ready plus shared clock in one update. |
| `ProjectionStore.complete`: sibling wake after durable completion | `batch_pipeline_projection.py:775` writes ready plus shared clock in one update. |
| `ProjectionReleaseStore.release`: ghost ready repair | `database/batch_pipeline_projection_release.py:293` writes ready, cohort, and shared clock in one update. Ordinary release resets pending at 345 and retires the clock. |
| Privacy refusal resume: restore saved persisted/ready state | `database/batch_pipeline_projection_privacy.py:139` immediately adds `projection_finish_entry_fields(saved['state_before'], now)` before the whole-document set. Privacy hold removes both fields and writes quarantine_held. |
| `reconcile_batch_projection_ghost_holds.py`: operator CAS repair to ready | `scripts/reconcile_batch_projection_ghost_holds.py:80` includes `projection_finish_state_fields('ready', time.time())` in the guarded update, independent of the read flag. |
| Backfill maintenance | `database/batch_pipeline_projection_finish_backfill.py:61` stamps only missing clocks, preserves existing clocks, and never changes state. |

The remaining result-state writers create **pending** (`merge.py`, session reset,
ordinary release) or **erased** (`database/batch_pipeline_purge.py`) obligations,
or **completed** (`ProjectionStore.acknowledge`). They do not introduce a finish
state without a clock. Privacy whole-document hold/restore explicitly removes
stale clocks before rebuilding the applicable finish-state fields. Database
store/shadow/Postgres adapters copy supplied rows; they do not manufacture an
additional ready/persisted transition. Existing copied historical rows remain
part of the mandatory stamping pass.

## Cloud Run, jobs, and operator scripts

The Cloud Run backend, sync, backfill and integration services share the above
main/router implementation (`runtime_images.json` service registry). A disabled
recurring sweep on a service is not proof it cannot write finish state.

The registered standalone Cloud Run job entrypoints are messaging maintenance
(`scripts/messaging_operations.py`), x-connector sync (`modal/x_connector_sync_job.py`),
frame-request retention, day-3 re-engagement and notifications. None defines a
batch-result projection_state writer or constructs Projector/ProjectionStore.
The isolated sync-backfill `utils.sync.worker_job` and record-seal worker/sweep/
repair entrypoints also introduce no direct finish-state writer: they process
or admit work and leave result projection to the shared worker RPC/serving paths.
The GPU batch runtime constructs `Pump(Scheduler(...))` directly
(`diarizer/batch_pipeline_runtime.py:256`): publication calls Scheduler.complete
and OrderedMerge produces pending results. Its optional projection callbacks
are not supplied by this runtime (`utils/batch_pipeline/pump.py:85,87,861,927`).
It does not implement a separate persisted/ready receipt writer. This is distinct
from the HTTP worker-complete path, which also only merges pending results.

| Operator entrypoint | Coverage |
|---|---|
| `scripts/batch_pipeline_projection_repair.py` | Constructs the real Projector at 84; assignment and follow-up transitions use the writer table above. |
| `scripts/redrive_staging_inputs.py` | At 154 calls `ProjectionReleaseStore(ProjectionStore(store)).release`; any ghost-ready transition uses the same unconditional helper. |
| `scripts/reconcile_batch_projection_ghost_holds.py` | Direct CAS ready update is clocked at 80. Covered with both read-flag values by unit tests. |
| `scripts/batch_pipeline_projection_finish_backfill.py` | Bounded maintenance-only clock writer; durable page checkpoints and completion marker. No new result state. |

## Reproduce and interpret the evidence

Run from the repository root (read-only source census; no cloud credentials):

```bash
rg -n 'projection_state' backend/database backend/utils backend/routers backend/services backend/scripts backend/modal backend/diarizer backend/pusher -g '*.py'
rg -n 'Projector\(|ProjectionStore\(|serving_for_stage|ProjectionSession\(' backend/database backend/utils backend/routers backend/services backend/scripts backend/modal backend/diarizer backend/pusher -g '*.py'
rg -n 'after_assign' backend/database/conversations.py backend/utils/batch_pipeline/projection.py backend/routers/listen
```

Behavioral evidence is in `tests/unit/test_batch_projection_finish_backoff.py`
(flag-off listen-host clock helper; real ready/retirement transactions with flag
true and false), `test_reconcile_batch_projection_ghost_holds.py` (operator ready
clock with both flag values), and `test_batch_projection_finish_backfill.py` plus
the Firestore emulator suite (checkpoint/version/failure/concurrency contracts).

This satisfies the source-writer inventory. Before re-enable, the rollout lead
must still confirm the admitted revision on **all** writers (including the 37
listen pods and any operator/job image), the completed stamping marker and zero
missing clocks, plus merged/deployed #25145 / SCA-1799 and **nonzero GMP values
for both** finish-read and finish-completed counters. A local passing test or an
open code PR does not satisfy those deployment/measurement conditions.
