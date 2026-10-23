# Local Sync Cloud Tasks stack gauntlet

Run this loopback-only gauntlet when changing Sync v2 admission, Cloud Tasks
dispatch, worker ownership/retry, staged-audio handling, or the Sync content
ledger:

```bash
npm run test:sync-cloud-tasks-stack:emulator
```

It needs the backend virtual environment, root Node dependencies, Redis, and
Java 21+ for the Firestore emulator. Run one scenario family with
`backend/testing/sync_cloud_tasks_stack/run.sh --only sync` or
`--only batch` (the default, `--only all`, runs both; CI runs both). The runner gives Firebase a fresh
loopback port, starts a private loopback Redis, and starts **separate**
admission and worker ASGI processes. Their environment is allowlisted and has
an empty home/cloud configuration; it carries no cloud credentials, provider
keys, proxies, or developer Redis/Firestore endpoint. Every child process
installs the same guard (`isolation.py`) before backend imports and rejects
non-loopback DNS and socket traffic. Each scenario uses a unique synthetic
user namespace, so concurrent gauntlet invocations cannot share local Sync
workspace material.

## Retired legacy admission contract

The Sync scenario requests a real signed capture manifest, then uploads framed
PCM to the real v2 route. After C9 it requires HTTP409, the existing client retry
code, no job ID and a cooldown hint. It verifies that no legacy task, provider,
job, storage or worker event is created and no speech allowance is consumed.
Sanitized positive admission evidence is required; every emitted JSONL stream
still passes the same UID/transcript sentinel checks.

The former scenarios began by creating a new legacy job through this route, so
they retire with legacy admission rather than requiring the deleted behavior.
Retained worker ownership/retry/held-recovery unit contracts remain, and the
batch scenarios below continue to exercise the new processing/recovery path.
This local replay does not certify production batch coverage, recovery visibility
or overlapping phone/Watch S1 behavior; those remain rollout gates.

Only external/provider leaves are replaced. No cloud credentials or live endpoints
participate. With `--keep` or `--state-dir`, the runner retains process logs and
sanitized evidence; paths are resolved before child processes start.

## Batch-lane scenarios

`batch.py` runs the real batch pipeline across four processes over the same
emulator and a private Redis (stage `dev`, namespace `batch_pipeline_dev`):

| Process | Real | Replaced |
| --- | --- | --- |
| admission ASGI (`BATCH_PIPELINE_ENABLED`, 100%) | `/v2/sync-capture-manifest`, `/v2/sync-local-files` → `accept_upload`, PCM decode, AES-GCM artifact staging, intake/job/ledger rows, status route | GCS → filesystem bucket with object generations |
| serving ASGI (`BATCH_PIPELINE_SERVING_ENABLED`, recovery `on`, all admitted) | `main` lifespan `Serving` loop, `/v2/batch-pipeline/{authorize-compute,reconcile,recover-quarantine}` behind the production OIDC dependency, projection, quarantine dispatch via `enqueue_named_task`, lease recovery | paid legacy STT leaf (counted, PCM-hash attributed); Google token verifier (one exact local token per audience/identity) |
| batch worker (`batch_worker.py`) | `batch_pipeline_runtime.run_process`: SIGTERM handling, `Pump(Scheduler(FirestoreStore))`, heartbeats, compute-admission RPC, ordered merge, `PipelineWorker`, artifact decrypt/encrypt | CUDA models → fake words/diarizer/model-VAD leaves; CUDA sync/memory probe no-ops; lease/heartbeat compressed to 8s/2s |

Recovery tasks go through the strict recorder (serving-origin HTTPS URL,
OIDC binding, opaque `{stage, segment_id}` body, intent-bound name) and the
runner delivers them to the serving process over loopback. The runner acts as
the reconcile scheduler by calling the real `/reconcile` route while it polls
status at 1s (the production poll limiter rejects faster polling).

Scenarios: happy path with exactly-once metering; empty ASR → quarantine →
one paid recovery despite duplicate/late deliveries (the status route reports
`processing` with a nonzero `poll_after_ms` while recovery is held, prepared or
running, with zero projected completion and no result/error even after a killed
paid call whose outcome is unknown, then `completed`); a failing paid recovery settles `failed_held` and
polls `failed` with `poll_after_ms: 0` without re-paying; worker SIGTERM drain;
worker SIGTERM + SIGKILL after grace → lease expiry → replacement completes;
serving SIGTERM during the paid call → graceful settle → replacement never
re-pays; serving SIGKILL during the paid call → intent stays `running`, never
re-paid; privacy fence during compute and before paid recovery; a
three-capture single-owner burst; and two concurrent worker replicas (the prod
replica count) draining a split burst, independent owners and one empty-ASR
capture with once-only compute, capture-order commits and one paid recovery. Provider behavior per owner comes from
`batch-control/*.json` in the state directory; defaults come from
`OMI_BATCH_STACK_WORDS_{LATENCY_MS,EMPTY_RATE,FAILURE_RATE}`,
`OMI_BATCH_STACK_PAID_LATENCY_MS`, and `OMI_BATCH_STACK_CAPACITY`.

Batch admission receives a serialized `BatchUnitPolicy` from the coordinator's
`batch-control/policy.json`; the admission seam supplies it to the real upload
route, which records it on each job outside the unchanged strict binding. Scheduler, projection and recovery owners
then stamp their parts at first handling, using their own role environment. Later
handling consumes the recorded part across revision or env changes. The gauntlet
checks actual job parts as well as the admission stamp. Excluded worker, provider,
process and authentication settings remain process inputs. No cloud
credentials or live endpoints participate in this replay.
