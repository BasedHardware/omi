#!/usr/bin/env bash
# Idempotent: seed local model slots on the local daemon when they lack accounts.
set -euo pipefail

BASE_URL="${OMI_LOCAL_DAEMON_URL:-http://127.0.0.1:8765}"
BASE_URL="${BASE_URL%/}"
PROVIDER_BASE="${OMI_HYBRID_DEFAULT_CHAT_BASE_URL:-http://127.0.0.1:11434/v1}"
MODEL="${OMI_HYBRID_DEFAULT_CHAT_MODEL:-gpt-5.4-mini}"
ACCOUNT_ID="${OMI_HYBRID_DEFAULT_PROVIDER_ACCOUNT_ID:-local-openai-compatible}"

if ! curl -fsS "${BASE_URL}/health" >/dev/null 2>&1; then
  echo "seed_hybrid_defaults: daemon not healthy at ${BASE_URL}/health" >&2
  exit 1
fi

policy_json="$(curl -fsS "${BASE_URL}/v1/provider-policy")"

seed_body="$(POLICY_JSON="$policy_json" python3 - "$PROVIDER_BASE" "$MODEL" "$ACCOUNT_ID" <<'PY'
import json
import os
import sys

provider_base, model, account_id = sys.argv[1:4]
data = json.loads(os.environ["POLICY_JSON"])
policy = data.get("provider_policy") or {"version": 1}
accounts = policy.setdefault("provider_accounts", [])
slots = policy.setdefault("model_slots", {})

account = next((a for a in accounts if a.get("id") == account_id), None)
changed = False
if account is None:
    accounts.append({
        "id": account_id,
        "kind": "openai_compatible",
        "base_url": provider_base,
        "api_key": None,
        "display_name": "Local OpenAI-compatible",
        "capabilities": {
            "chat_completions": True,
            "json_mode": True,
            "tool_calls": False,
            "vision": False,
            "speech_to_text": False,
        },
        "subscription_integration": None,
    })
    changed = True

for slot, json_mode in (
    ("post_transcript", True),
    ("proactive", True),
    ("chat", False),
):
    current = slots.get(slot) or {}
    if current.get("provider_account_id"):
        continue
    slots[slot] = {
        "provider_account_id": account_id,
        "model_id": model,
        "options": {
            "json_mode": json_mode,
            "tool_support": False,
        },
    }
    changed = True

slots.setdefault("memory_search", {
    "provider_account_id": None,
    "model_id": "local_wiki",
    "options": {},
})

print(json.dumps({"changed": changed, "policy": policy}))
PY
)"

changed="$(echo "$seed_body" | python3 -c 'import json, sys; print(json.load(sys.stdin)["changed"])')"

if [ "$changed" != "True" ]; then
  echo "seed_hybrid_defaults: model slots already have provider accounts"
  exit 0
fi

body="$(echo "$seed_body" | python3 -c 'import json, sys; print(json.dumps(json.load(sys.stdin)["policy"]))')"
curl -fsS -X PUT "${BASE_URL}/v1/provider-policy" \
  -H 'content-type: application/json' \
  -d "$body" >/dev/null

echo "seed_hybrid_defaults: seeded ${ACCOUNT_ID} -> ${PROVIDER_BASE} (${MODEL})"
