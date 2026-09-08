#!/usr/bin/env bash
# Manually replay a failed Codemagic desktop release against its exact signed
# artifact, optionally preceded by a clean local release build.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$MACOS_DIR/../.." && pwd)"
CODEMAGIC_APP_ID="66c95e6ec76853c447b8bcbb"
CODEMAGIC_WORKFLOW_ID="omi-desktop-swift-release"

BUILD_ID=""
FAILED_STEP=""
OUTPUT_DIR=""
RUN_CLEAN_BUILD=false

usage() {
  cat <<'USAGE'
Usage: scripts/rehearse-desktop-release.sh --codemagic-build-id ID [options]

Options:
  --codemagic-build-id ID  Exact failed Codemagic build to replay
  --failed-step PROFILE    Expected recovery profile (recorded in evidence)
  --clean                  Run a clean local release compile before artifact replay
  --output-dir PATH        Retained evidence directory (default: Ephemeral scratch)
  -h, --help               Show this help

The command is intentionally manual. It never dispatches Codemagic, creates a
tag or release, or changes Beta/Stable. CODEMAGIC_API_TOKEN must be exported;
on managed Omi Macs, source ~/.config/omi/codemagic-env.sh first.
USAGE
}

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

codemagic_get() {
  local url="$1"
  curl --fail-with-body --silent --show-error \
    --config <(printf 'header = "x-auth-token: %s"\n' "$CODEMAGIC_API_TOKEN") \
    "$url"
}

require_value() {
  [[ -n "${2:-}" && "${2:-}" != -* ]] || fail "$1 requires a value"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --codemagic-build-id) require_value "$1" "${2:-}"; BUILD_ID="$2"; shift 2 ;;
    --failed-step) require_value "$1" "${2:-}"; FAILED_STEP="$2"; shift 2 ;;
    --clean) RUN_CLEAN_BUILD=true; shift ;;
    --output-dir) require_value "$1" "${2:-}"; OUTPUT_DIR="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) fail "unknown argument: $1" ;;
  esac
done

[[ "$BUILD_ID" =~ ^[0-9a-f]{24}$ ]] || fail "--codemagic-build-id must be 24 lowercase hexadecimal characters"
: "${CODEMAGIC_API_TOKEN:?CODEMAGIC_API_TOKEN is required; source ~/.config/omi/codemagic-env.sh}"
[[ "$CODEMAGIC_API_TOKEN" =~ ^[A-Za-z0-9._~-]+$ ]] \
  || fail "CODEMAGIC_API_TOKEN contains unsupported characters"

if [[ -z "$OUTPUT_DIR" ]]; then
  scratch_root="${SCRATCH_ROOT:-/Volumes/Ephemeral/scratch}"
  [[ -d "$scratch_root" ]] || scratch_root="${TMPDIR:-/tmp}"
  OUTPUT_DIR="$scratch_root/release-rehearsals/$BUILD_ID-$(date -u +%Y%m%dT%H%M%SZ)"
fi
mkdir -p "$OUTPUT_DIR"
chmod 700 "$OUTPUT_DIR"
OUTPUT_DIR="$(cd "$OUTPUT_DIR" && pwd)"

BUILD_JSON="$OUTPUT_DIR/codemagic-build.json"
codemagic_get "https://api.codemagic.io/builds/$BUILD_ID" > "$BUILD_JSON"
chmod 600 "$BUILD_JSON"

build_field() {
  jq -er "$1" "$BUILD_JSON"
}

observed_id="$(build_field '.build._id // .build.id // .build.buildId')"
app_id="$(build_field '.build.appId')"
workflow_id="$(build_field '.build.fileWorkflowId // .build.workflowId // .build.workflow_id')"
release_tag="$(build_field '.build.tag')"
source_sha="$(build_field '.build.commit.hash // .build.commit.sha // .build.commit.id // .build.commit')"
provider_status="$(build_field '.build.status')"

[[ "$observed_id" == "$BUILD_ID" ]] || fail "Codemagic returned a different build id"
[[ "$app_id" == "$CODEMAGIC_APP_ID" ]] || fail "Codemagic build belongs to unexpected app $app_id"
[[ "$workflow_id" == "$CODEMAGIC_WORKFLOW_ID" ]] || fail "unexpected Codemagic workflow $workflow_id"
[[ "$release_tag" =~ ^v[0-9]+[.][0-9]+[.][0-9]+[+][0-9]+-macos$ ]] || fail "invalid release tag from Codemagic"
[[ "$source_sha" =~ ^[0-9a-f]{40}$ ]] || fail "invalid source SHA from Codemagic"
[[ "$provider_status" == "failed" ]] || fail "rehearsal requires a failed Codemagic build, got $provider_status"
git -C "$REPO_ROOT" cat-file -e "$source_sha^{commit}" || fail "source SHA is not available locally: $source_sha"

