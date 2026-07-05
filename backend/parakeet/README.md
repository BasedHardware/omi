# Parakeet ASR GPU Service

Self-hosted speech-to-text using **NVIDIA Parakeet** — multi-model architecture with TDT 0.6b (batch), RNNT 1.1b (v3 streaming), and NeMo CacheAwareRNNT (v4 streaming). Runs on GKE GPU node pool behind internal load balancer.

## API

### `POST /v1/transcribe` — Batch ASR
Multipart audio file (16 kHz mono) → `{"text", "segments": [{text, start, end}]}`
- Model: TDT 0.6b (0.1% WER)
- Full punctuation, capitalization, accurate timestamps

### `POST /v2/transcribe` — Batch + Diarization
Same as v1 plus server-side speaker diarization and language detection.
- Form param: `diarize=true` (default)
- Segments include `speaker` label
- Built-in pyannote/wespeaker embedding on GPU

### `WS /v3/stream` — Streaming ASR
WebSocket: send raw PCM16 chunks, receive JSON segments in real-time.
- Model: RNNT 1.1b with chunked decoder (2s chunks, 10s left context)
- VAD endpointing (Silero) with 5s max emission
- AGC normalization for quiet BLE microphone audio
- Built-in speaker diarization
- Query params: `sample_rate` (default 16000), `vad_threshold`, `hangover_s`
- Send text `"finalize"` to end session
- No punctuation (RNNT limitation — lowercase output)

### `WS /v4/stream` — NeMo Streaming ASR
WebSocket: send raw PCM16 chunks, receive JSON with partial/final transcripts.
- Model: NeMo CacheAwareRNNT (`nemotron-3.5-asr-streaming-0.6b`)
- Raw transcript output — backend handles text dedup + partial stability
- Concurrent session cap via `PARAKEET_MAX_CONCURRENT_STREAMS`
- Idle session reaper via `PARAKEET_STREAM_IDLE_TIMEOUT`
- Query params: `sample_rate` (default 16000)
- Send text `"finalize"` to end session
- Response: `{"stream_id", "partial_transcript", "final_transcript", "is_final"}`
- On finalize: `{"stream_id", "final_text", "status": "closed"}`

### `GET /stream/metrics` — Stream engine stats
Returns `{"total_streams_opened", "total_streams_closed", "total_chunks_processed", "total_streams_reaped", "active_streams"}`.

### `GET /health` — Health check
Returns `{"status": "healthy", "ready": true, "streaming": true/false}` (200) when models are loaded, or `{"status": "loading", "ready": false}` (503) during initialization. `streaming` indicates whether the v4 NeMo streaming pipeline is available.

### `GET /batch/metrics` — Batch engine stats
Returns `{"total_requests", "total_batches", "total_files", "rejected_requests", "pending_requests"}`.

### `GET /metrics` — Prometheus metrics
Standard Prometheus text format. Includes `parakeet_vram_used_mb`, `parakeet_vram_free_mb`, `parakeet_vram_total_mb`, `parakeet_vram_baseline_mb` gauges (live GPU VRAM via `mem_get_info`).

## Environment Variables

### Batch Model & GPU Worker

| Var | Default | Effect |
|-----|---------|--------|
| `PARAKEET_MODEL` | `nvidia/parakeet-tdt-0.6b-v3` | Batch model |
| `PARAKEET_DEVICE` | `cuda:0` | GPU device for batch inference |
| `PARAKEET_TORCH_COMPILE` | `true` | Enable torch.compile (+20-30% throughput from kernel fusion) |
| `PARAKEET_CUDA_GRAPHS` | `true` | Enable CUDA graph decoding (disable for T4/Turing GPUs) |
| `PARAKEET_GC_INTERVAL` | `50` | Full gc.collect() every N batches (gc.collect(0) per batch) |
| `PARAKEET_GPU_POLL_TIMEOUT` | `0.05` | GPU worker queue poll interval in seconds |
| `PARAKEET_BF16` | `1` | BF16 model loading (halves GPU memory) |

### Dynamic Batching

| Var | Default | Effect |
|-----|---------|--------|
| `PARAKEET_MAX_BATCH_SIZE` | `32` | Max files per GPU batch |
| `PARAKEET_BATCH_WAIT_SECONDS` | `0.002` | Timer flush interval for partial batches |
| `PARAKEET_MAX_QUEUE_DEPTH` | `4096` | Backpressure limit (503 when exceeded) |

### v3 Streaming (RNNT 1.1b)

| Var | Default | Effect |
|-----|---------|--------|
| `PARAKEET_V3_STREAM_MODEL` | (required) | v3 streaming model (RNNT 1.1b) |
| `PARAKEET_MAX_SPEECH_S` | `30` | Max segment duration before forced emission |
| `PARAKEET_AGC_TARGET` | `0.8` | AGC normalization target peak |
| `PARAKEET_VAD_THRESHOLD` | `0.5` | Silero VAD speech probability threshold |
| `PARAKEET_CHUNK_S` | `2.0` | RNNT chunk size in seconds |
| `PARAKEET_LEFT_CONTEXT_S` | `10.0` | RNNT left context in seconds |

### v4 Streaming (NeMo CacheAwareRNNT)

| Var | Default | Effect |
|-----|---------|--------|
| `PARAKEET_STREAM_MODEL` | | v4 NeMo streaming model name |
| `PARAKEET_MAX_CONCURRENT_STREAMS` | `128` | Max concurrent v4 sessions |
| `PARAKEET_STREAM_IDLE_TIMEOUT` | `300` | Seconds before idle stream is reaped |
| `PARAKEET_MAX_STREAM_DRAIN` | `16` | Max stream items drained per scheduler tick |

### Backend Integration

| Var | Default | Effect |
|-----|---------|--------|
| `PARAKEET_STREAM_VERSION` | `v3` | Which streaming version backend connects to (`v3` or `v4`) |
| `PARAKEET_PARTIAL_STABILITY_MS` | `300` | Delay before promoting stable partials (v4 only) |

### Other

| Var | Default | Effect |
|-----|---------|--------|
| `PARAKEET_INFERENCE_MODE` | `nemo` | Inference backend (`nemo` or `nim`) |
| `HOSTED_SPEAKER_EMBEDDING_API_URL` | | External diarizer fallback (optional — built-in preferred) |
| `HUGGINGFACE_TOKEN` | | For downloading pyannote speaker embedding model |

## Deploy

```bash
helm upgrade --install parakeet ./backend/charts/parakeet \
  -f ./backend/charts/parakeet/prod_omi_parakeet_values.yaml \
  --namespace prod-omi-backend
```

Backend connects via `HOSTED_PARAKEET_API_URL` (cluster-internal service URL). No auth required — service runs behind internal LB only.
