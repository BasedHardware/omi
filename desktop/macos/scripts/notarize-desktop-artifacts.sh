#!/usr/bin/env bash
# Submit independent app or DMG identities concurrently, then staple after all are accepted.
set -euo pipefail

KIND=""
WORK_DIR=""
declare -a LABELS=()
declare -a ARTIFACTS=()

usage() {
  cat >&2 <<'EOF'
Usage: scripts/notarize-desktop-artifacts.sh --kind app|dmg --work-dir DIR \
  --artifact LABEL PATH [--artifact LABEL PATH ...]
EOF
  exit 2
}

is_safe_label() {
  [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --kind) [[ $# -ge 2 && -n "$2" ]] || usage; KIND="$2"; shift 2 ;;
    --work-dir) [[ $# -ge 2 && -n "$2" ]] || usage; WORK_DIR="$2"; shift 2 ;;
    --artifact)
      [[ $# -ge 3 && -n "$2" && -n "$3" ]] || usage
      LABELS+=("$2")
      ARTIFACTS+=("$3")
      shift 3
      ;;
    *) usage ;;
  esac
done

[[ "$KIND" == "app" || "$KIND" == "dmg" ]] || usage
[[ -n "$WORK_DIR" && ${#LABELS[@]} -gt 0 ]] || usage
: "${APP_STORE_CONNECT_KEY_IDENTIFIER:?APP_STORE_CONNECT_KEY_IDENTIFIER is required}"
: "${APP_STORE_CONNECT_PRIVATE_KEY:?APP_STORE_CONNECT_PRIVATE_KEY is required}"
: "${APP_STORE_CONNECT_ISSUER_ID:?APP_STORE_CONNECT_ISSUER_ID is required}"
if [[ "$KIND" == "dmg" ]]; then
  : "${SIGN_IDENTITY:?SIGN_IDENTITY is required for DMG notarization}"
fi

for index in "${!LABELS[@]}"; do
  label="${LABELS[$index]}"
  artifact="${ARTIFACTS[$index]}"
  is_safe_label "$label" || { echo "ERROR: unsafe artifact label: $label" >&2; exit 2; }
  for prior_index in "${!LABELS[@]}"; do
    (( prior_index < index )) || break
    [[ "${LABELS[$prior_index]}" != "$label" ]] || {
      echo "ERROR: duplicate artifact label: $label" >&2
      exit 2
    }
    [[ "${ARTIFACTS[$prior_index]}" != "$artifact" ]] || {
      echo "ERROR: duplicate artifact path: $artifact" >&2
      exit 2
    }
  done
  if [[ "$KIND" == "app" ]]; then
    [[ -d "$artifact" ]] || { echo "ERROR: app artifact not found for $label: $artifact" >&2; exit 1; }
    artifact="$(cd "$artifact" && pwd -P)"
  else
    [[ -f "$artifact" ]] || { echo "ERROR: DMG artifact not found for $label: $artifact" >&2; exit 1; }
    artifact="$(cd "$(dirname "$artifact")" && pwd -P)/$(basename "$artifact")"
  fi
  ARTIFACTS[index]="$artifact"
  for prior_index in "${!LABELS[@]}"; do
    (( prior_index < index )) || break
    [[ "${ARTIFACTS[$prior_index]}" != "$artifact" ]] || {
      echo "ERROR: duplicate artifact path: $artifact" >&2
      exit 2
    }
  done
done

mkdir -p "$WORK_DIR"
RUN_DIR="$(mktemp -d "$WORK_DIR/notarize.XXXXXX")"

if [[ "$APP_STORE_CONNECT_PRIVATE_KEY" == @file:* || "$APP_STORE_CONNECT_PRIVATE_KEY" == /* ]]; then
  NOTARY_KEY="${APP_STORE_CONNECT_PRIVATE_KEY#@file:}"
  [[ -r "$NOTARY_KEY" ]] || { echo "ERROR: notary key is not readable: $NOTARY_KEY" >&2; exit 1; }
else
  NOTARY_KEY="$RUN_DIR/AuthKey_${APP_STORE_CONNECT_KEY_IDENTIFIER}.p8"
  umask 077
  printf '%b' "$APP_STORE_CONNECT_PRIVATE_KEY" > "$NOTARY_KEY"
  chmod 0400 "$NOTARY_KEY"
  cleanup_notary_key() {
    if (( BASH_SUBSHELL == 0 )); then
      rm -f "$NOTARY_KEY"
    fi
  }
  trap cleanup_notary_key EXIT
fi

submit_one() {
  local label="$1"
  local artifact="$2"
  local job_dir="$RUN_DIR/$label"
  local submission_artifact="$artifact"
  local result status submission_id
  mkdir -p "$job_dir"

  exec >"$job_dir/job.log" 2>&1
  echo "[$label] preparing $KIND artifact: $artifact"
  if [[ "$KIND" == "app" ]]; then
    submission_artifact="$job_dir/$label.zip"
    ditto -c -k --keepParent "$artifact" "$submission_artifact"
  else
    codesign --force --sign "$SIGN_IDENTITY" "$artifact"
    codesign --verify --verbose "$artifact"
  fi

  if ! result="$(xcrun notarytool submit "$submission_artifact" \
    --key "$NOTARY_KEY" \
    --key-id "$APP_STORE_CONNECT_KEY_IDENTIFIER" \
    --issuer "$APP_STORE_CONNECT_ISSUER_ID" \
    --wait \
    --output-format json 2>"$job_dir/submit.log")"; then
    echo "[$label] ERROR: notarytool submission command failed"
    return 1
  fi
  printf '%s\n' "$result" > "$job_dir/submission.json"
  status="$(printf '%s' "$result" | python3 -c \
    "import json,sys; print(json.load(sys.stdin).get('status', ''))" 2>/dev/null || true)"
  submission_id="$(printf '%s' "$result" | python3 -c \
    "import json,sys; print(json.load(sys.stdin).get('id', ''))" 2>/dev/null || true)"
  if [[ "$status" != "Accepted" ]]; then
    echo "[$label] ERROR: notarization status is ${status:-unparseable}"
    if [[ -n "$submission_id" ]]; then
      xcrun notarytool log "$submission_id" \
        --key "$NOTARY_KEY" \
        --key-id "$APP_STORE_CONNECT_KEY_IDENTIFIER" \
        --issuer "$APP_STORE_CONNECT_ISSUER_ID" \
        >"$job_dir/notary.log" 2>&1 || true
    fi
    return 1
  fi
  echo "[$label] Accepted"
}

declare -a PIDS=()
for index in "${!LABELS[@]}"; do
  submit_one "${LABELS[$index]}" "${ARTIFACTS[$index]}" &
  PIDS+=("$!")
done

failed=0
for index in "${!PIDS[@]}"; do
  if ! wait "${PIDS[$index]}"; then
    label="${LABELS[$index]}"
    echo "ERROR: notarization failed for identity $label (log: $RUN_DIR/$label/job.log)" >&2
    for diagnostic in job.log submit.log notary.log; do
      if [[ -s "$RUN_DIR/$label/$diagnostic" ]]; then
        echo "--- $label/$diagnostic ---" >&2
        sed -n '1,240p' "$RUN_DIR/$label/$diagnostic" >&2
      fi
    done
    failed=1
  fi
done

for label in "${LABELS[@]}"; do
  rm -f "$RUN_DIR/$label/$label.zip"
done
(( failed == 0 )) || exit 1

# Do not staple anything unless every identity was accepted.
for index in "${!LABELS[@]}"; do
  label="${LABELS[$index]}"
  artifact="${ARTIFACTS[$index]}"
  if ! xcrun stapler staple "$artifact" >>"$RUN_DIR/$label/job.log" 2>&1; then
    echo "ERROR: stapling failed for identity $label (log: $RUN_DIR/$label/job.log)" >&2
    exit 1
  fi
  echo "[$label] notarized and stapled: $artifact"
done
