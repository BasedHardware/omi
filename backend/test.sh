#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x ".venv/bin/python" ]]; then
    PYTHON_BIN=".venv/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi

export ENCRYPTION_SECRET="omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv"
export OPENAI_API_KEY="test-openai-key-not-real"
export BACKEND_PYTEST_TIMING_SUMMARY="${BACKEND_PYTEST_TIMING_SUMMARY:-1}"
export BACKEND_FAST_UNIT_WARN_SECONDS="${BACKEND_FAST_UNIT_WARN_SECONDS:-0.1}"
export BACKEND_FAST_UNIT_FAIL_SECONDS="${BACKEND_FAST_UNIT_FAIL_SECONDS:-0.12}"

pytest_args=(-v)

marker_expr="${BACKEND_PYTEST_MARK_EXPR:-not integration and not slow}"
if [[ -n "$marker_expr" ]]; then
  pytest_args+=(-m "$marker_expr")
fi

use_file_isolation="${BACKEND_PYTEST_FILE_ISOLATION:-1}"
if [[ "$use_file_isolation" != "1" && "$use_file_isolation" != "true" && "${BACKEND_PYTEST_XDIST:-auto}" != "0" && "${BACKEND_PYTEST_XDIST:-auto}" != "false" ]]; then
  if "$PYTHON_BIN" -c "import xdist" >/dev/null 2>&1; then
    workers="${BACKEND_PYTEST_WORKERS:-auto}"
    pytest_args+=(-n "$workers" --dist=loadfile)
  else
    echo "pytest-xdist is not installed; running backend unit tests serially."
  fi
fi

test_list_file="${BACKEND_UNIT_TEST_FILE_LIST:-}"
generated_test_list=""
if [[ -z "$test_list_file" ]]; then
  generated_test_list="$(mktemp)"
  trap '[[ -z "${generated_test_list:-}" ]] || rm -f "$generated_test_list"' EXIT
  "$PYTHON_BIN" scripts/select_backend_unit_tests.py --all --output "$generated_test_list"
  test_list_file="$generated_test_list"
fi

if [[ ! -f "$test_list_file" ]]; then
  echo "BACKEND_UNIT_TEST_FILE_LIST does not exist: $test_list_file" >&2
  exit 1
fi

selected_tests=()
while IFS= read -r test_path; do
  [[ -n "$test_path" ]] && selected_tests+=("$test_path")
done < "$test_list_file"

if [[ ${#selected_tests[@]} -eq 0 ]]; then
  echo "No backend unit tests selected."
  exit 0
fi

echo "Running ${#selected_tests[@]} backend unit test file(s)."

if [[ "$use_file_isolation" == "1" || "$use_file_isolation" == "true" ]]; then
  worker_count="${BACKEND_PYTEST_WORKERS:-auto}"
  if [[ "$worker_count" == "auto" ]]; then
    if command -v getconf >/dev/null 2>&1; then
      worker_count="$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)"
    elif command -v sysctl >/dev/null 2>&1; then
      worker_count="$(sysctl -n hw.ncpu 2>/dev/null || echo 4)"
    else
      worker_count="4"
    fi
  fi

  active_pids=()
  failed=0
  status_dir="$(mktemp -d)"
  test_index=0

  active_pid_count() {
    set +u
    local count="${#active_pids[@]}"
    set -u
    echo "$count"
  }

  reap_finished_children() {
    local running_pids
    local pid
    local still_active=()
    local current_pids=()

    running_pids="$(jobs -pr || true)"
    set +u
    current_pids=("${active_pids[@]}")
    for pid in "${current_pids[@]}"; do
      if [[ $'\n'"$running_pids"$'\n' == *$'\n'"$pid"$'\n'* ]]; then
        still_active+=("$pid")
      else
        if ! wait "$pid"; then
          failed=1
        fi
      fi
    done
    set -u
    set +u
    active_pids=("${still_active[@]}")
    set -u
  }

  for test_path in "${selected_tests[@]}"; do
    status_file="$status_dir/$test_index.status"
    test_index=$((test_index + 1))
    (
      echo "::group::$test_path"
      set +e
      "$PYTHON_BIN" -m pytest "${pytest_args[@]}" "$test_path"
      status=$?
      set -e
      if [[ "$status" -eq 5 && -n "$marker_expr" ]]; then
        echo "No tests matched marker expression for $test_path; treating as skipped."
        status=0
      fi
      printf '%s\t%s\n' "$status" "$test_path" > "$status_file"
      if [[ "$status" -ne 0 ]]; then
        echo "::error title=Backend unit file failed::$test_path exited with status $status"
      fi
      echo "::endgroup::"
      exit 0
    ) &
    active_pids+=("$!")

    while [[ "$(active_pid_count)" -ge "$worker_count" ]]; do
      reap_finished_children
      if [[ "$(active_pid_count)" -lt "$worker_count" ]]; then
        break
      fi
      oldest_pid="${active_pids[0]}"
      active_pids=("${active_pids[@]:1}")
      if ! wait "$oldest_pid"; then
        failed=1
      fi
    done
  done

  reap_finished_children
  set +u
  for pid in "${active_pids[@]}"; do
    if ! wait "$pid"; then
      failed=1
    fi
  done
  set -u

  for status_file in "$status_dir"/*.status; do
    [[ -e "$status_file" ]] || continue
    IFS=$'\t' read -r status test_path < "$status_file"
    if [[ "$status" -ne 0 ]]; then
      echo "Backend unit test file failed: $test_path (status $status)"
      failed=1
    fi
  done

  rm -rf "$status_dir"
  exit "$failed"
fi

set +e
"$PYTHON_BIN" -m pytest "${pytest_args[@]}" "${selected_tests[@]}"
status=$?
set -e
if [[ "$status" -eq 5 && -n "$marker_expr" ]]; then
  echo "No tests matched marker expression for selected files; treating as skipped."
  exit 0
fi
exit "$status"
