# Bounded backfill memory rollout

Draft build, 2026-10-04. No production changes. Review and observability acceptance precede rollout through the existing backend deploy workflow. The worker limit changes in `.github/actions/sync-backfill-lifecycle/action.yml`: **8 → 4 GiB**. PR #20661 merged to main with concurrency 6 on 2026-10-04. This draft explicitly pins concurrency back to **3** for the qualified 4-GiB configuration; concurrency 6 remains separately qualified only at 8 GiB. Keep 2 vCPU, concurrency 3, revision min/max 3/18, service max 18 and request-based CPU. Queue settings stay 40 concurrent / 10 per second. The action also mounts a **1-GiB in-memory volume at `/app/syncing`**; the Docker working directory is `/app`.

The coordinator's aggregate `cost-opps/evidence/backend-sync-backfill-container-memory-utilizations.json` records daily merged memory-utilization histograms at an 8-GiB allocation. Highest nonempty linear bucket upper bound = bucket index × 0.01 × 8 GiB. The source distribution is sampled; this is neither exact peak RSS nor proof against transient OOM.

| UTC day | Mean GiB | p99 bucket upper GiB | Highest bucket upper GiB |
| --- | ---: | ---: | ---: |
| Sep 24 | 0.726 | 0.88 | 1.20 |
| Sep 25 | 0.706 | 0.88 | 1.12 |
| Sep 26 | 0.674 | 0.88 | 1.36 |
| Sep 27 | 0.722 | 0.88 | 0.96 |
| Sep 28 | 0.708 | 0.88 | 0.96 |
| Sep 29 | 0.682 | 0.88 | 1.20 |
| Sep 30 | 0.741 | 0.96 | 1.04 |
| Oct 1 | 0.719 | 0.96 | **1.76** |
| Oct 2 | 0.732 | 0.96 | 1.12 |
| Oct 3 | 0.748 | 0.96 | 1.12 |

The full-range headroom calculation was run against every nonempty bucket in the supplied JSON. With the 1.76-GiB upper bucket, a 2-GiB allocation has **0.24 GiB / 12%** remaining; reject it because decode/PCM copies, downloads and memory-backed temp files can briefly exceed samples. 4 GiB leaves **2.24 GiB / 56%**. This aggregate calculation alone did not qualify the tail. The synthetic qualification and new input bounds below are required for 4 GiB. No user content was read.

