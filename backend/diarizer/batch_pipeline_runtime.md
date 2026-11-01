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

### Pump pipelining

`BATCH_PIPELINE_WORKER_PIPELINE_DEPTH` (Helm `worker.pipelineDepth`, default
`2`, range 1-4) runs that many pump lanes in one process. Lease claim, compute
admission, completion and ordered merge of one lane overlap another lane's GPU
chain; the chain itself (fetch/decode, VAD, ASR, diarization, persist and CUDA
quiescence) stays exclusive behind one asyncio lock, so device and host memory
remain one flight. Each lane renews its own leases while it waits for the GPU.
On SIGTERM or a fatal GPU error a lane still waiting refunds its leases without
an attempt charge instead of starting another chain. Periodic recovery,
result-ready drains and queue metrics run in their own task on the same 5s/15s
cadence instead of inside a lane between flights. Publication is unchanged: the transactional
ordered merge remains the per-owner ordering authority across lanes, exactly as
it already is across replicas and the serving reconciler. `1` restores the serial
pump. A waiting lane may hold one already-claimed flight ahead of later fresh
arrivals, so fresh work can wait up to one extra chain.

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
The encrypted payload includes `speech_spans`, an ordered nonoverlapping list of
`{start, end}` seconds on the original capture-relative timeline, sample-rounded
from the unpadded VAD union (silence `[]`). `speech_seconds` is the duration of that
same union (silence zero). C validates both against `audio_seconds`, then applies
the legacy VAD grouping policy for multipart projection and content-idempotent
accounting. ASR padding, window-local clocks and transcript gaps never define
these boundaries. The chain reuses its single VAD invocation for both fields.

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
uses bounded SDK retries under the same registered object name, and refuses
starting uploads if registration took
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
staging bucket. It selects the dedicated `batch-pipeline-pool` with
`service=batch-pipeline` and `env=<env>` labels, requests one GPU, and prevents
surge GPUs. **An NVIDIA L4 on `g2-standard-8` is required**: the joint chain was
qualified on L4 and ASR requires native BF16; T4 (`sm75`) is unsupported. The
live `diarizer-batch-pool` is separate and must not host this worker.

An operator creates the pool out-of-band, not through IaC or this chart, with
labels `env=<env>,service=batch-pipeline` (`env=dev` or `env=prod`), taints
`nvidia.com/gpu=present:NoSchedule` and `omi.ai/batch-pipeline=true:NoSchedule`,
node autoscaling `0..N`, and location policy `ANY`. The chart tolerates exactly
those two taints. Node autoscaling to zero is separate from the minimum-one
worker requirement below. The image puts GKE's `/usr/local/nvidia/bin` on
`PATH` and `/usr/local/nvidia/lib:/usr/local/nvidia/lib64` on `LD_LIBRARY_PATH`,
retaining `/usr/lib/x86_64-linux-gnu` for system libraries. The pinned torch
wheels supply CUDA userspace; the host mount supplies `libcuda.so.1`.

The worker cannot be installed over the live
embedding or Parakeet release. Dedicated bucket lifecycle must preserve pending
accepted work; D arms cleanup only after successful projection.

HPA uses A's **ready** age, separately targeting fresh 30s, recent 300s and deep
3600s, with 300s downscale stabilization. Each worker samples queue age every
15s on its own supervised task, independent of the GPU batch, so series stay
fresh while every replica is busy. Minimum one worker keeps the queue
sampler alive; zero is rejected until an independent sampler exists. With
several replicas, lease recovery and the result-ready drain run on one replica
per 30-second lease (`pump_recovery` in `{namespace}_leases`); each pump still
drains the owners of its own completions, and a lease-store error fails open. Enable
PodMonitoring only where its CRD is installed (it defaults on). The worker exports
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

### Fatal GPU recovery and memory qualification

CUDA OOM (including torch `OutOfMemoryError` and cuBLAS allocation failure) fences
the process just like illegal access. `FatalGpuError` must reach the pump's
no-failure lease recovery path; never publish partial results from that flight.
Restart under a retry lease without charging an attempt.