failed_step_count="$(
  jq -er '[.build.buildActions[] as $action | (($action.subactions[]? // $action) | select(.status == "failed"))] | length' "$BUILD_JSON"
)"
[[ "$failed_step_count" == "1" ]] || fail "expected exactly one failed Codemagic step, found $failed_step_count"
failed_step_name="$(
  jq -er '[.build.buildActions[] as $action | (($action.subactions[]? // $action) | select(.status == "failed") | (.name // $action.name))] | .[0]' "$BUILD_JSON"
)"
failed_log_url="$(
  jq -er '[.build.buildActions[] as $action | (($action.subactions[]? // $action) | select(.status == "failed") | (.logUrl // $action.logUrl))] | .[0]' "$BUILD_JSON"
)"
[[ "$failed_log_url" =~ ^https://api[.]codemagic[.]io/builds/$BUILD_ID/(step/[0-9a-f]{24}|logs/[0-9]+)$ ]] \
  || fail "Codemagic returned an unsafe failed-step log URL"

codemagic_get "$failed_log_url" > "$OUTPUT_DIR/codemagic-failed-step.log"
chmod 600 "$OUTPUT_DIR/codemagic-failed-step.log"

case "$failed_step_name" in
  "Audit app bundle dependencies") observed_profile="bundle-audit" ;;
  "Smoke signed desktop artifact") observed_profile="stable-signed-smoke" ;;
  "Smoke signed desktop beta artifact") observed_profile="beta-signed-smoke" ;;
  *) fail "failed step is not locally rehearsable: $failed_step_name" ;;
esac
if [[ -n "$FAILED_STEP" && "$FAILED_STEP" != "$observed_profile" ]]; then
  fail "requested failure profile $FAILED_STEP does not match observed profile $observed_profile"
fi

artifact_name="Omi.zip"
app_name="Omi.app"
if [[ "$observed_profile" == "bundle-audit" ]]; then
  artifact_name="Omi.app.zip"
elif [[ "$observed_profile" == "beta-signed-smoke" ]]; then
  artifact_name="Omi.Beta.zip"
  app_name="Omi Beta.app"
fi

