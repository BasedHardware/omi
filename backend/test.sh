#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

# Repository sources are UTF-8. Native Windows Python otherwise inherits the
# system code page, which makes source-reading tests locale-dependent.
export PYTHONUTF8="${PYTHONUTF8:-1}"

# Git exports repository-local variables while invoking hooks. They must not
# leak into pytest: tests that create temporary repositories would otherwise
# keep operating on the outer worktree. The runner is already anchored at the
# backend directory, so normal Git discovery remains available after scrubbing.
while IFS= read -r git_env_name; do
  [[ -n "$git_env_name" ]] && unset "$git_env_name"
done < <(git rev-parse --local-env-vars 2>/dev/null || true)

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
# Direct focused runs keep the strict default. The shared pre-push/CI runner supplies
# the same 1.0-second ceiling so cross-machine CPU differences do not create a second policy.
export BACKEND_FAST_UNIT_WARN_SECONDS="${BACKEND_FAST_UNIT_WARN_SECONDS:-0.1}"
export BACKEND_FAST_UNIT_FAIL_SECONDS="${BACKEND_FAST_UNIT_FAIL_SECONDS:-0.12}"

# The file-isolated runner already parallelizes pytest processes. Letting each process
# start a native BLAS/OpenMP pool oversubscribes the machine and makes process CPU time
# depend on which test first initializes NumPy. Keep one native worker per pytest process;
# callers can still override a setting when intentionally exercising parallel kernels.
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export VECLIB_MAXIMUM_THREADS="${VECLIB_MAXIMUM_THREADS:-1}"
export NUMEXPR_NUM_THREADS="${NUMEXPR_NUM_THREADS:-1}"
export BLIS_NUM_THREADS="${BLIS_NUM_THREADS:-1}"

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
  if [[ -n "$test_path" && "$test_path" != testing/e2e/* ]]; then
    selected_tests+=("$test_path")
  fi
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
  active_status_files=()
  active_test_paths=()
  failed_test_paths=()
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
    local index
    local pid
    local status_file
    local test_path
    local still_active=()
    local still_status_files=()
    local still_test_paths=()
    local running_pids

    # Each file-isolated child writes its status atomically before it exits.
    # Waiting for the oldest PID leaves a worker idle when a newer short test
    # finishes first; use that completion signal so the next file starts as
    # soon as *any* worker is available. This is portable to macOS's Bash 3,
    # which lacks `wait -n`.
    set +u
    # Snapshot running job PIDs once per reap pass.  ``jobs -pr`` lists only
    # actively-running jobs — a zombie child (exited but not yet waited on) is
    # NOT listed, so we can distinguish "still computing" from "died before
    # status handoff" without a blocking ``wait``.
    running_pids="$(jobs -pr 2>/dev/null || true)"
    for index in "${!active_pids[@]}"; do
      pid="${active_pids[$index]}"
      status_file="${active_status_files[$index]}"
      test_path="${active_test_paths[$index]}"
      if [[ -f "$status_file" ]]; then
        wait "$pid" || true
      elif [[ $'\n'"$running_pids"$'\n' == *$'\n'"$pid"$'\n'* ]]; then
        still_active+=("$pid")
        still_status_files+=("$status_file")
        still_test_paths+=("$test_path")
      else
        # Worker exited before writing its status file (OOM kill, signal,
        # crash).  Reap it so the scheduler does not spin forever waiting
        # for a file that will never arrive.
        wait "$pid" 2>/dev/null || true
        echo "::error title=Backend unit file failed::$test_path worker exited before writing status"
        failed_test_paths+=("$test_path")
        failed=1
      fi
    done
    active_pids=("${still_active[@]}")
    active_status_files=("${still_status_files[@]}")
    active_test_paths=("${still_test_paths[@]}")
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
      if [[ "$status" -ne 0 ]]; then
        echo "::error title=Backend unit file failed::$test_path exited with status $status"
      fi
      echo "::endgroup::"
      # Rename after writing so the scheduler never observes a partial status.
      status_temp="$status_file.pending"
      printf '%s\t%s\n' "$status" "$test_path" > "$status_temp"
      mv "$status_temp" "$status_file"
      exit 0
    ) &
    active_pids+=("$!")
    active_status_files+=("$status_file")
    active_test_paths+=("$test_path")

    while [[ "$(active_pid_count)" -ge "$worker_count" ]]; do
      reap_finished_children
      if [[ "$(active_pid_count)" -lt "$worker_count" ]]; then
        break
      fi
      sleep 0.02
    done
  done

  while [[ "$(active_pid_count)" -gt 0 ]]; do
    reap_finished_children
    if [[ "$(active_pid_count)" -gt 0 ]]; then
      sleep 0.02
    fi
  done

  for status_file in "$status_dir"/*.status; do
    [[ -e "$status_file" ]] || continue
    IFS=$'\t' read -r status test_path < "$status_file"
    if [[ "$status" -ne 0 ]]; then
      echo "Backend unit test file failed: $test_path (status $status)"
      failed_test_paths+=("$test_path")
      failed=1
    fi
  done

  if [[ "$failed" -ne 0 ]]; then
    rerun_list="/tmp/omi-backend-unit-failures.txt"
    echo
    echo "Backend unit suite failed."
    echo "Reproduce only the failed file(s) with the same test.sh runner and timing guard:"
    printf '  : > %q\n' "$rerun_list"
    for test_path in "${failed_test_paths[@]}"; do
      printf '  echo %q >> %q\n' "$test_path" "$rerun_list"
    done
    printf '  BACKEND_UNIT_TEST_FILE_LIST=%q bash test.sh\n' "$rerun_list"
    echo "Do not use bare pytest for fast-unit timing failures; it omits test.sh's guard settings."
  fi

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
