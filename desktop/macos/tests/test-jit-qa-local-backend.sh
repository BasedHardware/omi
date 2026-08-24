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
grep -Fqx '  vertex_gateway: ADC-isolated loopback 127.0.0.1:18084' <<< "$safe_output"

# Test mode exists only for the pure contract matrix; it can never start a
# stack whose readiness has not refreshed real development ADC.
expect_failure() {
  if "$@" >/dev/null 2>&1; then
    echo "FAIL: expected command to fail: $*" >&2
    exit 1
  fi
}
expect_failure env JIT_QA_TEST_MODE=1 OMI_JIT_QA_LOCAL_STATE_ROOT="$state_root" \
  "$LAUNCHER" up

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
expect_failure env JIT_QA_TEST_MODE=1 OMI_JIT_QA_TARGET=local-dev-gcp \
  OMI_PYTHON_API_URL=http://127.0.0.1:18080 OMI_DESKTOP_API_URL=http://127.0.0.1:18081 \
  GOOGLE_CLOUD_PROJECT=based-hardware-dev OMI_JIT_QA_LOCAL_STATE_ROOT="$REPO_ROOT" "$LAUNCHER" check

# Cleanup remains available even after auth/project validation would fail.
env JIT_QA_TEST_MODE=1 GOOGLE_CLOUD_PROJECT=unsafe OMI_JIT_QA_LOCAL_STATE_ROOT="$state_root" \
  "$LAUNCHER" down >/dev/null

target_file="$(mktemp /tmp/jit-qa-symlink-target-XXXXXX)"
printf '%s\n' 'must-survive' > "$target_file"
rm -f "$state_root/run.json"
ln -s "$target_file" "$state_root/run.json"
expect_failure env JIT_QA_TEST_MODE=1 OMI_JIT_QA_LOCAL_STATE_ROOT="$state_root" "$LAUNCHER" down
grep -Fqx 'must-survive' "$target_file"
rm -f "$state_root/run.json" "$target_file"

printf '%s\n' '{broken' > "$state_root/run.json"
expect_failure env JIT_QA_TEST_MODE=1 OMI_JIT_QA_LOCAL_STATE_ROOT="$state_root" "$LAUNCHER" down
grep -Fqx '{broken' "$state_root/run.json"
rm -f "$state_root/run.json"

PYTHONPATH="$REPO_ROOT/scripts/dev-harness" python3 -c \
  'import importlib.util, os, sys; p=sys.argv[1]; s=importlib.util.spec_from_file_location("jit_stack", p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); assert not m._owned_process_group(os.getpgrp(), "")' \
  "$PY"

# Development ADC refresh is a cloud readiness operation, not a one-second
# loopback liveness probe. Keep its timeout bounded but independently long
# enough for a normal token refresh.
PYTHONPATH="$REPO_ROOT/scripts/dev-harness" python3 -c \
  'import importlib.util, sys; p=sys.argv[1]; s=importlib.util.spec_from_file_location("jit_stack", p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); calls=[]; m._http=lambda url, timeout=1.0, **kwargs: calls.append((url, timeout)) or (True, 200); assert m._health("vertex-gateway")[0]; assert calls[0][1] == 1.0; assert calls[1][1] == m.CLOUD_READINESS_TIMEOUT_SECONDS' \
  "$PY"

grep -Fq '18080' "$PY"
grep -Fq '18081' "$PY"
grep -Fq 'FIRESTORE_EMULATOR_HOST' "$PY"
grep -Fq 'FIREBASE_AUTH_EMULATOR_HOST' "$PY"
grep -Fq 'api.omi.me' "$PY"
grep -Fq 'api.omiapi.com' "$PY"
grep -Fq 'node_modules" / ".bin" / "firebase"' "$PY"
grep -Fq 'jit_vertex_gateway:app' "$PY"
grep -Fq 'OMI_HARNESS_PRIVATE_UMASK' "$REPO_ROOT/scripts/dev-harness/dev_harness/supervise.py"
grep -Fq 'desktop/macos/scripts/jit-qa-local-backend up' "$DOC"
grep -Fq 'jit-qa-local-backend down' "$DOC"

echo 'PASS: JIT QA local hybrid stack is fixed-port and fail-closed'