Each synchronized full-chain flight logs `event=batch_chain_memory`: admitted
audio seconds, CUDA allocated/reserved baselines and peaks in bytes, process
lifetime host peak, and cgroup lifetime peak when the kernel exports it. CUDA
peaks reset after models load and before decode/VAD/ASR/diarization/persistence;
the receipt is emitted after CUDA synchronization. Host peaks include startup.
This receipt also runs when individual items fail; it is not an item-success
receipt. Nonfatal item failures log `event=batch_worker_failed` with only
`error_class`, a bounded `stage` and `segment_id`, once per item per flight,
even without an `on_failure` callback. Repository validation raises
`BatchValidationError` (a `ValueError`) with a closed `reason`: `word_shape`,
`word_clock`, `word_sequence`, `vad_nonfinite`, `vad_order`, `vad_bounds`,
`empty_asr`, or `no_owned_words`. Other exceptions use `unclassified`; never
classify provider messages by printing them. Numeric `samples`, `vad_spans`,
`windows`, `asr_words` and `owned_words` describe the failed shape; -1 means
the operation did not return that count. ASR counts include validated records
and context repeats; an invalid hypothesis fails before contributing its count.
Buffer only those strings/integers and emit after
the item exception handlers exit, so handler diagnostics cannot chain the worker
exception. Logging failures are swallowed without another log attempt; healthy
sibling results still return. Never add exception messages, traceback
locals, transcript/audio, object URIs or lease/admission tokens to this event.
Pyannote uses frame-centered VAD intervals: crop their end to the actual input
duration, reject malformed or wholly outside intervals, and keep every in-buffer
speech interval. Rebase ASR windows from the integer sample index used to slice
them. Before failing empty ASR on VAD speech or an ownership-empty hypothesis,
the Parakeet adapter makes one single-item ASR call over the full captured unit,
with 2s synthetic silence on each edge and an 8s minimum padded length. The
padded input must fit both 120s and the configured padded budget; otherwise it
remains held whole for fenced legacy recovery. No real samples are discarded.
Validated retry clocks are rebased by 2s and intersected with the real capture;
words whose midpoint is in synthetic padding are excluded. Original VAD speech
accounting, diarization input, privacy checks and persistence are unchanged.
`event=batch_asr_recovery` contains only segment ID, original closed empty reason,
sample count, original ASR count, recovered word count, original window count,
minimum/maximum window sample lengths, speech sample count and
`recovered|empty|skipped_oversize` outcome. It and the shared
fallback metric emit outside exception handlers; observability failure never
discards healthy results. A retry exception is labeled `stage=asr_recovery` and
fatal CUDA still fences the entire chain. Remaining empties never become silence
or bypass accepted content claims. The scheduler's attempt ceiling and the
separate default-off, owner-allowlisted legacy path are documented in
[serving settings](../docs/batch-pipeline-serving.md).

`BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED` ships **true** (Helm
`worker.workerValidationDispositionEnabled`). A closed `BatchValidationError`
ends this GPU chain on the first attempt. `ValidationFailureWork` carries only
its stage and reason; the scheduler retains them in `worker_failure`, removes
the ordered pending span and creates the existing held recovery obligation.
This is terminal for GPU retries, not a success or permission to delete audio.
The old lease cannot publish a late result. Empty-ASR handoffs also preserve
`empty_asr` versus `no_owned_words` along with their padded-retry evidence.
Unclassified provider/transport faults retain exponential backoff and the
existing bounded attempt policy; fatal CUDA retains the restart protocol.

If Pyannote rejects a frame wholly beyond EOF, the worker first checks the
canonical real buffer with independent strict local VAD, including its partial
final window. A valid empty strict-VAD result commits a truthful `silence`
payload through ordinary persistence and projection. This fixes tiny captures
(observed: 320 samples / 20ms) without treating invalid VAD as silence. Positive,
malformed, unavailable or noncanonical evidence takes the held recovery route.
The worker never calls an external provider for this silence check. Rollback:
set the worker validation disposition flag to `false`, restoring bounded GPU
retries; existing held intents and receipts remain authoritative.

## GPU skips that cannot change the transcript

Diarization was the dominant per-unit GPU cost (pyannote RTF ~0.04 versus
Parakeet ~0.0025) and ran over the whole unit, silence included, while ASR
already saw only padded VAD windows. Two Helm switches decide whether and on
what audio diarization runs; batching is unchanged.

