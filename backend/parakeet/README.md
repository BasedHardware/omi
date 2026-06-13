# Self-Hosted NVIDIA NeMo ASR at Scale

Production-grade speech-to-text using **NVIDIA Parakeet** on Kubernetes with GPU autoscaling. Dual-model architecture: **TDT 0.6b** for batch (0.1% WER, full punctuation) and **RNNT 1.1b** for real-time streaming (3% WER, ~5s segments). Replaces Deepgram nova-3 at **100-200x lower cost** for supported languages.

**Production status**: 7,005+ requests served, 0% error rate over 24h, 0 pod restarts.

## Why Self-Host NeMo

| | Deepgram nova-3 (SaaS) | Parakeet (self-hosted) |
|---|---|---|
| **Monthly cost** (68K hrs/mo) | $40,175 gross / $20,088 net | ~$500 (L4 GPU instance) |
| **Batch WER** (English) | 0.7% | **0.1%** |
| **Code-switching WER** | 29% | **4%** |
| **Diarization error rate** | 22.0% | **9.2%** |
| **Batch latency** | 1.15s | **1.04s** |
| **Data residency** | Third-party cloud | Your cluster |
| **Language coverage** | 50+ languages | 25 European (CJK/Hindi falls back to Deepgram) |

## Architecture

```
                         ┌─────────────────────────────────────────────┐
                         │           Parakeet GPU Pod (L4)             │
                         │                                             │
  /v1/transcribe ───────►│  TDT 0.6b (batch)                         │
  /v2/transcribe ───────►│    ├── full punctuation + capitalization    │
                         │    ├── speaker diarization (pyannote)       │
                         │    └── language detection (langdetect)      │
                         │                                             │
  /v3/stream (WS) ──────►│  RNNT 1.1b (streaming)                    │
                         │    ├── Silero VAD (speech/silence detect)   │
                         │    ├── AGC (normalizes quiet BLE mic)       │
                         │    ├── chunked decoder (2s + 10s context)   │
                         │    └── cosine speaker clustering            │
                         │                                             │
                         │  GPU Semaphore ── serializes CUDA access    │
                         │  Prometheus ── metrics for HPA autoscaling  │
                         └─────────────────────────────────────────────┘

  Memory: 12.6Gi / 20Gi (BF16, both models loaded)
  GPU: NVIDIA L4 (24GB) or T4 (16GB, batch-only)
```

### Dual-Model Design

| Model | Endpoint | Use Case | WER | Punctuation | Streaming |
|-------|----------|----------|-----|-------------|-----------|
| **TDT 0.6b** (`parakeet-tdt-0.6b-v3`) | `/v1`, `/v2` | Batch transcription, voice messages, file sync | 0.1% | Yes | No |
| **RNNT 1.1b** (`parakeet-rnnt-1.1b`) | `/v3` | Real-time wearable audio, live conversations | ~3% | No (lowercase) | Yes |

TDT (Token-and-Duration Transducer) predicts both tokens and duration in one step -- best offline accuracy. RNNT (Recurrent Neural Network Transducer) carries decoder state across chunks -- true frame-by-frame streaming with autoregressive context.

Both models loaded in BF16 to fit on a single L4 GPU (12.6Gi of 24Gi used).

## Benchmarks

### English Word Error Rate (12 LibriSpeech test-clean samples, 2-27s)

| Sample | Duration | Deepgram WER | Parakeet Batch WER | Parakeet Stream WER |
|--------|----------|-------------|-------------------|-------------------|
| sample_01 | 2.2s | 0.0% | 0.0% | 0.0% |
| sample_02 | 6.6s | 0.0% | 0.0% | 0.0% |
| sample_03 | 2.3s | 0.0% | 0.0% | 0.0% |
| sample_04 | 5.3s | 0.0% | 0.0% | 6.2% |
| sample_05 | 4.6s | 0.0% | 0.0% | 0.0% |
| sample_06 | 3.3s | 0.0% | 0.0% | 0.0% |
| sample_07 | 9.2s | 0.0% | 0.0% | 3.7% |
| sample_08 | 7.5s | 0.0% | 0.0% | 0.0% |
| sample_09 | 6.9s | 4.5% | 0.0% | 4.5% |
| sample_10 | 12.2s | 0.0% | 0.0% | 3.0% |
| sample_11 | 27.2s | 2.0% | 0.0% | 11.8% |
| sample_12 | 23.7s | 1.6% | 1.6% | 6.5% |
| **Average** | | **0.7%** | **0.1%** | **3.0%** |

