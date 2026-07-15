#!/usr/bin/env bash
# Live, non-production PTT current-screen probe.
#
# It intentionally drives the controller-owned `ptt_test_turn` action rather than a separate
# screenshot fixture, so the result exercises the physical capture → transport receipt → model
# report → reducer completion path that a real PTT press uses.
#
# Usage:
#   OMI_AUTOMATION_PORT=47920 bash scripts/ptt-screen-probe.sh
#   bash scripts/ptt-screen-probe.sh --port 47920
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PORT="${OMI_AUTOMATION_PORT:-}"

usage() {
  echo "Usage: OMI_AUTOMATION_PORT=<port> $0 [--port <port>]" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port)
      if [[ $# -lt 2 || -z "${2:-}" ]]; then
        usage
        exit 2
      fi
      PORT="${2:-}"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

if [[ -z "$PORT" ]]; then
  usage
  exit 2
fi
export OMI_AUTOMATION_PORT="$PORT"

CTL="$SCRIPT_DIR/omi-ctl"
if [[ ! -x "$CTL" ]]; then
  echo "ptt-screen-probe: missing executable $CTL" >&2
  exit 2
fi
for command in say ffmpeg python3; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "ptt-screen-probe: missing required command: $command" >&2
    exit 2
  fi
done

TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/omi-ptt-screen-probe.XXXXXX")"
trap 'rm -rf "$TEMP_DIR"' EXIT
AIFF="$TEMP_DIR/prompt.aiff"
PCM="$TEMP_DIR/prompt.pcm"
RESULT="$TEMP_DIR/result.json"

say -o "$AIFF" "What is on my screen?"
ffmpeg -hide_banner -loglevel error -y -i "$AIFF" -ac 1 -ar 16000 -f s16le "$PCM"
"$CTL" action ptt_test_turn \
  pcm="$PCM" \
  timeout=30 \
  force_transcript='What is on my screen?' \
  text_only=1 >"$RESULT"

python3 - "$RESULT" <<'PY'
import json
import sys

result_path = sys.argv[1]
with open(result_path, encoding="utf-8") as handle:
    payload = json.load(handle)
detail = payload.get("result", {}).get("detail", {})
safe_keys = (
    "error",
    "phase",
    "terminal_reason",
    "pending_tool_count",
    "post_tool_continuation_required",
    "provider_finished",
    "screen_evidence_state",
    "screen_evidence_protocol_active",
    "screen_evidence_last_completion",
)
print(json.dumps({key: detail.get(key, "") for key in safe_keys}, sort_keys=True))

failure = (
    not payload.get("ok", False)
    or detail.get("error")
    or detail.get("terminal_reason") != "success"
    or detail.get("pending_tool_count") != "0"
    or detail.get("screen_evidence_protocol_active") != "false"
    or detail.get("screen_evidence_last_completion") != "completed"
)
sys.exit(1 if failure else 0)
PY
