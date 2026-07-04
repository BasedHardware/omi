#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$MACOS_DIR/../.." && pwd)"

APP_NAME="${OMI_BUNDLE_SIZE_APP_NAME:-omi-bundle-size}"
APP_PATH="/Applications/$APP_NAME.app"
BUNDLE_PATH="$MACOS_DIR/build/$APP_NAME.app"
HARNESS_DIR="$MACOS_DIR/.harness/bundle-size"
REPORT_PATH="$HARNESS_DIR/latest.txt"
JSON_PATH="$HARNESS_DIR/latest.json"
LOG_PATH="$HARNESS_DIR/run.log"
BUILD_TIMEOUT_SECONDS="${OMI_BUNDLE_SIZE_BUILD_TIMEOUT_SECONDS:-600}"
RUN_PID=""

usage() {
  cat <<'USAGE'
Usage: scripts/bundle-size-harness.sh

Builds a named macOS bundle, records size breakdowns, and runs bundle-local
runtime smoke checks for the packaged Node agent and pi-mono extension.

Environment:
  OMI_BUNDLE_SIZE_APP_NAME   Named app bundle to build (default: omi-bundle-size)
  OMI_BUNDLE_SIZE_NO_ADHOC   Set to 1 to require a real signing identity
  OMI_BUNDLE_SIZE_KEEP_APP   Set to 1 to leave the launched named app running
  OMI_BUNDLE_SIZE_BUILD_TIMEOUT_SECONDS
                             Seconds to wait for build + launch (default: 600)
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

if [[ "$APP_NAME" != omi-* ]]; then
  echo "ERROR: OMI_BUNDLE_SIZE_APP_NAME must start with omi- (got: $APP_NAME)" >&2
  exit 2
fi
if ! [[ "$BUILD_TIMEOUT_SECONDS" =~ ^[0-9]+$ ]] || ((BUILD_TIMEOUT_SECONDS < 60)); then
  echo "ERROR: OMI_BUNDLE_SIZE_BUILD_TIMEOUT_SECONDS must be an integer >= 60 (got: $BUILD_TIMEOUT_SECONDS)" >&2
  exit 2
fi

mkdir -p "$HARNESS_DIR"
: > "$LOG_PATH"

cleanup() {
  if [[ -n "$RUN_PID" ]] && kill -0 "$RUN_PID" 2>/dev/null; then
    kill "$RUN_PID" 2>/dev/null || true
    wait "$RUN_PID" 2>/dev/null || true
  fi
  cleanup_stale_run_lock_if_safe
  if [[ "${OMI_BUNDLE_SIZE_KEEP_APP:-0}" != "1" ]]; then
    local executable_path="/Applications/$APP_NAME.app/Contents/MacOS/Omi Computer"
    while read -r pid command; do
      if [[ "$pid" =~ ^[0-9]+$ && "$command" == *"$executable_path"* ]]; then
        kill "$pid" 2>/dev/null || true
      fi
    done < <(ps -axo pid=,command=)
  fi
}
trap cleanup EXIT INT TERM

cleanup_stale_run_lock_if_safe() {
  local lock_dir="${TMPDIR:-/tmp}/omi-run-sh-${USER}.lock.d"
  [[ -d "$lock_dir" ]] || return 0

  local other_run_sh=0
  while read -r pid command; do
    if [[ "$pid" =~ ^[0-9]+$ && "$command" == *"./run.sh"* ]]; then
      other_run_sh=1
      break
    fi
  done < <(ps -axo pid=,command=)

  if [[ "$other_run_sh" == "0" ]]; then
    rmdir "$lock_dir" 2>/dev/null || true
  fi
}

run_bundle_build() {
  local ad_hoc=1
  if [[ "${OMI_BUNDLE_SIZE_NO_ADHOC:-0}" == "1" ]]; then
    ad_hoc=0
  fi

  (
    cd "$MACOS_DIR"
    OMI_APP_NAME="$APP_NAME" \
      OMI_ALLOW_ADHOC_SIGN="$ad_hoc" \
      OMI_SKIP_AUTH_SEED="${OMI_SKIP_AUTH_SEED:-1}" \
      OMI_SKIP_SETTINGS_SEED="${OMI_SKIP_SETTINGS_SEED:-1}" \
      OMI_SKIP_STALE_BUNDLE_SCAN="${OMI_SKIP_STALE_BUNDLE_SCAN:-1}" \
      ./run.sh --yolo
  ) >"$LOG_PATH" 2>&1 &
  RUN_PID="$!"

  local deadline=$((SECONDS + BUILD_TIMEOUT_SECONDS))
  while kill -0 "$RUN_PID" 2>/dev/null; do
    if grep -q "Press Ctrl+C to stop all services" "$LOG_PATH"; then
      return 0
    fi
    if grep -q "ERROR:" "$LOG_PATH"; then
      tail -80 "$LOG_PATH" >&2
      return 1
    fi
    if (( SECONDS > deadline )); then
      tail -80 "$LOG_PATH" >&2
      echo "ERROR: timed out after ${BUILD_TIMEOUT_SECONDS}s waiting for bundle build" >&2
      return 1
    fi
    sleep 2
  done

  wait "$RUN_PID"
}

bytes_for_path() {
  local path="$1"
  if [[ ! -e "$path" ]]; then
    printf '0'
    return
  fi
  du -sk "$path" | awk '{print $1 * 1024}'
}

human_size() {
  local bytes="$1"
  awk -v bytes="$bytes" 'BEGIN {
    split("B KiB MiB GiB", units, " ")
    value = bytes + 0
    unit = 1
    while (value >= 1024 && unit < 4) {
      value = value / 1024
      unit++
    }
    if (unit == 1) printf "%d %s", value, units[unit]
    else printf "%.1f %s", value, units[unit]
  }'
}

