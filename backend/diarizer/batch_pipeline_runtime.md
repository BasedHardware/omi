# Dedicated batch worker process

`python -m diarizer.batch_pipeline_runtime` is the sole GPU chain owner. It
constructs A's `Pump` with `Scheduler(pool='batch')`, one `PipelineWorker`, a
fresh per-pull `PoolCapacity`, and the configured conversation-unit ceiling.
The model microbatch size is distinct from the admitted conversation duration.
No live Parakeet endpoint or shared-live arbiter is used.

The default `BATCH_PIPELINE_WORKER_ENABLED=false` exits before clients or models
are constructed. Enabling the process drains accepted work, including after
admission rollback. It does not enable admission: the lead separately controls
`BATCH_PIPELINE_ENABLED`, its owner cohort, and the rollout gates in the design.
The Helm chart also defaults `enabled:false` and renders no resources.

Startup requires exactly one visible CUDA GPU with BF16 support. ASR uses
Parakeet v3 revision `541d1f99c6b0c3cd0b11a95167540bb8edefd82b` in BF16;
community-1 revision `3533c8cf8e369892e6b79ff1bf80f7b0286a54ee` stays FP32.
VAD reuses that pipeline's FP32 segmentation model. There is no FP8 or Nemotron
routing. The model factory sets `compute_timestamps=true` and
`greedy.use_cuda_graph_decoder=false` **before** constructing decoding; it also
disables the runtime graph and asserts actual eager state before and after
transcription. This closes the timestamp-initialization graph reset found by
the GPU quality lane. A graph-policy violation quarantines and restarts the
process. The prior ASR-only benchmark is not joint-image qualification.

SIGTERM stops new pulls; the bounded current chain drains with A's 20-second
lease renewals. Lost leases cannot complete. CUDA synchronizes before any result
returns to the pump. Fatal CUDA state exits for Kubernetes replacement. The
chart grants 1500 seconds for shutdown; lease expiry remains the recovery path
if a process is forcibly lost. `/ready` opens only after model startup and
closes on stop. `/health` requires the event loop to keep ticking. Queue metrics
are served at `/metrics`. C's legacy result projection and D's deletion outbox
maintenance run separately on the backend, with durable restart sweeps; importing
legacy provider clients into the GPU image is unnecessary.

## Encrypted staging and results

`utils.batch_pipeline.artifact_policy.create_artifact_store(store, storage_client,
bucket, master_secret)` composes B's object adapter with D's transactional privacy
callbacks. A decodes the original bundle to canonical 16kHz mono PCM16 WAV,
sets its actual capture/duration/source conversation and privacy generation,
then calls `stage_audio(item, wav)` before atomic enqueue. Replace the seed
`audio_uri` with the returned URI. Audio AAD excludes that self-reference.
`fetch_audio(item)` authenticates/decrypts in memory; the worker decodes once.
`persist_result(item, payload)` encrypts words, turns and provenance, then returns
an immutable generation-pinned URI. C calls `load_result(original_item, uri)`.
The original admitted WorkItem is required; payload identity is never trusted.

Both standard and enhanced accounts receive per-owner AES-256-GCM encryption
for temporary artifacts. E2EE, unknown protection, missing pinned generation,
account deletion, source tombstones, migration and generation changes refuse
processing. The envelope authenticates namespace, owner, segment, capture time,
duration, source conversation, kind, protection and privacy generation; results
also bind the exact staged audio URI. No plaintext temporary files are used.

Only the configured `BUCKET_BATCH_PIPELINE` and hashed-owner/segment object path
are accepted; arbitrary HTTPS URLs and unversioned reads are rejected. WAV and
result payloads have size ceilings; GCS metadata is checked before download.
Writes reserve a random create-only object name in D's durable deletion outbox
**before** uploading. The adapter reauthorizes immediately before and after IO,
disables hidden SDK retries, and refuses starting uploads if registration took
more than 30 seconds. Post-upload revocation deletes the exact generation and
returns no URI. An ambiguous upload retains its reserved deletion reference.
D's delayed erasure sweep covers deletion while an upload is still in flight;
completion-only retention must never remove the last reference first.

## Packaging and scaling

Build from repository root:

```sh
docker build -f backend/diarizer/Dockerfile.batch-pipeline -t batch-pipeline-worker:qualification .
```

The separate Python 3.11 image consumes `diarizer/pylock.batch-pipeline.toml`;
it does not alter the backend service or live Parakeet image. Recreate the lock
with its header command when changing `requirements-batch-pipeline.txt`.
A build is not a GPU qualification: before any cohort, verify joint startup,
actual graph/precision state, full-chain peak memory, lease loss, synthetic
end-to-end projection/deletion, and AMI quality in the built digest.

The chart `charts/batch-pipeline-worker` pins a qualified image digest, existing
Workload Identity service account, explicit data-plane project, secrets and
staging bucket. It fixes the `diarizer-batch-pool` node selector and taints,
requests one GPU, and prevents surge GPUs. It cannot be installed over the live
embedding or Parakeet release. Dedicated bucket lifecycle must preserve pending
accepted work; D arms cleanup only after successful projection.

HPA uses A's **ready** age, separately targeting fresh 30s, recent 300s and deep
3600s, with 300s downscale stabilization. Minimum one worker keeps the queue
sampler alive; zero is rejected until an independent sampler exists. Enable
PodMonitoring only where its CRD is installed. Its target-label mapping exports
`worker_release`; a different collector must preserve the same label plus
namespace and pod. Merge `prometheus-adapter-rules.yaml` into the existing
adapter's external rules. That query excludes samples older than 60s without
coercing unavailable data to zero. Missing/stale external metrics retain HPA
capacity; alert on adapter errors and missing sampler freshness. No chart or
adapter change has been deployed by this PR's implementation lane.

For local synthetic end-to-end work, use loopback Firestore and a version-aware
GCS emulator (or an injected fake object client). The older filesystem
`local_storage` harness has no generation preconditions and cannot substitute
for the versioned artifact adapter. Never remove generation checks to make a
local run pass, and never fall back from an emulator namespace to cloud data.