- `worker.diarizeSpeechOnlyEnabled` (`BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED`,
  **on**; unset is on, only `false` disables): evidence is unpadded VAD speech
  plus every emitted word clock (so a word in ASR context outside VAD is never
  withheld). Each region is padded 1 s, regions under 4 s apart keep their
  in-between audio, and pieces are joined with 0.5 s of zeros. Turns and
  overlaps map back to capture clocks; seam audio maps to nothing. The full
  unit is diarized when:
  - over 80% of samples would be kept: `omi_fallback_total{component="vad",
    from="batch_speech_only_diarization",reason="kept_over_80pct",outcome="recovered"}`;
  - compaction or mapping raises, or compacted output has no turns while words
    exist: same series with `reason="other",outcome="degraded"`.
  Every decision increments `omi_batch_pipeline_diarization_decisions_total{decision}`
  (`compacted`, `full_flag_off`, `full_no_evidence`, `full_kept_over_80pct`,
  `full_compaction_error`, `full_compacted_empty`, `skipped_short`), and
  `omi_batch_pipeline_diarization_audio_seconds_total{kind="unit"|"diarized"}`
  gives the measured retained fraction. A persisted compacted result with any
  word outside every turn (a diarizer gap inside a retained piece) increments
  `omi_batch_pipeline_compacted_unassigned_units_total` and `..._words_total`;
  such words abstain exactly as they do in full-unit gaps. The persisted
  diarization adds `speech_compaction.diarized_seconds`.
- `worker.shortSpeechSingleEnabled` (`BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED`,
  **off**; only `true` enables): one evidence region of at most 2 s, where
  pauses of at most 0.5 s (inclusive) join and a longer pause splits, takes the
  existing `skipped_single` `SPEAKER_00` result with `single_evidence:
  short_speech` and no model check. **Enablement precondition:** a paired run on
  the prod pyannote revision `3533c8cf8e369892e6b79ff1bf80f7b0286a54ee`
  showing the full diarizer returns a single speaker on the gate's own evidence
  (VAD plus words), including two bursts separated by at most 0.5 s. The AMI
  bench used other weights and only single continuous slices.

ASR inputs and words are identical with either switch on or off. Rollback:
set `worker.diarizeSpeechOnlyEnabled=false`.

Quarantine events are cumulative transitions, not current debt. For read-only
Firestore aggregation, count `batch_pipeline_prod_jobs` with `state ==
quarantined` AND `quarantine_reason == worker_failed`, then partition by
`recovery_state`, `worker_failure.stage/reason` and `recovery.failure.stage/reason`.
Use `count()` only. A `quarantined_at >= cutoff` count includes jobs subsequently
recovered, committed or terminally disposed; never label it "held". Legacy jobs
without `worker_failure` need an aggregate join to content-free worker logs;
absence of a code is not evidence of corrupt audio. An `abandoned_running`
recovery is an uncertain paid intent: do not automatically reset it or classify
it as silence. Reconcile its durable result or obtain a separately authorized,
idempotent recovery decision.

For qualification run a synthetic one-hour unit with the intended model batch
size and retain the GPU model/VRAM, exact image digest/config and receipt.
Set the chart **host RAM** limit from the larger measured process/container peak
with explicit headroom; CUDA peaks qualify device capacity separately.

The October 16 dev L4 compute qualification used the deployed image
`sha256:e2ae6e672c07d6532e58ad0f7aa55eda52d1959bad3d65f4c88dc714adc5b619`,
BF16 ASR, FP32 segmentation/VAD, eager decoding and effective batch 8 for ASR,
segmentation, embedding and VAD. A 20-minute public AMI montage followed by its
threefold 3600-second repetition ran in one model process with in-memory audio
and result adapters. The synchronized one-hour receipt recorded CUDA allocated /
reserved peaks of 2,238,839,808 / 7,184,842,752 bytes, process peak 5,910,188,032
bytes and cgroup lifetime peak **10,517,725,184 bytes (9.795GiB)**, including
startup. The chart requests **12Gi** and limits **14Gi**: round the host peak plus
`max(1GiB, 20%)` / `max(2GiB, 40%)` up to whole GiB, respectively. This provides
2.205GiB / 4.205GiB headroom. The qualification Job had a 24Gi cap; the proposed
14Gi cap and multi-unit decoded-group envelope were not separately exercised.
These are compute-chain measurements; deployed intake, lease-loss recovery,
projection, encrypted artifact IO and deletion remain separate qualification
gates. Admission stays off.

The worker Deployment and its workflow rollout wait both allow **1800 seconds**.
The first dev cold rollout took at least 718.6 seconds from pod creation to ASR
restore, exceeding the old 600-second deadline before joint readiness. The new
budget adds about 1081 seconds beyond that observed lower bound for node/image
startup and model loading. The existing diarizer workflow wait remains 600s.

PodMonitoring defaults on when the release is enabled. Queue age and freshness
export the Kubernetes namespace and `worker_release` from the deployment.
Autoscaling defaults off; verify fresh series and the external adapter before
turning it on. Both fixed replicas and the HPA minimum must remain at least one.

Staging uses resumable GCS uploads (including short captures), 8MiB chunks,
10s connect/120s read timeout per request and a 120s retry budget per request.
The stream refuses new chunks after 15 minutes. The deletion outbox keeps the
unique object name for 30 minutes, covering the last request/retry plus margin.
Retries retain the registered create-only object name and encrypted stream.


