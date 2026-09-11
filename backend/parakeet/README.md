# Parakeet ASR GPU Service

Self-hosted speech-to-text using **NVIDIA Parakeet** — separate TDT v3 serving instances for batch and buffered streaming. Runs on GKE GPU node pool behind internal load balancer.

## API

### `POST /v1/transcribe` — Batch ASR
Multipart audio file (16 kHz mono) → `{"text", "segments": [{text, start, end}]}`
- Model: TDT 0.6b v3; accuracy depends on the measured corpus
- Full punctuation, capitalization, accurate timestamps

### `POST /v2/transcribe` — Batch + Diarization
Same as v1 plus server-side speaker diarization and language detection.
- Form param: `diarize=true` (default)
- Segments include `speaker` label
- Built-in pyannote/wespeaker embedding on GPU

### `WS /v3/stream` — Streaming ASR
WebSocket: send raw PCM16 chunks, receive JSON segments in real-time.
- Model: TDT 0.6b v3 with buffered decoder (2s chunks, 2s right context, 10s left context)
- VAD endpointing (Silero), independent recurrent state for each session
- AGC normalization for quiet BLE microphone audio
- Built-in speaker diarization
- Query params: `sample_rate` (default 16000), `vad_threshold`, `hangover_s`
- Send text `"finalize"` to end session
- Automatic language detection across the 25 TDT v3 languages; qualify formatting and accuracy on the streaming output

### `GET /health` — Health check
Returns `{"status": "healthy", "ready": true}` (200) when the model is ready,
`{"status": "loading", "ready": false}` (503) during initialization, or
`{"status": "unhealthy", "ready": false, "reason": "..."}` (503) after a fatal
CUDA error. Kubernetes readiness, liveness, and startup probes use this endpoint.

### `GET /batch/metrics` — Batch engine stats
Returns `{"total_requests", "total_batches", "total_files", "rejected_requests", "pending_requests"}`.

## Environment Variables

### Batch Model & GPU Worker

| Var | Default | Effect |
|-----|---------|--------|
| `PARAKEET_MODEL` | `nvidia/parakeet-tdt-0.6b-v3` | Batch model |
| `PARAKEET_DEVICE` | `cuda:0` | GPU device for batch inference |
| `PARAKEET_TORCH_COMPILE` | `true` | Enable torch.compile; measure throughput for the deployed image |
| `PARAKEET_CUDA_GRAPHS` | `false` | Enable CUDA graph decoding. Must stay disabled when `PARAKEET_STREAM_MODEL` is configured because batch and streaming inference share one CUDA context. |
| `PARAKEET_GC_INTERVAL` | `50` | Full gc.collect() every N batches (gc.collect(0) per batch) |
| `PARAKEET_GPU_POLL_TIMEOUT` | `0.05` | GPU worker queue poll interval in seconds |
| `PARAKEET_BF16` | `1` | BF16 model loading (halves GPU memory) |

### Dynamic Batching

| Var | Default | Effect |
|-----|---------|--------|
| `PARAKEET_MAX_BATCH_SIZE` | `32` | Max files per GPU batch |
| `PARAKEET_BATCH_WAIT_SECONDS` | `0.002` | Timer flush interval for partial batches |
| `PARAKEET_MAX_QUEUE_DEPTH` | `4096` | Backpressure limit (503 when exceeded) |

### Streaming

| Var | Default | Effect |
|-----|---------|--------|
| `PARAKEET_STREAM_MODEL` | `nvidia/parakeet-tdt-0.6b-v3` | Streaming model (TDT v3 in the primary deployment) |
| `PARAKEET_MAX_SPEECH_S` | `30` | Max segment duration before forced emission |
| `PARAKEET_AGC_TARGET` | `0.8` | AGC normalization target peak |
| `PARAKEET_VAD_THRESHOLD` | `0.5` | Silero VAD speech probability threshold |
| `PARAKEET_CHUNK_S` | `2.0` | Buffered decoder chunk size in seconds |
| `PARAKEET_LEFT_CONTEXT_S` | `10.0` | Buffered decoder left context in seconds |

### Other

| Var | Default | Effect |
|-----|---------|--------|
| `PARAKEET_INFERENCE_MODE` | `nemo` | Inference backend (`nemo` or `nim`) |
| `HOSTED_SPEAKER_EMBEDDING_API_URL` | | External diarizer fallback (optional — built-in preferred) |
| `HUGGINGFACE_TOKEN` | | For downloading pyannote speaker embedding model |

## Deploy

Use the existing backend release workflows. They require an exact-image GPU
qualification artifact, verify or promote the image into the target registry,
and establish warm stream capacity before publishing primary routing. The
[release helper](../scripts/deploy_parakeet_stream.py) prints its source-only
plan unless `--apply` is passed.

Backend streaming connects via `HOSTED_PARAKEET_STREAM_API_URL`, with the historical `HOSTED_PARAKEET_API_URL` as a compatibility fallback. No auth required — service runs behind internal LB only.

## Dedicated realtime service

Set `PARAKEET_SERVICE_MODE` to `stream` for one streaming TDT/VAD/speaker embedding instance only,
`batch` for TDT/batch diarization, or `mixed` for the historical combined service
(default). Wrong-mode endpoints reject requests. Stream health becomes ready
only after required dependencies warm successfully. Run one Uvicorn process
per GPU so the per-pod admission cap cannot multiply across workers.

Backend live/PTT callers prefer `HOSTED_PARAKEET_STREAM_API_URL`; batch callers
retain `HOSTED_PARAKEET_API_URL`. The dev/prod stream Helm overlays provision
separate services and scheduling selectors; apply them after the corresponding
base environment values. Their production warm floor is 99 and maximum is 150,
subject to the [capacity qualification contract](../docs/plans/parakeet-primary/capacity-plan.md).
Do not apply a primary routing change before the dedicated capacity is ready.

`POST /__internal/drain` is pod-loopback only. It removes stream readiness and
rejects new admissions; shutdown drains leases with a bounded deadline and
bounds final flushes. The chart invokes it before termination. Counter
`parakeet_stream_admission_total{reason}` distinguishes admitted, full,
allocation-rejected, draining and not-ready requests. The existing cluster
adapter exposes active streams and recent rejection pressure to the stream HPA.

The [implementation and research record](../docs/plans/parakeet-primary/README.md)
contains fallback behavior, economics, release ordering and qualification limits.
