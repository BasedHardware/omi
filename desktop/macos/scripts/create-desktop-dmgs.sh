#!/usr/bin/env bash
# Create independently staged desktop DMGs concurrently.
set -euo pipefail

WORK_DIR=""
declare -a LABELS=()
declare -a APP_PATHS=()
declare -a APP_NAMES=()
declare -a OUTPUTS=()

usage() {
  cat >&2 <<'EOF'
Usage: scripts/create-desktop-dmgs.sh --work-dir DIR \
  --dmg LABEL APP_PATH APP_NAME OUTPUT [--dmg LABEL APP_PATH APP_NAME OUTPUT ...]
EOF
  exit 2
}

is_safe_label() {
  [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --work-dir) [[ $# -ge 2 && -n "$2" ]] || usage; WORK_DIR="$2"; shift 2 ;;
    --dmg)
      [[ $# -ge 5 && -n "$2" && -n "$3" && -n "$4" && -n "$5" ]] || usage
      LABELS+=("$2")
      APP_PATHS+=("$3")
      APP_NAMES+=("$4")
      OUTPUTS+=("$5")
      shift 5
      ;;
    *) usage ;;
  esac
done

[[ -n "$WORK_DIR" && ${#LABELS[@]} -gt 0 ]] || usage
command -v dmgbuild >/dev/null 2>&1 || {
  echo "ERROR: dmgbuild must be preinstalled" >&2
  exit 1
}

for index in "${!LABELS[@]}"; do
  label="${LABELS[$index]}"
  app_path="${APP_PATHS[$index]}"
  app_name="${APP_NAMES[$index]}"
  output="${OUTPUTS[$index]}"
  is_safe_label "$label" || { echo "ERROR: unsafe DMG label: $label" >&2; exit 2; }
  [[ "$app_name" != */* && "$app_name" != "." && "$app_name" != ".." ]] || {
    echo "ERROR: unsafe app name for $label: $app_name" >&2
    exit 2
  }
  for prior_index in "${!LABELS[@]}"; do
    (( prior_index < index )) || break
    [[ "${LABELS[$prior_index]}" != "$label" ]] || {
      echo "ERROR: duplicate DMG label: $label" >&2
      exit 2
    }
    [[ "${OUTPUTS[$prior_index]}" != "$output" ]] || {
      echo "ERROR: duplicate DMG output: $output" >&2
      exit 2
    }
  done
  [[ -d "$app_path" ]] || { echo "ERROR: app not found for $label: $app_path" >&2; exit 1; }
  mkdir -p "$(dirname "$output")"
  output="$(cd "$(dirname "$output")" && pwd -P)/$(basename "$output")"
  OUTPUTS[index]="$output"
  for prior_index in "${!LABELS[@]}"; do
    (( prior_index < index )) || break
    [[ "${OUTPUTS[$prior_index]}" != "$output" ]] || {
      echo "ERROR: duplicate DMG output: $output" >&2
      exit 2
    }
  done
done

mkdir -p "$WORK_DIR"
RUN_DIR="$(mktemp -d "$WORK_DIR/dmg.XXXXXX")"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

create_one() {
  local label="$1"
  local app_path="$2"
  local app_name="$3"
  local output="$4"
  local job_dir="$RUN_DIR/$label"
  local staged_app="$job_dir/staging/$app_name.app"
  mkdir -p "$job_dir/staging"

  exec >"$job_dir/job.log" 2>&1
  echo "[$label] staging $app_path"
  ditto "$app_path" "$staged_app"

  # Finder metadata is not signed application content and breaks deep strict
  # verification after a DMG copy. Preserve the notarization ticket.
  while IFS= read -r path; do
    xattr -d com.apple.FinderInfo "$path" 2>/dev/null || true
    xattr -d com.apple.ResourceFork "$path" 2>/dev/null || true
  done < <(find "$staged_app" -print)
  codesign --verify --deep --strict --verbose=2 "$staged_app"
  xcrun stapler validate "$staged_app"

  rm -f "$output"
  dmgbuild -s "$MACOS_DIR/dmg-assets/dmgbuild_settings.py" \
    -D app_path="$staged_app" \
    -D app_name="$app_name" \
    -D assets_dir="$MACOS_DIR/dmg-assets" \
    "$app_name" \
    "$output"
  [[ -f "$output" ]] || { echo "[$label] ERROR: dmgbuild did not create $output"; return 1; }
  echo "[$label] created $output"
}

declare -a PIDS=()
for index in "${!LABELS[@]}"; do
  create_one "${LABELS[$index]}" "${APP_PATHS[$index]}" "${APP_NAMES[$index]}" "${OUTPUTS[$index]}" &
  PIDS+=("$!")
done

failed=0
for index in "${!PIDS[@]}"; do
  if ! wait "${PIDS[$index]}"; then
    echo "ERROR: DMG creation failed for identity ${LABELS[$index]} (log: $RUN_DIR/${LABELS[$index]}/job.log)" >&2
    failed=1
  fi
done
(( failed == 0 )) || exit 1

for index in "${!LABELS[@]}"; do
  echo "[${LABELS[$index]}] DMG ready: ${OUTPUTS[$index]}"
done
