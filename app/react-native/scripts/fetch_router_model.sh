#!/usr/bin/env bash
# Fetches the embedding-router model into modules/local-brain/android/src/main/assets/.
#
# minilm.tflite is 90 MB and *.tflite is gitignored, so a fresh clone cannot build a
# working router without this. On a device the failure mode is now a clean rejection
# ("local brain unavailable") and a fall back to the heuristic -- but the router will
# never route anything until the model is actually here.
#
# Usage:  scripts/fetch_router_model.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/modules/local-brain/android/src/main/assets"

# Pinned to immutable Hugging Face revisions (not branch heads) and verified by SHA256.
MODEL_REV="7024b7f534f17fa9dc3c3ce5d42d85491ea971f5"
VOCAB_REV="1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
MODEL_URL="https://huggingface.co/Bombek1/all-MiniLM-L6-v2-litert/resolve/${MODEL_REV}/sentence-transformers_all-MiniLM-L6-v2.tflite"
VOCAB_URL="https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/${VOCAB_REV}/vocab.txt"
MODEL_SHA256="ba7e60d9b36c0fd3886f90679bb445588f8b90e03ee0e78ea21ed9c2b363734d"
VOCAB_SHA256="07eced375cec144d27c900241f3e339478dec958f92fddbc551f295c992038a3"

verify_sha256() {
  local file="$1"
  local expected="$2"
  local actual
  actual="$(sha256sum "$file" | awk '{print $1}')"
  if [[ "$actual" != "$expected" ]]; then
    echo "error: sha256 mismatch for $file" >&2
    echo "  expected: $expected" >&2
    echo "  actual:   $actual" >&2
    return 1
  fi
}

mkdir -p "$DEST"

if [[ -f "$DEST/minilm.tflite" ]]; then
  echo "already present: $DEST/minilm.tflite"
else
  echo "downloading MiniLM-L6-v2 (90 MB) -> $DEST/minilm.tflite"
  curl -fsSL -o "$DEST/minilm.tflite" "$MODEL_URL"
fi
verify_sha256 "$DEST/minilm.tflite" "$MODEL_SHA256"

# vocab.txt is small and needed by BertWordPiece.
if [[ -f "$DEST/vocab.txt" ]]; then
  echo "already present: $DEST/vocab.txt"
else
  echo "downloading vocab.txt -> $DEST/vocab.txt"
  curl -fsSL -o "$DEST/vocab.txt" "$VOCAB_URL"
fi
verify_sha256 "$DEST/vocab.txt" "$VOCAB_SHA256"

ls -la "$DEST"
echo
echo "Now rebuild so the assets are packaged:"
echo "  cd android && ./gradlew :app:assembleDebug"
echo
echo "Check the router actually loaded (it should log LocalBrain and stop saying"
echo "'brain: not loaded'):"
echo "  adb logcat | grep -i LocalBrain"