artifact_count="$(
  jq -er --arg artifact "$artifact_name" '[.build.artefacts[] | select((.name // .path // .fileName) == $artifact)] | length' "$BUILD_JSON"
)"
[[ "$artifact_count" == "1" ]] || fail "expected exactly one $artifact_name artifact, found $artifact_count"
artifact_url="$(
  jq -er --arg artifact "$artifact_name" '[.build.artefacts[] | select((.name // .path // .fileName) == $artifact) | (.url // .secureUrl // .downloadUrl)] | .[0]' "$BUILD_JSON"
)"
[[ "$artifact_url" =~ ^https://api[.]codemagic[.]io/artifacts/ ]] || fail "Codemagic $artifact_name URL is missing or unsafe"

echo "Rehearsing $release_tag ($source_sha) from Codemagic build $BUILD_ID"
echo "Provider failure: $failed_step_name"

if [[ "$RUN_CLEAN_BUILD" == true ]]; then
  clean_scratch="$OUTPUT_DIR/swift-release"
  clean_timeout_seconds="${OMI_RELEASE_REHEARSAL_CLEAN_TIMEOUT_SECONDS:-2700}"
  [[ "$clean_timeout_seconds" =~ ^[0-9]+$ ]] \
    || fail "OMI_RELEASE_REHEARSAL_CLEAN_TIMEOUT_SECONDS must be an integer of at least 60"
  clean_timeout_decimal=$((10#$clean_timeout_seconds))
  (( clean_timeout_decimal >= 60 )) \
    || fail "OMI_RELEASE_REHEARSAL_CLEAN_TIMEOUT_SECONDS must be an integer of at least 60"
  mkdir -p "$clean_scratch"
  echo "== Clean local release compile"
  python3 - "$MACOS_DIR" "$clean_scratch" "$clean_timeout_decimal" 2>&1 <<'PY' | tee "$OUTPUT_DIR/clean-release-build.log"
import os
import signal
import subprocess
import sys

working_directory, scratch_path, timeout_text = sys.argv[1:]
command = [
    "xcrun", "swift", "build", "-c", "release", "--package-path", "Desktop",
    "--scratch-path", scratch_path, "--triple", "arm64-apple-macosx",
]
process = subprocess.Popen(command, cwd=working_directory, start_new_session=True)
try:
    raise SystemExit(process.wait(timeout=int(timeout_text)))
except subprocess.TimeoutExpired:
    print(f"FAIL: clean local release compile exceeded {timeout_text}s", file=sys.stderr)
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()
    raise SystemExit(124)
PY
fi

echo "== Download exact signed Sparkle artifact"
artifact_headers="$OUTPUT_DIR/codemagic-artifact-headers.txt"
curl --fail-with-body --silent --show-error --head \
  --config <(printf 'header = "x-auth-token: %s"\n' "$CODEMAGIC_API_TOKEN") \
  --dump-header "$artifact_headers" \
  --output /dev/null \
  "$artifact_url"
signed_artifact_url="$(awk 'BEGIN { IGNORECASE=1 } /^location:/ { sub(/^[^:]+:[[:space:]]*/, ""); sub(/\r$/, ""); print; exit }' "$artifact_headers")"
rm -f "$artifact_headers"
[[ "$signed_artifact_url" != *$'\r'* && "$signed_artifact_url" != *$'\n'* && "$signed_artifact_url" != *'"'* && "$signed_artifact_url" != *'\\'* ]] \
  || fail "Codemagic artifact redirect contains unsafe characters"
[[ "$signed_artifact_url" =~ ^https://storage[.]googleapis[.]com/codemagic-build-artifacts/ ]] \
  || fail "Codemagic artifact redirect is missing or unsafe"
curl --fail-with-body --silent --show-error \
  --config <(printf 'url = "%s"\n' "$signed_artifact_url") \
  > "$OUTPUT_DIR/$artifact_name"
chmod 600 "$OUTPUT_DIR/$artifact_name"

exact_app_dir="$OUTPUT_DIR/exact-artifact"
mkdir -p "$exact_app_dir"
ditto -x -k "$OUTPUT_DIR/$artifact_name" "$exact_app_dir"
exact_app="$exact_app_dir/$app_name"
[[ -d "$exact_app/Contents" ]] || fail "$artifact_name did not contain exact $app_name"

if [[ "$observed_profile" == "bundle-audit" ]]; then
  echo "== Replay app bundle dependency audit"
  set +e
  "$SCRIPT_DIR/audit-desktop-bundle-deps.sh" "$exact_app" \
    > >(tee "$OUTPUT_DIR/rehearsal-audit.log") \
    2> >(tee "$OUTPUT_DIR/rehearsal-audit.err" >&2)
  gate_status=$?
  set -e
else
  echo "== Replay $observed_profile signed-artifact smoke"
  identity_args=()
  if [[ "$observed_profile" == "beta-signed-smoke" ]]; then
    identity_args+=(
      --expected-bundle-id com.omi.computer-macos.beta
      --expected-feed-url 'https://api.omi.me/v2/desktop/appcast.xml?identity=beta'
      --expected-python-api-url 'https://api.omiapi.com/'
      --expected-desktop-api-url 'https://desktop-backend-dt5lrfkkoa-uc.a.run.app/'
    )
  fi
  set +e
  OMI_SIGNED_ARTIFACT_SMOKE_ALLOW_PRODUCTION_LAUNCH=1 \
    "$SCRIPT_DIR/smoke-signed-desktop-artifact.sh" \
      --app "$exact_app" \
      --zip "$OUTPUT_DIR/$artifact_name" \
      --tag "$release_tag" \
      --source-sha "$source_sha" \
      --expected-channel beta \
      "${identity_args[@]}" \
      --launch \
      --auth-storage-canary \
      --notification-callback-canary \
      --timeout 90 \
      --result-json "$OUTPUT_DIR/desktop-smoke-result.json" \
      > >(tee "$OUTPUT_DIR/rehearsal-smoke.log") \
      2> >(tee "$OUTPUT_DIR/rehearsal-smoke.err" >&2)
  gate_status=$?
  set -e
fi

current_head_sha="$(git -C "$REPO_ROOT" rev-parse HEAD)"
current_worktree_dirty=false
[[ -z "$(git -C "$REPO_ROOT" status --porcelain)" ]] || current_worktree_dirty=true
current_diff_sha256="$(git -C "$REPO_ROOT" diff --binary HEAD | shasum -a 256 | awk '{print $1}')"

python3 - "$OUTPUT_DIR/rehearsal-evidence.json" <<PY
import json
from pathlib import Path

Path("$OUTPUT_DIR/rehearsal-evidence.json").write_text(json.dumps({
    "schema": "desktop-release-rehearsal/v1",
    "codemagic_build_id": "$BUILD_ID",
    "release_tag": "$release_tag",
    "source_sha": "$source_sha",
    "current_head_sha": "$current_head_sha",
    "current_worktree_dirty": $([[ "$current_worktree_dirty" == true ]] && echo True || echo False),
    "current_tracked_diff_sha256": "$current_diff_sha256",
    "provider_failed_step": "$failed_step_name",
    "requested_failure_profile": "$FAILED_STEP" or None,
    "clean_release_compile": $([[ "$RUN_CLEAN_BUILD" == true ]] && echo True || echo False),
    "rehearsed_gate_passed": $([[ "$gate_status" -eq 0 ]] && echo True || echo False),
    "signed_artifact_smoke_passed": $(if [[ "$observed_profile" == "bundle-audit" ]]; then echo None; elif [[ "$gate_status" -eq 0 ]]; then echo True; else echo False; fi),
}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
chmod 600 "$OUTPUT_DIR/rehearsal-evidence.json"

echo "Rehearsal evidence: $OUTPUT_DIR"
[[ "$gate_status" -eq 0 ]] || exit "$gate_status"
echo "Desktop release rehearsal passed"
