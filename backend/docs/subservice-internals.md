# Backend Subservice Internals

Per-subservice internal detail moved out of `backend/AGENTS.md` (size ratchet:
`.github/scripts/check_agents_md_lean.py`). The inter-service call graph and the
deploy/runtime contracts stay in `backend/AGENTS.md` → Service Map; this file
holds what each subservice does inside its own process.

```
pusher/                 # Subservice: real-time data distribution hub (separate Docker)
                        #   - Receives audio + transcripts from backend-listen via binary WebSocket protocol
                        #   - Routes transcripts to integrations/webhooks in 1s batches
                        #   - Streams audio to ML services and developer webhooks (4s accumulation)
                        #   - Runs LLM-powered conversation analysis (memories, action items, insights)
                        #   - Batches + uploads audio to private cloud storage (60s batches, 3 retries)
                        #   - Queues speaker sample extraction (120s age minimum)
                        #   - 5 concurrent background tasks per WebSocket connection

llm_gateway/            # Subservice: internal Omi-managed LLM auto-lane gateway

diarizer/               # Subservice: speaker audio analysis (separate Docker, GPU/CUDA)
                        #   - POST /v1/diarization — speaker boundary detection (pyannote/speaker-diarization)
                        #   - POST /v1/embedding — speaker vector extraction (pyannote/embedding)
                        #   - POST /v2/embedding — alt speaker vectors (wespeaker-voxceleb-resnet34-LM)

nllb_translation/       # Subservice: self-hosted NLLB translation (separate Docker, GPU/CUDA)
                        #   - POST /v1/translate — batch sentence translation (NLLB-200 + CTranslate2)
                        #   - Prometheus metrics at /metrics, health at /health, readiness at /ready
                        #   - Fallback to Gemini 2.5 Flash-Lite when NLLB is unavailable

modal/                  # Serverless GPU services (deployed on Modal) + Cloud Run Jobs
                        #   - Speaker identification: matches segments to speech profiles (SpeechBrain, T4 GPU)
                        #   - VAD: voice activity detection (pyannote/voice-activity-detection)
                        #   - notifications-job: hourly push notifications + X sync (Cloud Run Job)
                        #   - memory-maintenance-job: canonical ST→LT maintenance (Cloud Run Job)
                        #   - knowledge-ledger-drain-job: bounded writer-mode migration (Cloud Run Job)
```
