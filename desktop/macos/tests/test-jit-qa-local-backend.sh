#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(cd "$ROOT/../.." && pwd)"
LAUNCHER="$ROOT/scripts/jit-qa-local-backend"
PY="$REPO_ROOT/scripts/dev-harness/jit_qa_local_stack.py"
DOC="$ROOT/e2e/JIT_QA_LOCAL_STACK.md"

test -x "$LAUNCHER"
test -f "$PY"
test -f "$DOC"
bash -n "$LAUNCHER"
python3 -m py_compile "$PY"

# A test-mode contract check still exercises the endpoint and project fences;
# it only avoids refreshing a real ADC token. It cannot start or route a shared
# Firestore process and is not an operational bypass.
state_root="$(mktemp -d /tmp/jit-qa-local-dev-gcp-XXXXXX)"
credential_file="$(mktemp /tmp/jit-qa-credential-XXXXXX)"
printf '%s\n' '{"type":"service_account","project_id":"based-hardware-dev"}' > "$credential_file"
chmod 0644 "$credential_file"
trap 'rm -rf "$state_root" "$credential_file"' EXIT

safe_output="$(env \
  JIT_QA_TEST_MODE=1 \
  OMI_JIT_QA_TARGET=local-dev-gcp \
  OMI_PYTHON_API_URL=http://127.0.0.1:18080 \
  OMI_DESKTOP_API_URL=http://127.0.0.1:18081 \
  GOOGLE_CLOUD_PROJECT=based-hardware-dev \
  OMI_JIT_QA_LOCAL_STATE_ROOT="$state_root" \
  "$LAUNCHER" check)"
grep -Fqx 'JIT QA local stack contract: safe' <<< "$safe_output"
grep -Fqx '  main: http://127.0.0.1:18080' <<< "$safe_output"
grep -Fqx '  desktop: http://127.0.0.1:18081' <<< "$safe_output"
grep -Fqx '  firestore: emulator-only 127.0.0.1:18082' <<< "$safe_output"
grep -Fqx '  redis: owned loopback 127.0.0.1:18083' <<< "$safe_output"

expect_failure() {
  if "$@" >/dev/null 2>&1; then
    echo "FAIL: expected command to fail: $*" >&2
    exit 1
  fi
}

expect_failure env JIT_QA_TEST_MODE=1 OMI_JIT_QA_TARGET=local-dev-gcp \
  OMI_PYTHON_API_URL=https://api.omi.me OMI_DESKTOP_API_URL=http://127.0.0.1:18081 \
  GOOGLE_CLOUD_PROJECT=based-hardware-dev OMI_JIT_QA_LOCAL_STATE_ROOT="$state_root" "$LAUNCHER" check
expect_failure env JIT_QA_TEST_MODE=1 OMI_JIT_QA_TARGET=local-dev-gcp \
  OMI_PYTHON_API_URL=http://127.0.0.1:18080 OMI_DESKTOP_API_URL=https://api.omiapi.com \
  GOOGLE_CLOUD_PROJECT=based-hardware-dev OMI_JIT_QA_LOCAL_STATE_ROOT="$state_root" "$LAUNCHER" check
expect_failure env JIT_QA_TEST_MODE=1 OMI_JIT_QA_TARGET=local-dev-gcp \
  OMI_PYTHON_API_URL=http://127.0.0.1:18080 OMI_DESKTOP_API_URL=http://127.0.0.1:18081 \
  GOOGLE_CLOUD_PROJECT=based-hardware OMI_JIT_QA_LOCAL_STATE_ROOT="$state_root" "$LAUNCHER" check
expect_failure env JIT_QA_TEST_MODE=1 OMI_JIT_QA_TARGET=local-dev-gcp \
  OMI_PYTHON_API_URL=http://127.0.0.1:18080 OMI_DESKTOP_API_URL=http://127.0.0.1:18081 \
  GOOGLE_CLOUD_PROJECT=based-hardware-dev FIRESTORE_EMULATOR_HOST=firestore.googleapis.com \
  OMI_JIT_QA_LOCAL_STATE_ROOT="$state_root" "$LAUNCHER" check
expect_failure env JIT_QA_TEST_MODE=1 OMI_JIT_QA_TARGET=local-dev-gcp \
  OMI_PYTHON_API_URL=http://127.0.0.1:18080 OMI_DESKTOP_API_URL=http://127.0.0.1:18081 \
  GOOGLE_CLOUD_PROJECT=based-hardware-dev FIREBASE_AUTH_EMULATOR_HOST=127.0.0.1:9099 \
  OMI_JIT_QA_LOCAL_STATE_ROOT="$state_root" "$LAUNCHER" check
expect_failure env JIT_QA_TEST_MODE=1 OMI_JIT_QA_TARGET=local-dev-gcp \
  OMI_PYTHON_API_URL=http://127.0.0.1:18080 OMI_DESKTOP_API_URL=http://127.0.0.1:18081 \
  GOOGLE_CLOUD_PROJECT=based-hardware-dev GOOGLE_APPLICATION_CREDENTIALS="$credential_file" \
  OMI_JIT_QA_LOCAL_STATE_ROOT="$state_root" "$LAUNCHER" check

grep -Fq '18080' "$PY"
grep -Fq '18081' "$PY"
grep -Fq 'FIRESTORE_EMULATOR_HOST' "$PY"
grep -Fq 'FIREBASE_AUTH_EMULATOR_HOST' "$PY"
grep -Fq 'api.omi.me' "$PY"
grep -Fq 'api.omiapi.com' "$PY"
grep -Fq 'desktop/macos/scripts/jit-qa-local-backend up' "$DOC"
grep -Fq 'jit-qa-local-backend down' "$DOC"

echo 'PASS: JIT QA local hybrid stack is fixed-port and fail-closed'