smoke_packaged_runtime() {
  local app="$1"
  local node="$app/Contents/Resources/Omi Computer_Omi Computer.bundle/node"
  local pi_dir="$app/Contents/Resources/pi-mono-extension"

  "$node" --version >/dev/null
  (
    cd "$pi_dir"
    "$node" --experimental-strip-types -e "await import('./index.ts')"
  )
  (
    cd "$app/Contents/Resources/agent"
    "$node" -e "await import('./dist/adapters/pi-mono.js'); console.log('agent pi adapter import ok')" >/dev/null
  )
}

write_report() {
  local app="$1"
  local total resources agent agent_node pi pi_node binary resource_bundle symlinks

  total="$(bytes_for_path "$app")"
  resources="$(bytes_for_path "$app/Contents/Resources")"
  agent="$(bytes_for_path "$app/Contents/Resources/agent")"
  agent_node="$(bytes_for_path "$app/Contents/Resources/agent/node_modules")"
  pi="$(bytes_for_path "$app/Contents/Resources/pi-mono-extension")"
  pi_node="$(bytes_for_path "$app/Contents/Resources/pi-mono-extension/node_modules")"
  binary="$(bytes_for_path "$app/Contents/MacOS/Omi Computer")"
  resource_bundle="$(bytes_for_path "$app/Contents/Resources/Omi Computer_Omi Computer.bundle")"
  symlinks="$(find "$app/Contents/Resources/pi-mono-extension/node_modules" -type l 2>/dev/null | wc -l | tr -d ' ')"

  {
    echo "Bundle size harness report"
    echo "app: $app"
    echo "log: $LOG_PATH"
    echo
    printf "%-32s %12s\n" "total" "$(human_size "$total")"
    printf "%-32s %12s\n" "resources" "$(human_size "$resources")"
    printf "%-32s %12s\n" "agent" "$(human_size "$agent")"
    printf "%-32s %12s\n" "agent/node_modules" "$(human_size "$agent_node")"
    printf "%-32s %12s\n" "pi-mono-extension" "$(human_size "$pi")"
    printf "%-32s %12s\n" "pi-mono/node_modules" "$(human_size "$pi_node")"
    printf "%-32s %12s\n" "main executable" "$(human_size "$binary")"
    printf "%-32s %12s\n" "SPM resource bundle" "$(human_size "$resource_bundle")"
    printf "%-32s %12s\n" "pi symlinks" "$symlinks"
  } | tee "$REPORT_PATH"

  cat > "$JSON_PATH" <<JSON
{
  "app": "$app",
  "log": "$LOG_PATH",
  "sizes": {
    "total": $total,
    "resources": $resources,
    "agent": $agent,
    "agent_node_modules": $agent_node,
    "pi_mono_extension": $pi,
    "pi_mono_node_modules": $pi_node,
    "main_executable": $binary,
    "spm_resource_bundle": $resource_bundle
  },
  "pi_mono_symlinks": $symlinks
}
JSON
}

run_bundle_build

if [[ ! -d "$BUNDLE_PATH" && -d "$APP_PATH" ]]; then
  BUNDLE_PATH="$APP_PATH"
fi
if [[ ! -d "$BUNDLE_PATH" ]]; then
  echo "ERROR: bundle not found at $BUNDLE_PATH or $APP_PATH" >&2
  exit 1
fi

smoke_packaged_runtime "$BUNDLE_PATH"
write_report "$BUNDLE_PATH"
