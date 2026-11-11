#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
HARNESS_DIR="$MACOS_DIR/.local/tts-progressive-harness"
SOURCE_WAV="$MACOS_DIR/Desktop/Sources/Resources/VoicePhrases/openai-cedar-deeper-thinking-let-me-think-that-through.wav"
SAMPLE_MP3="$HARNESS_DIR/sample.mp3"
PORT_FILE="$HARNESS_DIR/port"

mkdir -p "$HARNESS_DIR"
rm -f "$PORT_FILE"
ffmpeg -hide_banner -loglevel error -y -stream_loop 7 -i "$SOURCE_WAV" -c:a libmp3lame -b:a 64k "$SAMPLE_MP3"

python3 "$SCRIPT_DIR/slow-mp3-server.py" "$SAMPLE_MP3" "$PORT_FILE" &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT

for _ in {1..100}; do
  [[ -s "$PORT_FILE" ]] && break
  sleep 0.05
done
[[ -s "$PORT_FILE" ]] || { echo "slow MP3 server did not start" >&2; exit 1; }

PORT="$(<"$PORT_FILE")"
cd "$MACOS_DIR"
OMI_TTS_STREAM_HARNESS_URL="http://127.0.0.1:$PORT/sample.mp3" \
  xcrun swift test -c debug --package-path Desktop --filter ProgressiveTTSLocalHarnessTests
