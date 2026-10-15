# GPU chain integration and qualification

This is an unconnected worker implementation for PR #21674. Existing sync and
batch HTTP services do not import it, so default-off routing remains unchanged.
The [scheduler contract](../docs/batch-pipeline-worker.md) owns admission, leases,
heartbeats, retries and ordered merge. Each input is a conversation/capture span,
target at most one hour, hard ceiling 7200 seconds. Internal ASR windows are not
queue units and do not change the durable merge key.

Run one process and construct models once per GPU. Compose `create_local_worker`
with explicit VAD, Parakeet and community-1 models plus fetch/decrypt and durable
persist/encrypt callbacks. Invoke `process_batch` from a blocking GPU worker lane;
never the async API event loop. Its process-wide lock serializes the entire
chain. No extra model thread, HTTP service or vendor call is created. Runtime
image/dependency co-residency, memory budget and model startup remain unqualified;
neither existing diarizer nor Parakeet image is changed by this implementation.

Canonical staged input is mono PCM16 WAV at 16kHz. Decode once into float32 and
run VAD on that waveform. VAD silence persists a silence result without either
ASR or diarization. The host decoded working set is bounded to two audio-hours;
GPU ASR windows sort across owners by duration and pack against padded seconds
and model batch size. Windows pad VAD edges and retain context across forced
cuts. Midpoint ownership restores conversation clocks and discards duplicate
context words. Overlapping voices and model substitutions still require public
reference scoring; token counts alone cannot establish word quality.

The words provider defaults to Parakeet and diarizer to pyannote. Registries admit
future alternatives only when explicitly supplied; unknown selections fail
closed. Single-speaker skipping requires the existing calibrated resolution's
>=90% coverage and exactly one identity. No heuristic based on words or VAD
segment count may claim a single speaker. Diarization is per conversation;
speaker labels never pool across owners. Payloads retain words and turns as
separate evidence for the downstream projection/assignment layer; this worker
does not name speakers or write user conversation records.

Pre-STT live reuse additionally defaults off. It requires existing lineage gates
plus an injected resolver's immutable-audio-bound full-source-coverage and
words-of-record-quality receipt. Current lexical dedupe runs after STT and cannot
issue that receipt. With no eligible receipt ASR runs normally. Missing or
ambiguous proof never causes audio loss. Aggregate worker counters have no owner
labels and are cumulative per instance.

Per-item decode/VAD/diarization/persistence failures return no result for that
item; scheduler retries those leases. A model-call failure invalidates that
microbatch's participating items. A durable result URI is returned only after
persistence succeeds. Heartbeat must run independently while this synchronous
chain holds a GPU; request completion is not a durability boundary.

Qualification command, from `backend/` on an isolated dev GPU, using public AMI
PCM and its aligned public transcript:

```bash
PYTHONPATH=. python diarizer/batch_pipeline_benchmark.py \
  --audio /public/ami.wav --reference /public/ami-reference.txt \
  --output /receipts/ami-asr-ablation.json
```

Optional `--vad-json /public/vad-spans.json` selects the same VAD spans in all
window cells; the whole baseline retains full audio. Compare that run to a run
without VAD to isolate VAD boundary effects. This measures ASR only, not full-chain
throughput. Batch size is the maximum window count, and effective sizes are
reported. Whole-input full attention is excluded above 300 seconds to avoid an
unbounded quadratic allocation. No benchmark has run for this implementation:
both dev L4s were occupied and isolated pool creation was denied by dev IAM.
There is no reproduced 17% deficit or validated chunking fix yet. Hold runtime
qualification and rollout until measured AMI WER, token recall, GPU throughput,
co-resident model memory, failure recovery and full-chain latency pass review.