### Multi-Language (8 languages, edge-tts synthetic)

| Language | Deepgram WER | Parakeet WER | Notes |
|----------|-------------|-------------|-------|
| Spanish | 19% | 19% | Tie |
| French | 15% | **8%** | Parakeet edge |
| German | 8% | 8% | Tie |
| Portuguese | 8% | 8% | Tie |
| Japanese | 1900%* | 900%* | Both fail -- model lacks CJK |
| Chinese | 1100%* | 100% | Both fail -- Parakeet romanizes |
| Hindi | **0%** | 100% | Deepgram wins -- Parakeet romanizes |
| Korean | **0%** | 157% | Deepgram wins -- Parakeet romanizes |

*WER inflated by character-level tokenization. Current model (`parakeet-tdt-0.6b-v3`) covers 25 European languages. CJK/Hindi/Korean requires upgrade to Nemotron 3.5 ASR or NIM container.*

### Code-Switching (mixed-language utterances)

| Mix | Deepgram WER | Parakeet WER | Notes |
|-----|-------------|-------------|-------|
| English + Spanish | 19% | **0%** | Parakeet perfect |
| English + French + German | 61% | **6%** | Deepgram dropped entire segments |
| English + Chinese | 7% | 7% | Tie -- both dropped Chinese |
| **Average** | **29%** | **4%** | **-86% improvement** |

### Diarization Error Rate (4 multi-speaker conversations, 0.25s collar)

| Conversation | Speakers | Deepgram DER | Parakeet DER |
|-------------|----------|-------------|-------------|
| 2-speaker business (31.8s) | 2 | 11.4% | **6.6%** |
| 3-speaker meeting (46.7s) | 3 | 13.0% | **11.1%** |
| 2-speaker short (13.1s) | 2 | 49.0% | **11.1%** |
| 2-speaker long (53.0s) | 2 | 14.5% | **7.9%** |
| **Average** | | **22.0%** | **9.2%** |

Parakeet uses embedding-based greedy cosine clustering (pyannote/wespeaker-voxceleb-resnet34-LM on GPU). Deepgram's native diarization misses on short clips; Parakeet's 0% false alarm rate is the key differentiator.

### Production Metrics (T+24h, 2026-06-09)

| Metric | Value |
|--------|-------|
| Requests served | 7,005 (6,770 v2 + 235 v1) |
| Error rate | 0.00% (0 / 20,789 responses) |
| v1 batch latency | 2.88s avg (improved 31% over 24h) |
| v2 batch + diarization latency | 8.65s avg (improved 21% over 24h) |
| Pod restarts | 0 |
| Memory | 13.0Gi (stable, no leak) |
| Uptime | 24h continuous |

### Latency Improvement Over Time (GPU cache warming)

| Checkpoint | v1 Latency | v2 Latency |
|------------|-----------|-----------|
| T+2h | 4.18s | 13.2s |
| T+8h | 4.03s | 10.9s |
| T+12h | 3.65s | 9.78s |
| T+16h | 3.45s | 9.31s |
| T+20h | 2.93s | 8.53s |
| T+24h | 2.88s | 8.65s (stabilized) |

## API Reference

### `POST /v1/transcribe` -- Batch ASR

Transcribe a complete audio file. Best accuracy (0.1% WER), full punctuation.

```bash
curl -X POST http://parakeet:8080/v1/transcribe \
  -F "file=@audio.wav"
```

**Request**: Multipart form, `file` field. 16 kHz mono WAV or raw PCM.

**Response**:
```json
{
  "text": "The quick brown fox jumps over the lazy dog.",
  "segments": [
    {"text": "The quick brown fox jumps over the lazy dog.", "start": 0.0, "end": 3.4}
  ]
}
```

### `POST /v2/transcribe` -- Batch + Diarization

Same as v1 plus server-side speaker diarization and language detection.

```bash
curl -X POST http://parakeet:8080/v2/transcribe \
  -F "file=@meeting.wav" \
  -F "diarize=true"
```

