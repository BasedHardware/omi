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
MODEL_URL="https://huggingface.co/Bombek1/all-MiniLM-L6-v2-litert/resolve/main/sentence-transformers_all-MiniLM-L6-v2.tflite"
VOCAB_URL="https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/main/vocab.txt"

mkdir -p "$DEST"

if [[ -f "$DEST/minilm.tflite" ]]; then
  echo "already present: $DEST/minilm.tflite"
else
  echo "downloading MiniLM-L6-v2 (90 MB) -> $DEST/minilm.tflite"
  curl -fsSL -o "$DEST/minilm.tflite" "$MODEL_URL"
fi

# vocab.txt is small and needed by BertWordPiece. Not committed, because the
# Android side of this module has no assets directory in git at all yet -- see the
# README.
if [[ -f "$DEST/vocab.txt" ]]; then
  echo "already present: $DEST/vocab.txt"
else
  echo "downloading vocab.txt -> $DEST/vocab.txt"
  curl -fsSL -o "$DEST/vocab.txt" "$VOCAB_URL"
fi

ls -la "$DEST"
echo
echo "Now rebuild so the assets are packaged:"
echo "  cd android && ./gradlew :app:assembleDebug"
echo
echo "Check the router actually loaded (it should log LocalBrain and stop saying"
echo "'brain: not loaded'):"
echo "  adb logcat | grep -i LocalBrain"