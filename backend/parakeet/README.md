# Parakeet ASR GPU service

Self-hosted speech-to-text using **NVIDIA Parakeet TDT** (`parakeet-tdt-0.6b-v3`), an open-source
**optional/extra** STT engine. **This does NOT replace Deepgram** — Deepgram stays the default; this
is an additional engine users can opt into. Same deployment shape as `backend/diarizer` and `backend/vad`:
FastAPI + CUDA on a GKE GPU node pool, reached internally by URL.

## API
- `POST /v1/transcribe` — multipart audio file (16 kHz mono) → `{"text", "segments":[{text,start,end}]}`
- `GET /health`

Diarization is **not** done here — the backend keeps using the existing diarizer/speaker-id
services. Parakeet only provides text+timestamps.

## Who uses it (opt-in only)
- **Mobile** (iOS + Android): an optional "Omi Parakeet (cloud)" engine users can select in Transcription settings.
- **Desktop** (Apple Silicon): on-device Parakeet is already available; this cloud service is the fallback for Intel Macs / unsupported languages.
- Deepgram remains the default everywhere; nothing is switched over automatically.

Backend wires in via `STTService.parakeet` + a `process_audio_parakeet()` dispatch (the STT layer is
Deepgram-only today — see `backend/utils/stt/streaming.py`), reaching this service by
`HOSTED_PARAKEET_API_URL` (cf. `HOSTED_VAD_API_URL`, `HOSTED_SPEAKER_EMBEDDING_API_URL`).

## Deploy (GKE, copies the diarizer pattern)
```bash
# Build + push image (Cloud Build / docker), then:
helm upgrade --install parakeet ./backend/charts/parakeet \
  -f ./backend/charts/parakeet/prod_omi_parakeet_values.yaml --namespace omi
```
Reserve the internal static IP `prod-parakeet-ilb-ip-address` first (matches the diarizer/vad ILB setup).

## ⚠️ Status: NOT yet verified on GPU
This is scaffolded from the diarizer pattern but **has not run on a GPU**. Before production:
1. Lock exact pins from a GPU build — NeMo's torch wheel must match the CUDA runtime (13.2) in the
   `Dockerfile`. `requirements.txt` is a starting point only.
2. Confirm the NeMo `transcribe(..., timestamps=True)` hypothesis shape (`hyp.timestamp['segment']`)
   on the deployed model version.
3. Benchmark concurrency + cost on a real L4 (target the diarizer's HPA shape: 1 GPU/replica, p99 300ms).
4. Decide batch (this `/v1/transcribe`) vs streaming (NeMo cache-aware / Sortformer) for real-time mobile.