**Response**:
```json
{
  "text": "Good morning. I wanted to discuss the quarterly results.",
  "segments": [
    {"text": "Good morning.", "start": 0.0, "end": 1.2, "speaker": "SPEAKER_0"},
    {"text": "I wanted to discuss the quarterly results.", "start": 2.1, "end": 4.8, "speaker": "SPEAKER_1"}
  ],
  "detected_language": "en"
}
```

### `WS /v3/stream` -- Streaming ASR

WebSocket endpoint for real-time transcription. Send raw PCM16 chunks, receive JSON segments.

```python
import asyncio
import websockets

async def stream():
    async with websockets.connect("ws://parakeet:8080/v3/stream?sample_rate=16000") as ws:
        # Send audio chunks (PCM16, 16kHz mono)
        with open("audio.raw", "rb") as f:
            while chunk := f.read(3200):  # 100ms chunks
                await ws.send(chunk)
                await asyncio.sleep(0.1)

        await ws.send("finalize")  # End session

        # Receive segments
        async for msg in ws:
            print(msg)  # {"text": "...", "start": 0.0, "end": 5.2, "speaker": "SPEAKER_0"}
```

**Query parameters**:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `sample_rate` | 16000 | Audio sample rate in Hz |
| `vad_threshold` | 0.5 | Silero VAD speech probability threshold |
| `hangover_s` | 0.8 | Seconds of silence before endpointing |

**Segment fields**: `text`, `start`, `end`, `speaker`, `is_user`, `person_id`, `detected_language`

### `GET /health` -- Health Check

Returns `{"status": "healthy"}`.

## Deployment

### Prerequisites

- Kubernetes cluster with GPU node pool (NVIDIA L4 recommended, T4 minimum)
- `nvidia-device-plugin` DaemonSet installed
- Helm 3
- HuggingFace token (for pyannote speaker embedding model download)

### Quick Start

```bash
# Deploy to production
helm upgrade --install parakeet ./backend/charts/parakeet \
  -f ./backend/charts/parakeet/prod_omi_parakeet_values.yaml \
  --namespace prod-omi-backend \
  --set "image.tag=$(git rev-parse --short HEAD)"

# Or via GitHub Actions
gh workflow run gcp_parakeet.yml -f environment=prod -f branch=main
```

### GPU Node Pool Setup (GKE)

```bash
gcloud container node-pools create parakeet-pool \
  --cluster=<CLUSTER> \
  --region=us-central1 \
  --machine-type=g2-standard-8 \
  --accelerator=type=nvidia-l4,count=1 \
  --num-nodes=1 \
  --enable-autoscaling \
  --min-nodes=1 \
  --max-nodes=10 \
  --node-labels=service=parakeet,env=prod \
  --node-taints=nvidia.com/gpu=present:NoSchedule
```

### Resource Requirements

| Configuration | GPU | GPU Memory | System Memory | CPU | Notes |
|---------------|-----|-----------|---------------|-----|-------|
| Dual model (TDT + RNNT, BF16) | L4 (24GB) | 12.6Gi | 20Gi limit | 2-3 cores | Production recommended |
| Batch only (TDT, BF16) | T4 (16GB) | ~6Gi | 12Gi limit | 2 cores | Budget option |
| NIM sidecar | L4 (24GB) | Managed | 8Gi gateway | 1 core | Future upgrade path |

### Backend Integration

The backend connects via cluster-internal service URL. Set these in GCP Secret Manager or Helm values:

```yaml
# Backend Helm values (backend-listen)
env:
  - name: HOSTED_PARAKEET_API_URL
    value: "http://prod-omi-parakeet.prod-omi-backend.svc.cluster.local:8080"
  - name: STT_PRERECORDED_MODEL
    value: "parakeet,dg-nova-3"  # Parakeet primary, Deepgram fallback
  - name: STT_SERVICE_MODELS
    value: "dg-nova-3"           # Streaming stays on Deepgram (opt-in for Parakeet)
```

**Language-based routing**: Parakeet handles 25 European languages. CJK, Hindi, Korean, Arabic automatically fall back to Deepgram nova-3 via the comma-separated model list.

## Scaling

### Horizontal Pod Autoscaler

The Helm chart includes an HPA that scales on multiple signals:

```yaml
# prod_omi_parakeet_values.yaml
autoscaling:
  enabled: true
  minReplicas: 1
  maxReplicas: 10
  streamsPerPod: 60          # Scale on active WebSocket connections
  targetGPUUtilization: 70   # Scale on GPU utilization (via DCGM)
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 600  # 10-min cooldown
    scaleUp:
      stabilizationWindowSeconds: 60   # 1-min ramp
```

