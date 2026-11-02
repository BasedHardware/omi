#!/usr/bin/env bash
# Invoke from the always-on host's existing scheduler. Does not install a job.
# OMI_PERF_DEVICE=<adb serial> OMI_PERF_ARTIFACT_ROOT=<scratch> bash app/tool/perf_nightly.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
: "${OMI_PERF_DEVICE:?set the dedicated Android adb serial}"
: "${OMI_PERF_ARTIFACT_ROOT:?set an artifact directory on scratch storage}"
HEAVY="${OMI_HEAVY_BIN:-$HOME/workspace/omi/bin/omi-heavy}"
[[ -x "$HEAVY" ]] || { echo 'set OMI_HEAVY_BIN to the host heavy-command gate' >&2; exit 64; }
export OMI_HEAVY_BIN="$HEAVY"
mkdir -p "$OMI_PERF_ARTIFACT_ROOT"
LOCK="$OMI_PERF_ARTIFACT_ROOT/.nightly-lock"
mkdir "$LOCK" || { echo 'another nightly run owns the lock; inspect it before removing a stale lock' >&2; exit 75; }
trap 'rmdir "$LOCK"' EXIT
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || {
  echo 'nightly requires a clean pinned checkout; no implicit pull or reset' >&2; exit 65;
}
OUT="$OMI_PERF_ARTIFACT_ROOT/$(date -u +%Y%m%dT%H%M%SZ)"
exec_status=0
bash app/tool/perf_device_run.sh \
  --platform android --device "$OMI_PERF_DEVICE" --runs 3 --out "$OUT" || exec_status=$?
echo "nightly receipt: $OUT (exit=$exec_status)"
exit "$exec_status"
