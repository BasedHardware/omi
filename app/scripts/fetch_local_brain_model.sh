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
# NOT a Google-published artifact, which is why the sha256 below is pinned: an
# unpinned 90 MB binary pulled by URL is not reviewable and a changed upstream
# commit would silently swap the weights this router was measured against.
#
# Pinned from the artifact this branch was measured with. If you re-export the model
# yourself, regenerate it with:
#   sha256sum app/android/app/src/main/assets/minilm.tflite
# and update the measured accuracy numbers alongside it -- the 67% held-out figure in
# the PR description was produced with exactly these weights.
MODEL_SHA256="ba7e60d9b36c0fd3886f90679bb445588f8b90e03ee0e78ea21ed9c2b363734d"
MODEL_BYTES=89923416
MODEL_URL_NOTE="third-party conversion, sha256-pinned; see README in the brain package"

if [[ -f "$DEST/minilm.tflite" ]]; then
  echo "already present: $DEST/minilm.tflite"
  exit 0
fi

mkdir -p "$DEST"
echo "downloading MiniLM-L6-v2 (90 MB) -> $DEST/minilm.tflite"
echo "note: $MODEL_URL_NOTE"

# Download to a temporary name and rename only after the digest checks out.
#
# curl -o writes straight to the target, so an exhausted --retry leaves a truncated
# file at the final path. The next run then sees it exists and exits 0, and the
# failure surfaces much later as the model failing to load inside the app. Verifying
# the digest before the rename makes a partial download impossible to mistake for a
# complete one, which is the whole reason the sha256 is pinned above.
TMP="$(mktemp "$DEST/.minilm.tflite.XXXXXX")"
trap 'rm -f "$TMP"' EXIT

curl -fSL --retry 3 -o "$TMP" "$MODEL_URL"

ACTUAL_SHA="$(sha256sum "$TMP" | cut -d' ' -f1)"
if [[ "$ACTUAL_SHA" != "$MODEL_SHA256" ]]; then
  echo "ERROR: sha256 mismatch for minilm.tflite" >&2
  echo "  expected $MODEL_SHA256" >&2
  echo "  actual   $ACTUAL_SHA" >&2
  echo "  The artifact at $MODEL_URL is not the one this router was measured with." >&2
  echo "  Re-export it yourself and update MODEL_SHA256 deliberately if intended." >&2
  exit 1
fi

ACTUAL_BYTES="$(wc -c < "$TMP" | tr -d ' ')"
if [[ "$ACTUAL_BYTES" != "$MODEL_BYTES" ]]; then
  echo "ERROR: size mismatch for minilm.tflite: expected $MODEL_BYTES, got $ACTUAL_BYTES" >&2
  exit 1
fi

mv "$TMP" "$DEST/minilm.tflite"
trap - EXIT
echo "verified sha256 and size"

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
echo "Build, install and run the dev flavor:"
echo "  cd app && flutter run --flavor dev"
echo
echo "Drive the router without tapping, via adb:"
echo "  adb logcat -c"
echo "  adb shell am start -n com.friend.ios.dev/com.friend.ios.MainActivity"
echo "  # then from Dart: await LocalBrain.instance.route('turn on the flashlight')"