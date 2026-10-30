# Bounded backfill input limits

Input-side guards only. This change does not alter Cloud Run sizing: the worker keeps the lifecycle action's current memory, concurrency and max-scale settings (`.github/actions/sync-backfill-lifecycle/action.yml`). It supersedes the input-guard portion of #20662; the 4 GiB / concurrency 3 sizing from that draft was dropped and would need its own qualification against the current 8 GiB / concurrency 6 design.

Rollback: restore the previous serving revision through the normal deploy path if a newly bounded input or filesystem-pressure response blocks legacy work.

Before this revision, `utils/multipart.py` capped each upload part at 200 MiB; Starlette's parser defaults to 1,000 files. The capture manifest's 20-file bound applies only to that optional manifest, not every upload. No whole-file duration, aggregate encoded/decoded byte, or frame-count bound protected the worker. `MAX_SYNC_FRAME_BYTES=65536` limits one frame, and `MAX_VAD_SEGMENT_SECONDS=300` limits a derivative segment only after the complete recording has been loaded. Filename `_fs` and PCM sample-rate fields were not bounded. Thus neither the four-speech-hour daily quota nor 300-second VAD segments bound decode/VAD allocations: both are downstream of loading the input.

`utils/sync/input_limits.py` now applies the same batch-wide bounds at historical admission (V2 only, after the final lane is resolved, before staging/claims/202; V1 never processes backfill and keeps its retryable 503) and on every Cloud Tasks download attempt:

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

Worker downloads check blob metadata and stream at most the remaining 64-MiB budget, even if a generation changes. Before allocating PCM, they validate the staged frames again. Legacy oversized work returns a 409 `locked` defer, with cloud audio and content claims preserved; it is not marked invalid or consumed by our handler, including on its final application retry. A saturated volume propagates as retryable storage pressure instead of a successful/invalid-audio result. Capacity deferral resets the job to queued under its existing run fence, so the processing-stale detector cannot fail it during retry backoff. Cloud Tasks still has its own maximum retry window, and staging retains its existing one-day lifecycle: resolve any legacy rejection promptly by restoring the previous serving revision. Do not claim indefinite durability from a 503.

`syncing/` may retain raw audio, full WAVs and derivative segments after cancellation, including executor leaves that outlive their coordinator. Immediate retries overwrite the same job filenames; abandoned job directories can accumulate. Writes that hit a full filesystem (ENOSPC/EDQUOT) fail as retryable capacity pressure rather than a successful or invalid-audio result; do not recursively clean active retry material.
