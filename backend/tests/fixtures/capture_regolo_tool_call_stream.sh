#!/usr/bin/env bash
# Capture a live Regolo streaming tool-call fixture for Phase 1 acceptance gate 9.
#
# Run once, manually, with a real Regolo API key. Commits the captured SSE
# stream to regolo_tool_call_stream.json so the replay test in
# test_regolo_provider.py (and future regressions) can diff against it.
#
# Usage:
#   REGOLO_API_KEY=your_key bash capture_regolo_tool_call_stream.sh
#
# Why this exists: the Define→Develop debate gate (gemini, Apr 27 2026)
# rejected the "stub-only" smoke test as too optimistic. The fixture
# captures Regolo's actual delta shape so we can verify LangChain's native
# OpenAI accumulator handles tool_calls.function.arguments chunks correctly.
# If diffs reveal divergence from OpenAI's shape, the accumulator goes in
# _RegoloChatProxy as a follow-up.

set -euo pipefail

if [[ -z "${REGOLO_API_KEY:-}" ]]; then
  echo "error: REGOLO_API_KEY env var required" >&2
  exit 1
fi

OUT="$(dirname "$0")/regolo_tool_call_stream.json"

# Single-shot streaming completion with one tool — get_weather is the
# canonical OpenAI tool-calling smoke test. The model is Llama-3.3-70B-Instruct
# because it is the Phase 1 default for tool_call workloads (per
# desktop/docs/REGOLO_INTEGRATION.md decision table) and was confirmed
# tool-capable in the Apr 22 2026 live probes.

curl -sS -N \
  -H "Authorization: Bearer ${REGOLO_API_KEY}" \
  -H "Content-Type: application/json" \
  -X POST \
  https://api.regolo.ai/v1/chat/completions \
  -d '{
    "model": "Llama-3.3-70B-Instruct",
    "stream": true,
    "messages": [
      {"role": "user", "content": "What is the weather in Paris right now?"}
    ],
    "tools": [
      {
        "type": "function",
        "function": {
          "name": "get_weather",
          "description": "Get current weather for a city",
          "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"]
          }
        }
      }
    ],
    "tool_choice": "auto"
  }' > "$OUT.raw"

# The raw output is SSE — each line is "data: {...}" or "data: [DONE]".
# Convert to a JSON array of delta objects for stable replay in tests.
python3 <<PYEOF
import json, sys
deltas = []
with open("$OUT.raw") as f:
    for line in f:
        line = line.strip()
        if not line.startswith("data: "):
            continue
        payload = line[6:]
        if payload == "[DONE]":
            break
        try:
            deltas.append(json.loads(payload))
        except json.JSONDecodeError as e:
            print(f"skipping malformed line: {line[:80]} ({e})", file=sys.stderr)
with open("$OUT", "w") as f:
    json.dump(deltas, f, indent=2)
print(f"captured {len(deltas)} deltas -> $OUT")
PYEOF

rm -f "$OUT.raw"
echo "done. commit $OUT to the repo."
