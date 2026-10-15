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
unbounded quadratic allocation. The [October 15 isolated dev L4 receipt](batch_pipeline_benchmark.md)
measures ASR batching and a length-dependent word-loss mitigation. The exact
reported 17% vendor-relative deficit was not reproduced. VAD compaction failed
its word-quality gate and remains off. Co-resident model memory, pyannote DER,
failure recovery and full-chain latency still require runtime qualification.

## Pool boundaries and stored-audio compaction

`BATCH_PIPELINE_POOL_KIND=dedicated_batch` is the default. Set
`BATCH_PIPELINE_UNIT_SECONDS` per pool (dedicated default/hard cap 7200 seconds).
Hour-sized conversation compute must never run on live Parakeet pods. A running
inference cannot be preempted: the October 15 dev requalification's 3600-second
backfill rejected every overlapping live upload and used 10.76 GiB.

`shared_live` requires units <=120 seconds, a total pull <=120 audio seconds,
a padded model batch <=120 seconds, and one in-flight batch per GPU. The local
multi-model factory refuses shared-live placement: future co-location must use
the existing live model's priority/admission arbiter, yield between bounded
pulls and pass joint latency/memory qualification. Merely choosing a pool config
must not launch a second chain on a live GPU. A's scheduler pool capacity gate
and these worker limits both apply; durable conversation identity need not
change when an integration layer introduces bounded compute pieces.

`TRANSCRIPTION_FINAL_PASS_VAD_COMPACTION_ENABLED=false` preserves the existing
stored-audio path. When explicitly enabled, local Silero speech regions retain
300 ms onset/500 ms tail margins, merge overlapping padded intervals and compact
PCM before shadow Parakeet. Word clocks map back by original sample offsets;
a word crossing a removed gap abstains to the original request. The shared
pyannote final-pass seam also compacts sync/shadow diarization input and splits
turns and overlaps back onto original intervals. Embeddings and source audio
remain on the original timeline. Empty VAD skips shadow ASR, but existing sync
words never lose all speaker evidence merely because VAD is empty. VAD failure
retains original behavior and records the shared fallback.

The sync adapter already receives words; it makes no additional Parakeet call.
Compacting its shared pyannote seam saves diarization work without retranscribing
those words. No Nemotron routing or cascade is introduced. The selector remains
available; pyannote stays the default.

Pre-STT WAL coverage now emits `reason` in its existing aggregate log and
`omi_sync_wal_audio_coverage_total{outcome,reason}`. Reason values are bounded to
none/unparseable/degraded/truncated/overflow/evidence/geometry/error/other.
Matcher/proof eligibility is unchanged. This distinguishes missing evidence,
geometry failures and degraded/truncated lookups without exposing user data.