## Per-item quarantine

Explicit failed items stop retrying at `BATCH_PIPELINE_MAX_ATTEMPTS` (default 5).
The scheduler records a terminal failure and removes it from ordered pending
work; it never reports successful silence. Successful siblings retain their
assignment receipts, while later uploads may advance. Legacy recovery is held,
not dispatched: see [terminal quarantine and the visible gap](../docs/batch-pipeline-worker.md#terminal-quarantine-and-the-visible-gap)
for client status, retained audio/usage obligations and the fenced recovery design.

Worker strict-silence disposition is separately dark behind
`BATCH_PIPELINE_WORKER_SILENCE_DISPOSITION_ENABLED=false`, rendered from Helm
`worker.workerSilenceDispositionEnabled: false`. It reuses integration's local
Silero inspection after empty ASR, before quarantine; ONNX and the VAD asset
are packaged in this image. Enable only with an approved worker image rollout
and worker flag change; setting it back to false restores empty-ASR quarantine.
See `docs/listen_pusher_pipeline.mdx` for payload and recovery semantics.


### Paid quarantine recovery request lifetime

`BATCH_PIPELINE_RECOVERY_TASKS_ENABLED` defaults to `true`. The 20-second
serving reconciliation loop prepares the existing fenced recovery intent and
queues a named HTTP task on `BATCH_PIPELINE_RECOVERY_TASKS_QUEUE`, falling back
to `SYNC_TASKS_QUEUE` when unset, using `SYNC_TASKS_INVOKER_SA`. Production
integration uses the isolated `batch-quarantine-recovery` queue (16 concurrent
dispatches, eight/second, five attempts), provisioned by the existing deploy
action before the integration revision. Four slots left recovery p95 above five
minutes at the 5% ramp (10-19), so production runs 16/8. This prevents shared legacy sync
retries from consuming recovery dispatch slots; it does not grant another paid
intent. Clear the queue override to roll back isolation.
The target is `BATCH_PIPELINE_RECOVERY_TASK_AUDIENCE` (integration's own HTTPS
origin, declared separately from the worker audience in dev and prod) plus
`/v2/batch-pipeline/recover-quarantine`; the audience must be an HTTPS origin.
The handler awaits the sole provider call and result persistence before replying,
so ordinary Cloud Run revision draining sees an active request. Background sweeps
enqueue prepared work or reconcile running artifacts. Any dispatch failure
(including missing configuration or a lost enqueue acknowledgement) falls back
to inline recovery with the same token. The task and inline path race through
the same transactional start fence, so at most one can invoke paid STT. The
shared fallback metric records this degraded inline execution. A disabled
handler host or owner cohort returns retryable HTTP 503, never a successful ack.
Each prepared intent has at most one outstanding wake task: the sweep leases a
wake (`recovery_wake`, default 600s, `BATCH_PIPELINE_RECOVERY_WAKE_LEASE_SECONDS`)
and names the task by intent token and wake sequence, so a backlog no longer
adds a new task per unit on every sweep. At lease expiry the previous task is
probed; it keeps its lease while it exists, and only NotFound (or three failed
probes) mints the next sequence; a delivery of that same wake that leaves the
intent prepared, or a failed enqueue, re-arms a 120-second wake, and a stale
delivery never shortens a newer wake. `0` restores the legacy two-minute wake-name
generation on every sweep. Neither path authorizes a second provider call. Existing privacy, lease, content ownership and intent-token
fences apply to every delivery, including duplicates and admission rollback.

Integration declares a 3,600-second Cloud Run request timeout in both manifests,
above the 1,500-second task dispatch deadline and application path timeout.
Modulate has a 300-second client budget. If the application returns 504,
cancelling the ASGI await does not stop its executor thread: that thread may
still persist the result while its instance survives. A retry adopts the same
`running` token and only reconciles artifacts; it never starts a second paid
call. Ordinary drain protection ends with the request; a timeout followed by
instance death can still leave uncertain work held (including the existing
900-second abandonment fence). This is not permission to reset the token.

Kill switch: set `BATCH_PIPELINE_RECOVERY_TASKS_ENABLED=false` to restore inline
sweeping. Already enqueued tasks still use the same intent fence. No historical
`failed_held` intent is reset. An exceptional instance kill can still leave an
uncertain paid call held; this requires provider result reconciliation or an
explicit new epoch, never blind retry. Do not weaken the quarantine-to-completion
gate or exclude censored held work to hide this residual obligation.