Gross active-memory saving: `4 GiB × $0.0000025/GiB-s × 3600 × (180.8–269.1 billed hours/day) × 30` = **$195–291/month**, plus possible idle saving. Credits/commitments reduce cash savings; concurrency/minimum changes overlap. [Cloud Run list rates](https://cloud.google.com/run/pricing).

After review, establish a day of phase/request/queue/memory baseline, deploy the memory-only setting through the normal path, and compare at least 24 hours. Reject any memory termination/restart or increased retries, and investigate persistent >10% p95 job-latency/queue-age regression. Aggregate metrics must cover the worker; absent metrics cannot count as a pass. Rollback to the previous serving revision through the normal deploy path if a newly bounded input or filesystem-pressure response blocks legacy work. Increasing to 8 GiB alone retains the input guard and 1-GiB volume; it only addresses RSS pressure.

A conservative concurrency-6 risk scenario doubles the complete 1.76-GiB footprint to **3.52 GiB**, leaving only 0.48 GiB under 4 GiB. That is not qualification: hold the concurrency draft until synthetic long-file/retry stress and a staged 8-GiB/concurrency-6 experiment establish adequate headroom. Merging both sizing drafts unconditionally produces 4 GiB/concurrency 6, which these samples do not justify. Fresh sync remains at 8 GiB because its sampled peaks reach 5.28 GiB.


## Input bounds and retry storage

Before this revision, `utils/multipart.py` capped each upload part at 200 MiB; Starlette's parser defaults to 1,000 files. The capture manifest's 20-file bound applies only to that optional manifest, not every upload. No whole-file duration, aggregate encoded/decoded byte, or frame-count bound protected the worker. `MAX_SYNC_FRAME_BYTES=65536` limits one frame, and `MAX_VAD_SEGMENT_SECONDS=300` limits a derivative segment only after the complete recording has been loaded. Filename `_fs` and PCM sample-rate fields were not bounded. Thus neither the four-speech-hour daily quota nor 300-second VAD segments bound decode/VAD allocations: both are downstream of loading the input.

`utils/sync/input_limits.py` now applies the same batch-wide bounds at historical admission (V1 and V2, before staging/claims/202) and on every Cloud Tasks download attempt:

| Bound | Limit |
| --- | ---: |
| Files | 20 |
| Encoded bytes, including framing | 64 MiB |
| Audio bytes: maximum of source WAV and 16-kHz/16-bit VAD representation | 64 MiB |
| Frames | 360,000 |
| Duration | 3,600 seconds, additionally constrained by the audio-byte bound |
| PCM sample rate | 8,000–48,000 Hz |
| Opus decoder frame samples | 40, 80, 160, 320, 640, 960, 1,280 or 1,920 at 16 kHz |

The effective longest file **and total batch audio** is `64 MiB / 32,000 bytes/s = 2,097.152 seconds` (34m 57.152s). PCM8 at 16 kHz reaches it with exactly 32 MiB of samples plus framing; high-rate PCM can reach its source-byte bound sooner. PCM normalization rounds up per frame. Opus expansion is conservatively charged at the maximum output accepted by `decoder.decode(..., frame_size=...)`, rather than compressed bytes. No input is truncated or prefix-acknowledged to satisfy a resource limit. Existing decoder handling of malformed suffixes remains unchanged.

Admission returns 413 for over-limit input before custody transfer. The Flutter upload API treats 413 as `SyncUploadHttpException`, without a job ID/202 acknowledgement. WAL sync marks 413 as a definitive upload refusal (`uploadRejected`), retains the local recording, and stops automatic retries; Transcribe Later retains its file and shows failure. This requires smaller batches or recordings; existing clients do not automatically split them. This contract requires explicit recovery for rejected long recordings; it is an intentional new admission policy, not transparent acceptance of every former upload.

Worker downloads check blob metadata and stream at most the remaining 64-MiB budget, even if a generation changes. Before allocating PCM, they validate the staged frames again. Legacy oversized work returns 503, with cloud audio and content claims preserved; it is not marked invalid or consumed by our handler, including on its final application retry. A saturated volume propagates as retryable storage pressure instead of a successful/invalid-audio result. Cloud Tasks still has its own maximum retry window, and staging retains its existing one-day lifecycle: resolve any legacy rejection promptly by restoring the previous serving revision. Do not claim indefinite durability from a 503.

`syncing/` may retain raw audio, full WAVs and derivative segments after cancellation, including executor leaves that outlive their coordinator. Immediate retries overwrite the same job filenames; abandoned job directories can accumulate. The in-memory volume bounds their **aggregate instance charge at 1 GiB**. Writes that reach that limit fail as capacity pressure rather than OOM; do not recursively clean active retry material. [Cloud Run in-memory volume contract](https://docs.cloud.google.com/run/docs/configuring/services/in-memory-volume-mounts).

## Local synthetic qualification (2026-10-04)

Executed with Python 3.11.15 on macOS arm64. `scripts/sync/qualify_memory.py` extracts and executes the unchanged production `decode_pcm_file_to_wav`, `pcm_to_wav`, `_run_file_vad`, and `retrieve_vad_segments` functions. It uses real pydub and NumPy conversions; synthetic VAD windows classify the complete file as speech to maximize segment storage. No provider requests, cloud clients, model inference or customer content. Every trial has three overlapping requests, one immediate same-job retry, and three other cancelled attempts retaining original WAVs plus all-speech segments. All synthetic paths are created under a fresh `.local/` directory and removed by that owned run.

RSS is `getrusage(RUSAGE_SELF).ru_maxrss`, converted to bytes for each OS; logical file bytes are sampled every 5 ms while writes occur. macOS files are disk-backed, so the sum is a **conservative high-water RSS plus tmpfs-equivalent envelope**, not an actual Cloud Run cgroup measurement. High-water RSS can persist beyond a phase; the sum intentionally does not undercount by reporting only post-run RSS. The 1-GiB filesystem mount itself was not created or tested locally.

| Trial (concurrency 3, retry, retained attempts) | Peak RSS GiB | Peak file bytes GiB | RSS + files envelope GiB | Result |
| --- | ---: | ---: | ---: | --- |
| Formerly accepted 200-MiB PCM16 file/request | 3.796 | 2.344 | **6.139** | 4 GiB fails, before app overhead |
| New maximum encoded-size PCM16 file: 64 MiB/request | 1.291 | 0.750 | **2.041** | Local bounded-file pass |
| Longest accepted PCM8 file: 2,097.152s/request | 0.638 | 0.594 | **1.232** | Local maximum-duration pass |
| Maximum 20-file batch: 64 MiB total/request | 0.189 | 0.753 | **0.941** | Local bounded-batch pass |
| Former 1,000-file batch at 200 MiB/file | — | Planned raw staging alone: 585.94 | — | Harness refused allocation; no runtime bound previously prevented it |

The old maximum-batch trial is explicitly **not completed**: downloading its raw files alone exceeds 4 GiB by two orders of magnitude, so the harness stopped before generating that data. That input is rejected before admission by the new contract. The largest bounded envelope leaves 1.959 GiB under 4 GiB before the shared app. Conservatively replacing measured file bytes with the full 1-GiB volume and reserving **1 GiB for additional runtime/provider overhead** gives `1.291 + 1 + 1 = 3.291 GiB`, or 0.709 GiB headroom. This is an engineering allowance, not a measured full-app idle footprint or proof against every allocator/provider behavior. Concurrency 6 is not qualified.

Reproduce from the repository root (the runner appends its PID to `.local/owned-pids.txt`):

```bash
backend/.venv/bin/python backend/scripts/sync/qualify_memory.py --root .local/qualify-file-syncing --output .local/qualify-file.json --bounded --file-mib 64
backend/.venv/bin/python backend/scripts/sync/qualify_memory.py --root .local/qualify-duration-syncing --output .local/qualify-duration.json --bounded --file-mib 64 --pcm8
backend/.venv/bin/python backend/scripts/sync/qualify_memory.py --root .local/qualify-batch-syncing --output .local/qualify-batch.json --bounded --file-mib 64 --batch-files 20
```

Before promotion, replay these bounded synthetic workloads in a **dev candidate of the exact image**, with the full app, 4 GiB/concurrency 3, actual volume and allocator, provider failure/retry/cancellation, and the normal deploy identity. Verify filesystem permissions for UID 10001, the volume's 1-GiB limit, preserved cloud audio on ENOSPC, peak container memory below 4 GiB with useful headroom, and no blocked legacy jobs. This local pass is the source-level qualification; dev container and live acceptance remain mandatory. No merge, deployment, cluster mutation or production-content read occurred during qualification.
