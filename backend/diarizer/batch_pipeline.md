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

Capture units are cut at upload boundaries, so a unit whose VAD speech starts at
sample 0 usually starts mid-utterance, and Parakeet TDT v3 then decodes nothing
(decoder start-state blank; KB `projects/parakeet-primary/evidence/2026-09-21-tdt-empty-output-root-cause.md`).
With `BATCH_PIPELINE_ASR_LEFT_CONTEXT_SECONDS` set (default 0, off until an L4
community-1 replay qualifies it; 8 is the evaluated value), such a unit's first
ASR window is prefixed with the contiguous predecessor of the same capture
stream (same owner and privacy generation, and the same source, client device
and lock read from the staged unit's authenticated intake context; record units
use their conversation. Intake's per-unit `conversation_id` is a chunk identity
that hashes each unit's own `capture_at`, so it never links two capture spans.
A unit with no readable intake context gets no context. Gap within 1s; an
overlap is trimmed so audio is never replayed), starting 0.5s before the onset
of the speech run that crosses the seam. Predecessors come from the same flight
or a bounded process-local tail cache (`BATCH_PIPELINE_ASR_LEFT_CONTEXT_UNITS`,
default 64, 10-minute TTL; other-generation tails of the owner are dropped on
sight). Window core ownership still starts at the unit's first sample, so
prefix words are never emitted, double-counted, or counted as the unit's ASR
output (an empty unit stays `empty_asr`); a seam-straddling word is clipped to
the capture. The padded empty-ASR retry keeps its synthetic silence. Ordering,
owner, merge and paid-recovery semantics are unchanged; only the ASR input of
the first window changes.

Flight packing (`BATCH_PIPELINE_FLIGHT_BATCHING_ENABLED`, **default off**; only
the exact value `true` enables it; `BATCH_PIPELINE_FLIGHT_BATCH_SECONDS`, default
1800) removes duplicated pyannote work inside one locked flight. Community-1
segmentation runs once per unit and feeds both VAD (CPU aggregation and
binarization) and diarization, and the WeSpeaker trunk runs once per 10s chunk
instead of once per (chunk, local speaker), pooled with the same masks. Forwards
pack chunks across the flight's units at the pinned model batch size, so a
forward is never larger than the serial one. Clustering, labels and turns stay
pyannote's own per-unit `apply`. With speech-only diarization
(`BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED`, #22358) the diarizer sees a
compacted waveform, so cross-unit packed embeddings and the cached full-unit
segmentation are not used for it; that call keeps its serial pyannote `apply`,
and only the per-file shared trunk applies inside it. Packed segmentation then
serves VAD alone. Units above the budget, unsupported model
layouts, non-fatal packed failures, cached-feature shape mismatches and CUDA
out-of-memory inside the packed path take the unchanged serial calls; other
fatal CUDA errors still quarantine the chain. `tests/unit/test_batch_pipeline_flight.py`
compares both paths on CPU with random weights (exact VAD spans and turns;
segmentation within 1e-5, embeddings within 1e-4) whenever torch and pyannote
are installed.

**Enablement gate.** CPU equality does not cover the L4: packing moves a unit's
last chunk out of its own batch-of-one forward into a shared batch, so cuDNN may
pick a different kernel, and a ~1e-5 embedding move or a powerset frame near 0.5
can change a VBx assignment. Before setting the flag on anywhere, run the paired
qualification on one isolated dev L4 with community-1 revision
`3533c8cf8e369892e6b79ff1bf80f7b0286a54ee` and batch pin 8, on public or consented
multi-speaker audio (for example AMI far-field meetings, or a pendant clip with two
voices):

```bash
PYTHONPATH=. BATCH_PIPELINE_MODEL_BATCH_SIZE=8 python diarizer/batch_pipeline_flight_qualify.py \
  --audio /public/ami/ES2004a.Array1-01.wav /public/ami/IS1009a.Array1-01.wav \
  --unit-seconds 23,41,67,95,128,30.5,212 --output /receipts/flight-qualify.json
```

It cuts the inputs into one flight of mixed-length units (ragged tails share
packed forwards) and scores two configurations, serial against flag-on, on the
same waveforms. Every serial reference is taken on the unpatched pipeline,
before `FlightPyannote` installs its hooks.

- `speech_only` (the Helm default, `diarizeSpeechOnlyEnabled=true`): packed
  segmentation feeds VAD, then the worker's own `_diarize_unit` diarizes the
  compacted waveform through the per-file shared-trunk hook. Evidence is
  VAD-only, since the harness runs no ASR.
- `full_unit` (speech-only off): full-unit `diarize_many`, plus raw
  segmentation and embeddings against the unpatched pipeline.

Exit status comes from the configuration the deployment runs (`--speech-only`,
default from the env, else on). A `full_unit` pass never authorizes the flag
while speech-only stays on. The gate fails closed. It passes (exit 0) only when:

- every unit was actually packed;
- VAD spans are equal;
- speaker counts are equal;
- units where serial finds two or more speakers agree on at least 99% of
  speech time after optimal label mapping;
- at least five such units exist;
- the packed CUDA working-set peak stays within 1.10x serial.

A non-positive serial CUDA baseline, or too few multi-speaker units, exits 2
(insufficient evidence). The packed flight must also stay inside the chart's
host envelope (9.795 GiB receipt, 12 GiB request, 14 GiB limit). Attach the receipt to the enabling change. #22324's `vad` and
`diarize` stage timers measure GPU time for this path only once they wrap
`_flight_segment`/`vad_spans` and `_flight_diarize`.

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
