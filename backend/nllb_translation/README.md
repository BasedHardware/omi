# NLLB Translation Service

Self-hosted translation using **Meta NLLB-200** (No Language Left Behind) — a 200-language neural machine translation model running on GPU via CTranslate2. Replaces Google Cloud Translation V3 for realtime transcript translation in the Omi listen pipeline.

## Architecture

```
backend-listen (transcribe.py)
  └── TranslationCoordinator
        └── TranslationService._translate_nllb_batch()
              └── POST http://nllb-translation:8080/v1/translate
                    └── CTranslate2 + SentencePiece (GPU inference)
```

The backend auto-detects source language via `langdetect` before each NLLB call, passing the detected BCP-47 code as `source_language_code` so the model receives proper source language tokens. If NLLB fails, the backend falls back to Google Cloud Translation V3 automatically.

## API

### `POST /v1/translate` — Batch Translation

```json
{
  "contents": ["Hello, how are you?", "Nice to meet you."],
  "target_language_code": "es",
  "source_language_code": "en"
}
```

Response:
```json
{
  "translations": [
    {"translated_text": "Hola, ¿cómo estás?", "detected_language_code": "en"},
    {"translated_text": "Encantado de conocerte.", "detected_language_code": "en"}
  ],
  "model": "facebook/nllb-200-distilled-600M",
  "latency_ms": 42.3
}
```

- `source_language_code` is optional — omit for auto-detect (no source token prefix)
- `contents` max batch size controlled by `NLLB_MAX_BATCH_SIZE` (default 64)
- Language codes: BCP-47 (en, es, zh-CN, etc.) or NLLB native (eng_Latn, spa_Latn, etc.)

### `GET /health` — Health Check

Returns model config and load status. Used by startup probe.

### `GET /ready` — Readiness

Returns 200 when model is loaded and ready for inference, 503 otherwise. Used by readiness probe.

### `GET /metrics` — Prometheus Metrics

Standard Prometheus exposition format. Metrics include:
- `nllb_requests_total` — by target_lang and status (ok/error/unsupported)
- `nllb_translation_latency_seconds` — end-to-end latency histogram
- `nllb_inference_latency_seconds` — pure CTranslate2 inference (excludes tokenization)
- `nllb_tokenization_latency_seconds` — SentencePiece tokenization
- `nllb_chars_translated_total` — character throughput
- `nllb_sentences_translated_total` — sentence throughput
- `nllb_batch_size` — batch size distribution
- `nllb_active_requests` — concurrent request gauge
- `nllb_model_loaded` — model readiness gauge

## Supported Languages

22 languages mapped from BCP-47 to NLLB tokens:

| BCP-47 | NLLB Token | Language |
|--------|-----------|----------|
| en | eng_Latn | English |
| es | spa_Latn | Spanish |
| zh / zh-CN | zho_Hans | Chinese (Simplified) |
| zh-TW | zho_Hant | Chinese (Traditional) |
| hi | hin_Deva | Hindi |
| pt / pt-BR | por_Latn | Portuguese |
| ru | rus_Cyrl | Russian |
| ja | jpn_Jpan | Japanese |
| de | deu_Latn | German |
| ar | arb_Arab | Arabic |
| fr | fra_Latn | French |
| it | ita_Latn | Italian |
| ko | kor_Hang | Korean |
| nl | nld_Latn | Dutch |
| th | tha_Thai | Thai |
| tr | tur_Latn | Turkish |
| uk | ukr_Cyrl | Ukrainian |
| ur | urd_Arab | Urdu |
| vi | vie_Latn | Vietnamese |

Unsupported language codes return HTTP 400.

## Environment Variables

| Var | Default | Effect |
|-----|---------|--------|
| `NLLB_MODEL_DIR` | `/models/nllb-200-distilled-600M-ct2-int8` | Path to CTranslate2 model directory |
| `CT2_DEVICE` | `cuda` | Inference device (`cuda` or `cpu`) |
| `CT2_COMPUTE_TYPE` | `int8_float16` | CTranslate2 compute type |
| `CT2_INTER_THREADS` | `1` | Inter-op parallelism threads |
| `CT2_INTRA_THREADS` | `4` | Intra-op parallelism threads |
| `NLLB_MAX_INPUT_LENGTH` | `512` | Max source tokens per sentence |
| `NLLB_MAX_BATCH_SIZE` | `64` | Max sentences per request |
| `NLLB_BEAM_SIZE` | `1` | Beam search width (1 = greedy, fastest) |
| `NLLB_INFERENCE_WORKERS` | `2` | Thread pool size for GPU inference |
| `PORT` | `8080` | Server port |

## Performance

Benchmarked on NVIDIA L4 GPU with 600M INT8 model, greedy decoding:

| Metric | Value |
|--------|-------|
| Single sentence p50 | ~50ms |
| Single sentence p99 | < 200ms |
| 10-sentence batch | ~83ms |
| Cold start (first request) | ~260ms |
| Warm steady-state | ~40ms |
| Peak throughput | 30 sentences/sec |

See `TUNING_RESULTS.md` for the full tuning sweep across beam sizes, compute types, and thread configs.

## Backend Integration

The backend uses NLLB via the `TranslationProvider` enum in `utils/translation.py`. Provider is controlled exclusively by `TRANSLATION_SERVICE_MODELS` — the URL alone never changes provider.

```bash
# 1. Google only (default — no config needed)
# TRANSLATION_SERVICE_MODELS is unset

# 2. NLLB primary with Google fallback (recommended)
TRANSLATION_SERVICE_MODELS=nllb,google

# 3. NLLB only (no fallback)
TRANSLATION_SERVICE_MODELS=nllb
```

`HOSTED_TRANSLATION_API_URL` must also be set for `nllb` to activate.

## Deploy

### Prerequisites
- GKE cluster with GPU node pool (NVIDIA L4, `cloud.google.com/gke-accelerator: nvidia-l4`)
- GPU tolerations configured (`nvidia.com/gpu: NoSchedule`)

### Deploy to GKE

Via GitHub Actions (recommended):
```bash
gh workflow run gcp_nllb_translation.yml \
  -f environment=development \
  -f branch=main
```

Via Helm directly:
```bash
helm upgrade --install dev-omi-nllb-translation \
  ./backend/charts/nllb-translation \
  -f ./backend/charts/nllb-translation/dev_omi_nllb_translation_values.yaml \
  --namespace dev-omi-backend
```

The model is downloaded automatically by an init container from HuggingFace on first deploy (~600MB, pinned revision).

### Wire backend

After NLLB is deployed, set `HOSTED_TRANSLATION_API_URL` in the backend-listen Helm values:
```yaml
- name: HOSTED_TRANSLATION_API_URL
  value: "http://dev-omi-nllb-translation:8080"
```

Then set `TRANSLATION_SERVICE_MODELS=nllb,google` and restart the backend.

## Local Development

```bash
# Requires NVIDIA GPU with CUDA
cd backend/nllb_translation
pip install -r requirements.txt
# Download model
python3 -c "from huggingface_hub import snapshot_download; snapshot_download('JustFrederik/nllb-200-distilled-600M-ct2-int8', local_dir='/tmp/nllb-model')"
NLLB_MODEL_DIR=/tmp/nllb-model python3 -m uvicorn main:app --port 8080
```

For CPU-only testing (slower):
```bash
CT2_DEVICE=cpu CT2_COMPUTE_TYPE=int8 NLLB_MODEL_DIR=/tmp/nllb-model python3 -m uvicorn main:app --port 8080
```
