#!/usr/bin/env bash
# Idempotent: seed ai_provider + chat_provider on the local daemon when unset.
set -euo pipefail

BASE_URL="${OMI_LOCAL_DAEMON_URL:-http://127.0.0.1:8765}"
BASE_URL="${BASE_URL%/}"
PROVIDER_BASE="${OMI_HYBRID_DEFAULT_CHAT_BASE_URL:-http://127.0.0.1:11434/v1}"
MODEL="${OMI_HYBRID_DEFAULT_CHAT_MODEL:-llama3.2}"

if ! curl -fsS "${BASE_URL}/health" >/dev/null 2>&1; then
  echo "seed_hybrid_defaults: daemon not healthy at ${BASE_URL}/health" >&2
  exit 1
fi

settings_json="$(curl -fsS "${BASE_URL}/v1/settings")"

has_key() {
  local key="$1"
  echo "$settings_json" | python3 -c "
import json, sys
key = sys.argv[1]
data = json.load(sys.stdin)
for s in data.get('settings', []):
    if s.get('key') != key:
        continue
    raw = s.get('value_json') or ''
    if not raw or raw == 'null':
        sys.exit(1)
    try:
        v = json.loads(raw)
    except json.JSONDecodeError:
        sys.exit(1)
    if isinstance(v, dict) and v.get('base_url'):
        sys.exit(0)
sys.exit(1)
" "$key"
}

provider_payload="$(python3 - <<PY
import json
print(json.dumps({
    "kind": "openai_compatible",
    "base_url": "${PROVIDER_BASE}",
    "model": "${MODEL}",
}))
PY
)"

updated=0
body='{}'

if ! has_key ai_provider && ! has_key provider; then
  body="$(echo "$provider_payload" | python3 -c "
import json, sys
p = json.load(sys.stdin)
print(json.dumps({'ai_provider': p}))
")"
  updated=1
  echo "seed_hybrid_defaults: will set ai_provider -> ${PROVIDER_BASE}"
fi

if ! has_key chat_provider; then
  if [ "$updated" -eq 1 ]; then
    body="$(echo "$body" | python3 -c "
import json, sys
p = json.loads(sys.stdin.read())
chat = json.loads('''${provider_payload}''')
p['chat_provider'] = chat
print(json.dumps(p))
")"
  else
    body="$(echo "$provider_payload" | python3 -c "
import json, sys
p = json.load(sys.stdin)
print(json.dumps({'chat_provider': p}))
")"
    updated=1
  fi
  echo "seed_hybrid_defaults: will set chat_provider -> ${PROVIDER_BASE}"
fi

if [ "$updated" -eq 0 ]; then
  echo "seed_hybrid_defaults: ai_provider and chat_provider already configured"
  exit 0
fi

curl -fsS -X PUT "${BASE_URL}/v1/settings" \
  -H 'content-type: application/json' \
  -d "$body" >/dev/null

echo "seed_hybrid_defaults: done"
