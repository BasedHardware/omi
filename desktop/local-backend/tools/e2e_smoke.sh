#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${OMI_LOCAL_BACKEND_SMOKE_DATA_DIR:-$(mktemp -d /tmp/omi-local-backend-smoke.XXXXXX)}"
PORT="${OMI_LOCAL_BACKEND_SMOKE_PORT:-$(python3 - <<'PY'
import socket
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.bind(("127.0.0.1", 0))
    print(s.getsockname()[1])
PY
)}"
BASE_URL="http://127.0.0.1:${PORT}"
LOG_FILE="${DATA_DIR}/daemon.log"

DAEMON_PID=""

cleanup() {
  if [[ -n "${DAEMON_PID}" ]] && kill -0 "${DAEMON_PID}" >/dev/null 2>&1; then
    kill "${DAEMON_PID}" >/dev/null 2>&1 || true
    wait "${DAEMON_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

json_value() {
  python3 - "$1" "$2" <<'PY'
import json
import sys

path = sys.argv[1].split(".")
with open(sys.argv[2], "r", encoding="utf-8") as handle:
    value = json.load(handle)
for part in path:
    if part.isdigit():
        value = value[int(part)]
    else:
        value = value[part]
print(value)
PY
}

json_embedded_value() {
  python3 - "$1" "$2" "$3" <<'PY'
import json
import sys

path = sys.argv[1].split(".")
with open(sys.argv[2], "r", encoding="utf-8") as handle:
    value = json.load(handle)
for part in path[:-1]:
    if part.isdigit():
        value = value[int(part)]
    else:
        value = value[part]
embedded = json.loads(value[path[-1]])
print(embedded[sys.argv[3]])
PY
}

request() {
  local method="$1"
  local path="$2"
  local body="${3:-}"
  local output
  output="$(mktemp)"
  if [[ -n "${body}" ]]; then
    curl -fsS -X "${method}" "${BASE_URL}${path}" \
      -H "Content-Type: application/json" \
      --data "${body}" \
      -o "${output}"
  else
    curl -fsS -X "${method}" "${BASE_URL}${path}" -o "${output}"
  fi
  printf '%s\n' "${output}"
}

assert_json_value() {
  local file="$1"
  local path="$2"
  local expected="$3"
  local actual
  actual="$(json_value "${path}" "${file}")"
  if [[ "${actual}" != "${expected}" ]]; then
    echo "Expected ${path}=${expected}, got ${actual}" >&2
    echo "Response file: ${file}" >&2
    exit 1
  fi
}

start_daemon() {
  OMI_LOCAL_BACKEND_HOST=127.0.0.1 \
  OMI_LOCAL_BACKEND_PORT="${PORT}" \
  OMI_LOCAL_BACKEND_DATA_DIR="${DATA_DIR}" \
    cargo run --quiet --manifest-path "${ROOT_DIR}/Cargo.toml" >"${LOG_FILE}" 2>&1 &
  DAEMON_PID="$!"

  for _ in $(seq 1 80); do
    if curl -fsS "${BASE_URL}/health" >/dev/null 2>&1; then
      return
    fi
    if ! kill -0 "${DAEMON_PID}" >/dev/null 2>&1; then
      echo "Daemon exited during startup. Log:" >&2
      sed -n '1,160p' "${LOG_FILE}" >&2 || true
      exit 1
    fi
    sleep 0.25
  done

  echo "Timed out waiting for daemon health at ${BASE_URL}/health. Log:" >&2
  sed -n '1,160p' "${LOG_FILE}" >&2 || true
  exit 1
}

stop_daemon() {
  if [[ -n "${DAEMON_PID}" ]] && kill -0 "${DAEMON_PID}" >/dev/null 2>&1; then
    kill "${DAEMON_PID}" >/dev/null 2>&1 || true
    wait "${DAEMON_PID}" >/dev/null 2>&1 || true
  fi
  DAEMON_PID=""
}

wait_for_completed_job() {
  local job_id="$1"
  local job_file
  for _ in $(seq 1 30); do
    job_file="$(request GET "/v1/processing-jobs/${job_id}")"
    if [[ "$(json_value "processing_job.status" "${job_file}")" == "completed" ]]; then
      printf '%s\n' "${job_file}"
      return
    fi
    request POST "/v1/processing-jobs/process-next" >/dev/null || true
    sleep 0.25
  done
  echo "Processing job ${job_id} did not complete" >&2
  exit 1
}

echo "Starting local daemon smoke on ${BASE_URL}"
echo "Data dir: ${DATA_DIR}"

start_daemon

health_file="$(request GET /health)"
assert_json_value "${health_file}" "service" "omi-local-backend"
assert_json_value "${health_file}" "mode" "local"

profile_file="$(request GET /profile/status)"
assert_json_value "${profile_file}" "mode" "local"
assert_json_value "${profile_file}" "authenticated" "False"

conversation_file="$(request POST /v1/conversations '{
  "id": "conv-e2e-smoke",
  "session_id": "session-e2e-smoke",
  "title": "Smoke seed",
  "overview": "Created by local smoke"
}')"
assert_json_value "${conversation_file}" "conversation.id" "conv-e2e-smoke"

