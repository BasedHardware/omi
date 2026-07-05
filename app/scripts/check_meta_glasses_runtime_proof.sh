#!/usr/bin/env bash
set -euo pipefail

LOG="${1:-${LOG:-/tmp/omi-meta-glasses-runtime-proof-pulled.log}}"

if [[ ! -f "$LOG" ]]; then
  echo "missing_log=$LOG"
  exit 2
fi

latest_window="$(awk '
  /MetaGlassRuntimeProof provider-init/ {buf=$0 ORS; next}
  {buf=buf $0 ORS}
  END {printf "%s", buf}
' "$LOG")"

count() {
  grep -F -c "$1" <<<"$latest_window" || true
}

provider_init="$(count 'MetaGlassRuntimeProof provider-init')"
not_ready="$(count 'auto-start-skip reason=not-ready')"
stream_started="$(count 'MetaGlassStreamDiag stream-started')"
frame_event="$(count 'MetaGlassStreamDiag frame-event')"
frame_captured="$(count 'MetaGlassStreamDiag frame-captured')"
gestures_unsupported="$(count 'gestures=unsupported')"
stream_failed="$(count 'MetaGlassStreamDiag stream-start-failed')"

printf 'provider_init=%s\n' "$provider_init"
printf 'not_ready=%s\n' "$not_ready"
printf 'stream_started=%s\n' "$stream_started"
printf 'frame_event=%s\n' "$frame_event"
printf 'frame_captured=%s\n' "$frame_captured"
printf 'gestures_unsupported=%s\n' "$gestures_unsupported"
printf 'stream_failed=%s\n' "$stream_failed"

if (( stream_started > 0 && frame_event > 0 && frame_captured > 0 )); then
  echo "meta_glasses_runtime_proof=pass"
  exit 0
fi

if (( not_ready > 0 && stream_started == 0 && frame_event == 0 && frame_captured == 0 )); then
  echo "meta_glasses_runtime_proof=pending_not_ready"
else
  echo "meta_glasses_runtime_proof=fail"
fi
exit 1
