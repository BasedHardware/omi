#!/usr/bin/env bash
# Fetches the local-brain routing model into the Android assets dir.
#
# The file is 90 MB and gitignored, matching how this app already handles models:
# OnDeviceWhisperProvider takes a modelPath and the file is fetched, not committed.
# The other two assets this needs (vocab.txt, minilm_tokens.json) ARE committed,
# because together they are the prompt contract and reading them is how you audit
# what the router sees.
#
# Usage: app/scripts/fetch_local_brain_model.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEST="$HERE/app/android/app/src/main/assets"

MODEL_URL="https://huggingface.co/Bombek1/all-MiniLM-L6-v2-litert/resolve/main/sentence-transformers_all-MiniLM-L6-v2.tflite"
# Third-party conversion of sentence-transformers/all-MiniLM-L6-v2 (Apache-2.0).
# NOT a Google-published artifact and NOT checksum-verified by this script. Export
# it yourself and pin a sha256 before relying on this in production.
MODEL_URL_NOTE="third-party conversion; see README in the brain package"

if [[ -f "$DEST/minilm.tflite" ]]; then
  echo "already present: $DEST/minilm.tflite"
  exit 0
fi

mkdir -p "$DEST"
echo "downloading MiniLM-L6-v2 (90 MB) -> $DEST/minilm.tflite"
echo "note: $MODEL_URL_NOTE"
curl -fSL --retry 3 -o "$DEST/minilm.tflite" "$MODEL_URL"

for required in vocab.txt minilm_tokens.json; do
  if [[ ! -f "$DEST/$required" ]]; then
    echo "ERROR: $required is missing and is supposed to be committed." >&2
    echo "  It carries the tokenizer vocabulary and the tool schemas; without them" >&2
    echo "  the router cannot be audited. Restore it from git rather than fetching." >&2
    exit 1
  fi
done

ls -la "$DEST/minilm.tflite"
echo
echo "Build and run:"
echo "  cd app && flutter build apk --debug"
echo
echo "Drive the router without tapping, via adb:"
echo "  adb logcat -c"
echo "  adb shell am start -n com.friend.ios.dev/com.friend.ios.MainActivity"
echo "  # then from Dart: await LocalBrain.instance.route('turn on the flashlight')"