segment_file="$(request POST /v1/conversations/conv-e2e-smoke/transcript-segments '{
  "id": "seg-e2e-smoke-0",
  "text": "Plan the backend free desktop MVP and verify deterministic local processing.",
  "start_ms": 0,
  "end_ms": 2400,
  "segment_index": 0,
  "source": "smoke"
}')"
assert_json_value "${segment_file}" "transcript_segment.id" "seg-e2e-smoke-0"

updated_file="$(request PATCH /v1/conversations/conv-e2e-smoke '{
  "title": "Smoke updated",
  "overview": "Updated before processing"
}')"
assert_json_value "${updated_file}" "conversation.title" "Smoke updated"

list_file="$(request GET /v1/conversations)"
assert_json_value "${list_file}" "conversations.0.id" "conv-e2e-smoke"

search_file="$(request GET '/v1/search/conversations?q=deterministic')"
assert_json_value "${search_file}" "results.0.conversation_id" "conv-e2e-smoke"

job_file="$(request POST /v1/conversations/conv-e2e-smoke/finalize-transcript)"
job_id="$(json_value "processing_job.id" "${job_file}")"
completed_job_file="$(wait_for_completed_job "${job_id}")"
assert_json_value "${completed_job_file}" "processing_job.status" "completed"
fallback_provider="$(json_embedded_value "processing_job.result_json" "${completed_job_file}" provider)"
if [[ "${fallback_provider}" != "fallback" ]]; then
  echo "Expected fallback processing provider, got ${fallback_provider}" >&2
  echo "Response file: ${completed_job_file}" >&2
  exit 1
fi

status_file="$(request GET /v1/processing-jobs/status)"
assert_json_value "${status_file}" "failed" "0"

processed_file="$(request GET /v1/conversations/conv-e2e-smoke)"
assert_json_value "${processed_file}" "conversation.status" "processed"
assert_json_value "${processed_file}" "conversation.title" "Plan the backend free desktop MVP and verify"

settings_file="$(request PUT /v1/settings '{
  "local_first": true,
  "ai_provider": {
    "kind": "openai_compatible",
    "base_url": "http://127.0.0.1:43210/v1",
    "model": "local-stub",
    "api_key": "local-test-key"
  }
}')"
assert_json_value "${settings_file}" "settings.0.key" "ai_provider"
assert_json_value "${settings_file}" "settings.1.key" "local_first"

stop_daemon
start_daemon

persisted_file="$(request GET /v1/conversations/conv-e2e-smoke)"
assert_json_value "${persisted_file}" "conversation.status" "processed"
assert_json_value "${persisted_file}" "transcript_segments.0.text" "Plan the backend free desktop MVP and verify deterministic local processing."

persisted_search_file="$(request GET '/v1/search/conversations?q=backend')"
assert_json_value "${persisted_search_file}" "results.0.conversation_id" "conv-e2e-smoke"

request DELETE /v1/conversations/conv-e2e-smoke >/dev/null

deleted_list_file="$(request GET /v1/conversations)"
deleted_count="$(python3 - "${deleted_list_file}" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    data = json.load(handle)
print(len(data["conversations"]))
PY
)"
if [[ "${deleted_count}" != "0" ]]; then
  echo "Expected deleted conversation to be hidden from list, got ${deleted_count} conversations" >&2
  echo "Response file: ${deleted_list_file}" >&2
  exit 1
fi

cat <<EOF
PASS local backend E2E smoke
- daemon: ${BASE_URL}
- data_dir: ${DATA_DIR}
- verified: health, profile, settings, conversation CRUD, transcript append/finalize, search, processing status, restart persistence
- desktop_env: OMI_DESKTOP_BACKEND_MODE=local OMI_LOCAL_DAEMON_URL=${BASE_URL}
EOF
