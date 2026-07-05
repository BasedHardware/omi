#!/usr/bin/env bash
set -euo pipefail

DEVICE="${DEVICE:-2649C7E8-7E64-501B-9108-8BC6038B8C2F}"
BUNDLE="${BUNDLE:-dev.moni11811.omi}"
SOURCE="${SOURCE:-Documents/meta_glasses_runtime_proof.log}"
DEST="${DEST:-/tmp/omi-meta-glasses-runtime-proof-pulled.log}"

xcrun devicectl device copy from \
  --device "$DEVICE" \
  --domain-type appDataContainer \
  --domain-identifier "$BUNDLE" \
  --source "$SOURCE" \
  --destination "$DEST"

printf 'pulled=%s\n' "$DEST"
if [[ -f "$DEST" ]]; then
  grep -E 'MetaGlassStreamDiag|MetaGlassGestureDiag|MetaGlassRuntimeProof|videoStreamingError|micOnlyFallback' "$DEST" | tail -120 || true
fi
