# DevKit Voice Agent Dev Scripts

Local development scripts for testing Omi DevKit 2 voice-agent flows (Deepgram STT/TTS/Voice Agent + BLE speaker/mic) without the full production stack.

## Prereqs
- `backend/.env.local-dev` with `DEEPGRAM_API_KEY` (and optionally `OPENAI_API_KEY` for better turn-based replies)
- Python deps from `backend/venv` (includes `httpx`, `websockets`, `bleak`; `opuslib` + libopus for DevKit opus mic decode)
- `arecord`/`aplay` (or `ffplay`) for laptop mic/speaker modes
- DevKit 2 advertising over BLE; **only one BLE client at a time** (`MAX_CONN=1`)

## Scripts
- `tts_dev_server.py` — minimal local server: `/v2/tts/synthesize` (Deepgram TTS, supports `ulaw_8000`/`pcm_8000`), `/v4/listen` Deepgram STT relay, and basic stubs. Accepts `ADMIN_KEY`-prefixed dev tokens.
- `devkit_mic_dg_agent.py` — **live Deepgram Voice Agent** with **DevKit mic input** (opus over BLE, decoded to PCM) and output to `--output laptop|devkit|both`.
- `laptop_mic_dg_agent_devkit.py` — live Deepgram Voice Agent: laptop mic input, DevKit speaker output.
- `laptop_dg_voice_agent_live.py` — live Deepgram Voice Agent fully on laptop (mic + speaker).
- `laptop_voice_agent.py` — turn-based (record → STT → agent → TTS): laptop mic, output to `--output laptop|devkit|both` with latency/chunking instrumentation.
- `laptop_voice_agent_local.py` — turn-based, fully on laptop.
- `devkit_talk.py` — send TTS text to DevKit speaker over BLE (output test).

## Quick start
```bash
# 1) Local TTS/STT server
cd /home/palontologist/Downloads/dev/omi-app
set -a; . backend/.env.local-dev; set +a
export ADMIN_KEY=local-dev-admin-key-
backend/venv/bin/python scripts/voice_agent_dev/tts_dev_server.py

# 2) Live agent: DevKit mic + DevKit speaker
backend/venv/bin/python scripts/voice_agent_dev/devkit_mic_dg_agent.py --output devkit

# 2b) Fastest interactive (all laptop)
backend/venv/bin/python scripts/voice_agent_dev/laptop_dg_voice_agent_live.py
```

Notes: DevKit BLE speaker playback is slower than realtime due to the firmware pump protocol; live DG Agent on laptop speakers is the most responsive path. Disconnect the DevKit from the phone/app before laptop BLE scripts connect.