### Prometheus Metrics

Built-in metrics exposed on `/metrics` (port 9091):

| Metric | Type | Description |
|--------|------|-------------|
| `parakeet_active_streams` | Gauge | Active `/v3/stream` WebSocket connections |
| `parakeet_active_batch_requests` | Gauge | Active batch transcription requests |
| `parakeet_request_duration_seconds` | Histogram | Request latency by endpoint |
| `parakeet_stream_duration_seconds` | Histogram | WebSocket session duration |

The ServiceMonitor scrapes every 15s. Prometheus Adapter rules translate these into Kubernetes metrics API for HPA consumption.

### GPU Concurrency

NeMo's `model.transcribe()` is **not thread-safe** ([NeMo #13988](https://github.com/NVIDIA/NeMo/issues/13988)). The service uses a `threading.Semaphore` to serialize GPU access:

```python
_GPU_SEMAPHORE = threading.Semaphore(int(os.getenv("PARAKEET_MAX_CONCURRENT", "1")))
```

Scale horizontally (more pods) rather than vertically (more concurrent requests per pod). Each pod handles one GPU inference at a time; the HPA adds pods as load increases.

### Throughput Estimates

| Configuration | Batch Throughput | Streaming Capacity |
|---------------|-----------------|-------------------|
| 1 pod, semaphore=1 | ~12 req/min (v1), ~7 req/min (v2) | 1 concurrent stream |
| 1 pod, batch_size=4 (planned) | ~48 req/min (v1) | 1 concurrent stream |
| 3 pods, semaphore=1 | ~36 req/min (v1) | 3 concurrent streams |
| 10 pods (HPA max) | ~120 req/min (v1) | 10 concurrent streams |

## Configuration

### Parakeet Service Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PARAKEET_MODEL` | `nvidia/parakeet-tdt-0.6b-v3` | Batch model (TDT) |
| `PARAKEET_STREAM_MODEL` | *(required)* | Streaming model (RNNT 1.1b) |
| `PARAKEET_BF16` | `1` | BF16 model loading (halves GPU memory) |
| `PARAKEET_INFERENCE_MODE` | `nemo` | `nemo` (direct) or `nim` (NIM sidecar) |
| `PARAKEET_MAX_CONCURRENT` | `1` | GPU semaphore limit |
| `PARAKEET_MAX_SPEECH_S` | `30` | Max segment duration before forced emission |
| `PARAKEET_AGC_TARGET` | `0.8` | AGC normalization target peak (0.0-1.0) |
| `PARAKEET_VAD_THRESHOLD` | `0.5` | Silero VAD speech probability threshold |
| `PARAKEET_CHUNK_S` | `2.0` | RNNT streaming chunk size in seconds |
| `PARAKEET_LEFT_CONTEXT_S` | `10.0` | RNNT left context window in seconds |
| `PARAKEET_SPEAKER_THRESHOLD` | `0.45` | Cosine distance threshold for speaker matching |
| `PARAKEET_HANGOVER_S` | `0.8` | Silence duration before endpointing |
| `HOSTED_SPEAKER_EMBEDDING_API_URL` | | External diarizer service (fallback if built-in unavailable) |
| `HUGGINGFACE_TOKEN` | | Required for pyannote speaker embedding model download |
| `NIM_INFERENCE_URL` | `http://localhost:9000` | NIM sidecar URL (when `PARAKEET_INFERENCE_MODE=nim`) |

## NIM Migration Path

Raw NeMo + FastAPI is prototype-grade per NVIDIA. The production-recommended stack is NVIDIA NIM or Triton Inference Server.

| Tier | Stack | Batching | Concurrency | Status |
|------|-------|----------|-------------|--------|
| **Current** | NeMo + FastAPI + Semaphore | 1-at-a-time | Serialized | Production (stable) |
| **Next** | NeMo + request batching | `batch_size=4-8` | Serialized | Planned |
| **Target** | NVIDIA NIM | Auto (up to 1024) | Handled | Requires NGC license |
| **Alternative** | ONNX + TensorRT + Triton | `dynamic_batching` | Handled | Free, self-managed |

`Dockerfile.nim` is included for the NIM sidecar pattern:

```bash
# NIM sidecar (requires NGC API key)
docker run -d --gpus all -p 9000:9000 \
  nvcr.io/nim/nvidia/parakeet-1-1b-rnnt-multilingual:latest

# Gateway (this service, no GPU)
docker run -p 8080:8080 \
  -e PARAKEET_INFERENCE_MODE=nim \
  -e NIM_INFERENCE_URL=http://host.docker.internal:9000 \
  parakeet-nim-gateway
```

## Running Benchmarks

Benchmark scripts are in `backend/scripts/stt/`:

```bash
cd backend

# Prepare LibriSpeech test samples (shared across benchmarks)
python scripts/stt/n_benchmark_02_prerecorded.py --prepare

# Pre-recorded WER: Deepgram vs Parakeet (12 samples)
HOSTED_PARAKEET_API_URL=http://localhost:8080 \
DEEPGRAM_API_KEY=<key> \
  python scripts/stt/u_benchmark_parakeet_prerecorded.py

# Streaming WER (12 samples via /v3/stream WebSocket)
python scripts/stt/v_benchmark_parakeet_streaming.py

# Multi-language + code-switching (11 samples, 8 languages)
python scripts/stt/w_benchmark_parakeet_multilang.py

# Diarization Error Rate (4 multi-speaker conversations)
python scripts/stt/x_benchmark_parakeet_der.py
```

## Incident History

| Date | Issue | Impact | Resolution |
|------|-------|--------|------------|
| 2026-06-08 06:15 UTC | CUDA concurrency crash | 2,103 500s over ~10 min | GPU semaphore (`PARAKEET_MAX_CONCURRENT=1`). Zero errors since. |

Root cause: 33 concurrent `/v2/transcribe` requests hit NeMo simultaneously. NeMo mutates shared state (freeze/unfreeze, preprocessor config) with no internal locking. Fixed by serializing GPU access at the application layer.

## Known Limitations

1. **No punctuation in streaming** -- RNNT outputs lowercase unpunctuated text. Batch TDT has full punctuation. Planned fix: RNNT interim segments + TDT re-transcribe on silence.
2. **CJK/Hindi/Korean** -- Current model covers 25 European languages only. Falls back to Deepgram. Upgrade path: Nemotron 3.5 ASR (40 languages) via NIM container.
3. **NeMo thread-safety** -- `model.transcribe()` is not thread-safe ([NeMo #15771](https://github.com/NVIDIA-NeMo/NeMo/issues/15771)). Semaphore serializes to 1 concurrent request per pod. Scale horizontally.
4. **Over-segmentation in diarization** -- Detects 3-5 speakers when 2-3 are present. DER is still lower than Deepgram because confusion rate is near-zero.
5. **RNNT streaming WER on long continuous narration** -- VAD false-endpoints continuous speech >7s with no silence gaps. Real conversational audio with natural pauses gets near-batch quality. Tunable via `PARAKEET_HANGOVER_S`.

## File Structure

```
backend/parakeet/
  main.py              # FastAPI app, GPU semaphore, Prometheus metrics
  transcribe.py        # NeMo/NIM model loading, batch transcription, diarization
  stream_handler.py    # RNNT streaming decoder, VAD, AGC, speaker clustering
  Dockerfile           # NeMo + CUDA 13.2 runtime (raw NeMo mode)
  Dockerfile.nim       # Lightweight gateway for NIM sidecar pattern
  requirements.txt     # Python dependencies

backend/charts/parakeet/
  values.yaml                          # Default Helm values
  prod_omi_parakeet_values.yaml        # Production overrides (L4 GPU, HPA, metrics)
  dev_omi_parakeet_values.yaml         # Dev overrides
  templates/
    hpa.yaml                           # HPA with GPU/stream/request metrics
    servicemonitor.yaml                # Prometheus ServiceMonitor
    prometheus-adapter-config.yaml     # Custom metrics for HPA
    service-metrics.yaml               # Metrics service (port 9091)

backend/scripts/stt/
  u_benchmark_parakeet_prerecorded.py  # Batch WER benchmark
  v_benchmark_parakeet_streaming.py    # Streaming WER benchmark
  w_benchmark_parakeet_multilang.py    # Multi-language + code-switching
  x_benchmark_parakeet_der.py          # Diarization error rate

.github/workflows/
  gcp_parakeet.yml                     # Deploy to GKE (dev/prod)
```
