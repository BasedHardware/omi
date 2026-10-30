#!/usr/bin/env bash
# Run the upstream harness with real AI: OpenAI calls are served by OpenRouter (default) or Gemini
# through the local proxy (Tools/dev/llm_proxy.py). Needs a funded key: OPENROUTER_API_KEY in
# ~/.openrouter-key.env, or LLM_PROVIDER=gemini with GEMINI_API_KEY in ~/.gemini-key.env.
# Speech-to-text runs on the iPhone (on-device mode), so no Deepgram key is needed.
#
# Usage: Tools/dev/dev-up-real.sh [lan-ip]
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# The Omi repository: around this app when it lives inside it, else the sibling checkout omi-fresh.
if [ -d "$HERE/../../../../backend" ]; then DEFAULT_UPSTREAM="$HERE/../../../.."; else DEFAULT_UPSTREAM="$HERE/../../../omi-fresh"; fi
UPSTREAM="${OMI_UPSTREAM:-$DEFAULT_UPSTREAM}"
LAN="${1:-}"
PROVIDER="${LLM_PROVIDER:-openrouter}"
set -a
if [ "$PROVIDER" = openrouter ]; then source "${OPENROUTER_KEY_FILE:-$HOME/.openrouter-key.env}"; fi
[ -f "${GEMINI_KEY_FILE:-$HOME/.gemini-key.env}" ] && source "${GEMINI_KEY_FILE:-$HOME/.gemini-key.env}"
set +a
if [ "$PROVIDER" = openrouter ]; then : "${OPENROUTER_API_KEY:?OPENROUTER_API_KEY missing}"; fi
: "${GEMINI_API_KEY:?GEMINI_API_KEY missing (the harness preflight wants one even when OpenRouter serves chat)}"

pkill -f "llm_proxy.py" 2>/dev/null || true
nohup python3 "$HERE/llm_proxy.py" --provider "$PROVIDER" --gateway-port 9912 > /tmp/omi-llm-proxy.log 2>&1 &
sleep 1

# Provider keys the harness preflight requires. OpenAI goes to the proxy; Deepgram and Anthropic
# are not used by the mobile flows exercised here (on-device STT, proxy-served chat).
export OPENAI_API_KEY="local-proxy-not-a-real-openai-key"
export OPENAI_BASE_URL="http://127.0.0.1:9911/v1"
# Server speech-to-text: Deepgram nova-3 when ~/.deepgram-key.env exists (works with the app in
# the background, like production); otherwise the iPhone transcribes (Settings › Capture).
if [ -f "${DEEPGRAM_KEY_FILE:-$HOME/.deepgram-key.env}" ]; then
  set -a; source "${DEEPGRAM_KEY_FILE:-$HOME/.deepgram-key.env}"; set +a
  export STT_SERVICE_MODELS="dg-nova-3,parakeet"
else
  export DEEPGRAM_API_KEY="local-unused-deepgram"
  export STT_SERVICE_MODELS="parakeet"
fi
# Voice profiles (onboarding's voice sample): the speaker-embedding model runs locally when its venv
# exists (python3.12 -m venv ~/.venvs/omi-embedding; pip install torch==2.8.0 torchaudio==2.8.0
# pyannote.audio==4.0.3 fastapi uvicorn python-multipart soundfile).
EMBED_VENV="${OMI_EMBEDDING_VENV:-$HOME/.venvs/omi-embedding}"
if [ -x "$EMBED_VENV/bin/uvicorn" ]; then
  export HOSTED_SPEAKER_EMBEDDING_API_URL="http://127.0.0.1:8095"
fi
export ANTHROPIC_API_KEY="local-unused-anthropic"
export GEMINI_API_KEY
# The backend reaches its LLM gateway through the proxy's front (port 9912): web search is answered
# there through OpenRouter, everything else passes to the harness gateway (needs the harness patch).
export OMI_DEV_LLM_GATEWAY_URL="http://127.0.0.1:9912"
# The backend's pusher service finalizes conversations the server ends itself (silence timeouts,
# the hourly stale cleanup). The harness does not run it; without it they stay in progress forever.
PUSHER_PORT=8097
export HOSTED_PUSHER_API_URL="http://127.0.0.1:$PUSHER_PORT"
# Conversation notes as in production (v2 writer since 2026-09-01): sections plus a short gist.
export CONVERSATION_NOTES_V2_ENABLED=true

cd "$UPSTREAM"
# Save the emulators' data first: the harness imports it on start, but its export-on-exit does not
# always run when the harness is stopped, and a restart then brings back an older snapshot.
curl -s -m 30 -X POST http://127.0.0.1:4400/_admin/export -H "Content-Type: application/json" \
  -d "{\"path\":\"$UPSTREAM/.local/dev-harness/default/services/firebase-export\",\"initiatedBy\":\"dev-up-real\"}" \
  >/dev/null 2>&1 || true
make dev-down >/dev/null 2>&1 || true
if [ -n "$LAN" ]; then export OMI_DEV_HOST="$LAN"; fi
PROVIDER_MODE=real OMI_HARNESS_REDIS_PORT="${OMI_HARNESS_REDIS_PORT:-6390}" make dev-up

# The harness has no Firestore -> Typesense sync: keep conversations searchable for the agent.
pkill -f "index_conversations_typesense.py" 2>/dev/null || true
nohup python3 "$HERE/index_conversations_typesense.py" --all --watch 15 > /tmp/omi-typesense-index.log 2>&1 &
echo "conversation search index: syncing every 15 s (log /tmp/omi-typesense-index.log)"

# Started after the harness, which stops stray local services while it comes up.
if [ -n "${HOSTED_SPEAKER_EMBEDDING_API_URL:-}" ]; then
  pkill -f "speaker_embedding_shim" 2>/dev/null || true
  nohup "$EMBED_VENV/bin/uvicorn" speaker_embedding_shim:app --app-dir "$HERE" --host 127.0.0.1 --port 8095 > /tmp/omi-embedding.log 2>&1 &
  echo "voice profiles: local speaker embedding on :8095 (log /tmp/omi-embedding.log)"
fi

# Pusher with exactly the backend's environment (the harness sets emulator hosts, buckets, secrets).
pkill -f "pusher.main:app" 2>/dev/null || true
BACKEND_PID=$(lsof -ti tcp:8000 -sTCP:LISTEN | head -1)
if [ -n "$BACKEND_PID" ]; then
  ENV_FILE=$(mktemp)
  python3 "$HERE/procenv.py" "$BACKEND_PID" "$ENV_FILE"
  (cd "$UPSTREAM/backend" && python3 - "$ENV_FILE" "$PUSHER_PORT" <<'PY'
import subprocess, sys
env = {}
for line in open(sys.argv[1]):
    key, value = line.rstrip("\n").split("=", 1)
    if key not in ("PORT", "__PYVENV_LAUNCHER__", "PWD", "OLDPWD", "SHLVL", "_"):
        env[key] = value
env["PORT"] = sys.argv[2]
log = open("/tmp/omi-pusher.log", "w")
subprocess.Popen([".venv/bin/python", "-m", "uvicorn", "pusher.main:app", "--host", "127.0.0.1", "--port", sys.argv[2]],
                 env=env, stdout=log, stderr=log, start_new_session=True)
PY
  )
  rm -f "$ENV_FILE"
  echo "pusher: finalizes server-ended conversations on :$PUSHER_PORT (log /tmp/omi-pusher.log)"
fi
