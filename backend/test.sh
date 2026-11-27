#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
usage: bash test.sh [--list] [TEST_FILE[::NODE] ...]
       bash test.sh [--list] --changed [--base REF]
       bash test.sh [--list] --all

  TEST_FILE ...  run exactly these files. Accepts tests/unit/x.py, backend/tests/unit/x.py,
                 a path relative to the current directory, or a bare file name that is
                 unique under tests/. A path that does not resolve is an error.
  --changed      run what CI's PR selector picks for this branch: changes since the
                 merge-base with REF (default origin/main), plus staged, unstaged and
                 untracked files.
  --base REF     compare against REF instead of origin/main (implies --changed).
  --all          the full unit suite. That is CI's job; locally it is an explicit opt-in.
  --list         print the selected files and exit without running them.

With no selection, a local run uses --changed and CI (CI or GITHUB_ACTIONS is "true")
uses --all. BACKEND_UNIT_TEST_FILE_LIST=<file> supplies a backend-relative list instead;
combining it with TEST_FILE, --changed or --all is an error.
BACKEND_PYTEST_WORKERS=<n> sets how many files run at once. Unset or "auto" means every
core in CI and half the cores (at least 2, at most 8) elsewhere.
USAGE
}

usage_error() {
  echo "test.sh: $*" >&2
  echo "Run 'bash test.sh --help' for usage." >&2
  exit 2
}

selection_mode=""
diff_base_ref=""
list_only=0
requested_paths=()
requested_count=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h | --help)
      usage
      exit 0
      ;;
    --all | --changed)
      if [[ -n "$selection_mode" && "$selection_mode" != "${1#--}" ]]; then
        usage_error "--all and --changed are mutually exclusive"
      fi
      selection_mode="${1#--}"
      ;;
    --base)
      [[ $# -ge 2 && -n "$2" && "$2" != -* ]] || usage_error "--base requires a git ref"
      diff_base_ref="$2"
      shift
      ;;
    --base=*)
      diff_base_ref="${1#--base=}"
      [[ -n "$diff_base_ref" ]] || usage_error "--base requires a git ref"
      ;;
    --list)
      list_only=1
      ;;
    --)
      shift
      while [[ $# -gt 0 ]]; do
        requested_paths+=("$1")
        requested_count=$((requested_count + 1))
        shift
      done
      break
      ;;
    -*)
      usage_error "unknown option: $1"
      ;;
    *)
      requested_paths+=("$1")
      requested_count=$((requested_count + 1))
      ;;
  esac
  shift
done

if [[ -n "$diff_base_ref" ]]; then
  [[ "$selection_mode" != "all" ]] || usage_error "--base applies to --changed, not --all"
  selection_mode="changed"
fi
if [[ "$requested_count" -gt 0 && -n "$selection_mode" ]]; then
  usage_error "test files and --$selection_mode are mutually exclusive; pass one selection"
fi
if [[ -n "${BACKEND_UNIT_TEST_FILE_LIST:-}" ]]; then
  if [[ "$requested_count" -gt 0 || -n "$selection_mode" ]]; then
    usage_error "BACKEND_UNIT_TEST_FILE_LIST is already a selection; unset it or drop the test files/--all/--changed"
  fi
  selection_mode="list"
elif [[ "$requested_count" -gt 0 ]]; then
  selection_mode="paths"
fi

running_in_ci=0
if [[ "${CI:-}" == "true" || "${GITHUB_ACTIONS:-}" == "true" ]]; then
  running_in_ci=1
fi
implicit_selection=0
if [[ -z "$selection_mode" ]]; then
  implicit_selection=1
  if [[ "$running_in_ci" == "1" ]]; then
    selection_mode="all"
  else
    selection_mode="changed"
  fi
fi

CALLER_DIR="$PWD"
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"
ROOT_DIR_PHYSICAL="$(pwd -P)"

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
# The warn value is the per-test CPU target; the fail value is the blocking budget and
# must keep headroom above it. CPU time is less load-sensitive than wall-clock but not
# immune: contention stall cycles are charged to the process, so identical work measured
# ~2x higher with the machine saturated (0.03s -> 0.06s on an 8-core host). At the former
# 0.12s budget -- only 1.2x the target -- a busy runner failed a shifting set of files
# that all passed in isolation. CI carries a 1.0-second ceiling for the same reason, and
# the local lane now uses the same one: a laptop shared with builds and other agents is
# at least as loaded as a runner, and the former 0.30s local budget failed pushes on
# tests that passed alone and passed CI (2026-10-20, twice in one sync push). A
# stricter local gate than CI only blocks pushes CI would accept; the warn target still
# reports anything over 0.1s.
export BACKEND_FAST_UNIT_WARN_SECONDS="${BACKEND_FAST_UNIT_WARN_SECONDS:-0.1}"
export BACKEND_FAST_UNIT_FAIL_SECONDS="${BACKEND_FAST_UNIT_FAIL_SECONDS:-1.0}"

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

# LangSmith's pytest integration is for live evaluation/upload, which this
# hermetic suite does not use. Local startup measurements saved ~0.17s per
# process before collection; file isolation pays this cost hundreds of times.
# Keep the other plugins active.
pytest_args=(-p no:langsmith_plugin -v)
if [[ "${BACKEND_UNIT_SHARD_SUMMARY:-0}" == "1" ]]; then
  pytest_args+=(-p testing.shard_failure_summary)
  # Tests that launch their own runner must not publish into this summary.
  unset BACKEND_UNIT_SHARD_SUMMARY
fi

marker_expr="${BACKEND_PYTEST_MARK_EXPR:-not integration and not slow}"
if [[ -n "$marker_expr" ]]; then
  pytest_args+=(-m "$marker_expr")
fi

use_file_isolation="${BACKEND_PYTEST_FILE_ISOLATION:-1}"
use_session_xdist=0
if [[ "$use_file_isolation" != "1" && "$use_file_isolation" != "true" && "${BACKEND_PYTEST_XDIST:-auto}" != "0" && "${BACKEND_PYTEST_XDIST:-auto}" != "false" ]]; then
  if "$PYTHON_BIN" -c "import xdist" >/dev/null 2>&1; then
    # The worker count is resolved after selection, by the same bounded rule.
    use_session_xdist=1
  else
    echo "pytest-xdist is not installed; running backend unit tests serially."
  fi
fi

selection_dir="$(mktemp -d)"
trap 'rm -rf "$selection_dir"' EXIT

# Print the physical path of an existing file with every symlink resolved, the
# file's own included (Bash 3.2 and macOS have no portable `readlink -f`). A
# symlinked test file is collected from its target, so containment must be
# judged on the target, not on the directory that holds the link.
resolve_physical_path() {
  local path="$1" target hops=0
  while [[ -L "$path" ]]; do
    hops=$((hops + 1))
    [[ "$hops" -le 40 ]] || return 1
    target="$(readlink "$path")" || return 1
    case "$target" in
      /*) path="$target" ;;
      *) path="$(dirname "$path")/$target" ;;
    esac
  done
  [[ -e "$path" ]] || return 1
  printf '%s/%s\n' "$(cd "$(dirname "$path")" 2>/dev/null && pwd -P)" "$(basename "$path")"
}

path_is_inside_backend() {
  case "$1" in
    "$ROOT_DIR_PHYSICAL"/*) return 0 ;;
  esac
  return 1
}

# Print the backend-relative form of an existing file; fail when the file, or
# whatever it resolves to through symlinks, is outside backend/.
backend_relative_path() {
  local directory relative resolved
  directory="$(cd "$(dirname "$1")" 2>/dev/null && pwd -P)" || return 1
  path_is_inside_backend "$directory/" || return 1
  resolved="$(resolve_physical_path "$1")" || return 1
  path_is_inside_backend "$resolved" || return 1
  relative="${directory#"$ROOT_DIR_PHYSICAL"}"
  relative="${relative#/}"
  printf '%s%s\n' "${relative:+$relative/}" "$(basename "$1")"
}

# Selector output is backend-relative. Fail when one of those paths reaches
# outside backend/ through a symlinked file or directory. Only the builtin -L
# test runs per path component; a path is resolved only when a link is found.
selected_path_escapes_backend() {
  local path="${1%%::*}" partial="" component
  local components=()
  IFS='/' read -r -a components <<< "$path"
  for component in "${components[@]}"; do
    partial="${partial:+$partial/}$component"
    if [[ -L "$partial" ]]; then
      backend_relative_path "$path" >/dev/null || return 0
      return 1
    fi
  done
  return 1
}

# Resolve one requested test path to a backend-relative path. Never guesses: a
# path that does not exist, a directory, or an ambiguous bare name is an error.
report_outside_backend() {
  local resolved
  if resolved="$(resolve_physical_path "$2")" && [[ "$resolved" != "$(cd "$(dirname "$2")" 2>/dev/null && pwd -P)/$(basename "$2")" ]]; then
    echo "test.sh: $1 resolves through a symlink to $resolved, outside backend/; this runner only runs backend tests" >&2
  else
    echo "test.sh: $1 is outside backend/; this runner only runs backend tests" >&2
  fi
}

resolve_test_path() {
  local spec="$1" file_part node_suffix="" candidate relative name matches match_count match
  local candidates=()
  file_part="${spec%%::*}"
  [[ "$file_part" == "$spec" ]] || node_suffix="::${spec#*::}"
  case "$file_part" in
    /*) candidates=("$file_part") ;;
    *)
      candidates=("$CALLER_DIR/$file_part" "$ROOT_DIR/$file_part")
      [[ "$file_part" != backend/* ]] || candidates+=("$ROOT_DIR/${file_part#backend/}")
      ;;
  esac
  for candidate in "${candidates[@]}"; do
    if [[ -d "$candidate" ]]; then
      echo "test.sh: $spec is a directory; pass test files, --changed, or --all" >&2
      return 1
    fi
    if [[ -f "$candidate" ]]; then
      if ! relative="$(backend_relative_path "$candidate")"; then
        report_outside_backend "$spec" "$candidate"
        return 1
      fi
      printf '%s%s\n' "$relative" "$node_suffix"
      return 0
    fi
  done
  if [[ "$file_part" != */* ]]; then
    name="$file_part"
    [[ "$name" == *.py ]] || name="$name.py"
    matches="$(find tests -type f -name "$name" -not -path '*/__pycache__/*' 2>/dev/null | LC_ALL=C sort)"
    match_count=0
    [[ -z "$matches" ]] || match_count="$(printf '%s\n' "$matches" | wc -l | tr -d ' ')"
    if [[ "$match_count" -eq 1 ]]; then
      if ! match="$(backend_relative_path "$matches")"; then
        report_outside_backend "$spec" "$matches"
        return 1
      fi
      printf '%s%s\n' "$match" "$node_suffix"
      return 0
    fi
    if [[ "$match_count" -gt 1 ]]; then
      echo "test.sh: $spec is ambiguous; $match_count files under backend/tests/ have that name:" >&2
      while IFS= read -r match; do
        echo "  $match" >&2
      done <<< "$matches"
      return 1
    fi
    echo "test.sh: $spec: no file of that name under backend/tests/" >&2
    return 1
  fi
  echo "test.sh: $spec: no such file (looked relative to $CALLER_DIR and backend/)" >&2
  return 1
}

# --changed reuses CI's PR selector over the same diff CI computes (merge-base
# with the base ref versus HEAD), widened by the uncommitted state of this tree,
# so a local run can select more than CI for the same change, never less.
select_changed_tests() {
  local base_ref="${diff_base_ref:-origin/main}" merge_base changed_list changed_count
  if ! git rev-parse --verify --quiet "${base_ref}^{commit}" >/dev/null; then
    usage_error "--changed cannot resolve $base_ref. Run 'git fetch origin main', pass --base REF, pass test files, or use --all."
  fi
  merge_base="$(git merge-base "$base_ref" HEAD)" ||
    usage_error "--changed found no merge-base between $base_ref and HEAD; pass --base REF or use --all."
  changed_list="$selection_dir/changed-files.txt"
  {
    "$ROOT_DIR/../scripts/changed-files" "$merge_base" HEAD
    "$ROOT_DIR/../scripts/changed-files" "$merge_base"
    git ls-files --others --exclude-standard --full-name -- ':/'
  } | LC_ALL=C sort -u > "$changed_list"
  changed_count="$(wc -l < "$changed_list" | tr -d ' ')"
  test_list_file="$selection_dir/changed-tests.txt"
  selection_reason_file="$selection_dir/changed-reason.txt"
  # The selector answers an empty path list with the full suite, which suits a
  # CI event whose diff could not be computed. Here the diff was computed and is
  # empty: there is nothing to test, and a clean checkout must not run everything.
  if [[ "$changed_count" -eq 0 ]]; then
    : > "$test_list_file"
    echo "test.sh --changed: no changes since ${merge_base:0:12} ($base_ref), so nothing is selected. Pass test files, or --all for the full suite." >&2
    return
  fi
  "$PYTHON_BIN" scripts/select_backend_unit_tests.py \
    --changed-files "$changed_list" \
    --output "$test_list_file" \
    --reason-output "$selection_reason_file"
  echo "test.sh --changed: $changed_count changed path(s) since ${merge_base:0:12} ($base_ref): $(cat "$selection_reason_file")" >&2
}

selection_reason_file=""
case "$selection_mode" in
  paths)
    test_list_file="$selection_dir/requested-tests.txt"
    : > "$test_list_file"
    resolve_failed=0
    for spec in "${requested_paths[@]}"; do
      if resolved="$(resolve_test_path "$spec")"; then
        grep -qxF -- "$resolved" "$test_list_file" || printf '%s\n' "$resolved" >> "$test_list_file"
      else
        resolve_failed=1
      fi
    done
    if [[ "$resolve_failed" -ne 0 ]]; then
      echo "test.sh: no tests were run; fix the path(s) above." >&2
      exit 2
    fi
    ;;
  list)
    test_list_file="$BACKEND_UNIT_TEST_FILE_LIST"
    ;;
  changed)
    if [[ "$implicit_selection" == "1" ]]; then
      echo "test.sh: no selection given, so running --changed (CI's PR selection for this branch). Pass test files to narrow it, or --all for the full suite." >&2
    fi
    select_changed_tests
    ;;
  all)
    test_list_file="$selection_dir/all-tests.txt"
    "$PYTHON_BIN" scripts/select_backend_unit_tests.py --all --output "$test_list_file"
    ;;
esac

if [[ ! -f "$test_list_file" ]]; then
  echo "BACKEND_UNIT_TEST_FILE_LIST does not exist: $test_list_file" >&2
  exit 1
fi

selected_tests=()
selected_count=0
while IFS= read -r test_path; do
  # The automatic full selection leaves E2E to its own CI job. Every other
  # selection (an explicit list, named files, or the PR selector's output, which
  # CI passes to this runner as an explicit list) must honor hermetic E2E paths.
  if [[ -n "$test_path" && ( "$test_path" != testing/e2e/* || "$selection_mode" != "all" ) ]]; then
    selected_tests+=("$test_path")
    selected_count=$((selected_count + 1))
  fi
done < "$test_list_file"

# Named files were contained as they resolved. The selector's output gets the
# same rule: a symlinked file or directory under backend/ must not make pytest
# collect code from elsewhere. An explicit BACKEND_UNIT_TEST_FILE_LIST is the
# caller's own statement and may name files anywhere, as it always could.
if [[ ( "$selection_mode" == "changed" || "$selection_mode" == "all" ) && "$selected_count" -gt 0 ]]; then
  escaped_count=0
  for test_path in "${selected_tests[@]}"; do
    if selected_path_escapes_backend "$test_path"; then
      echo "test.sh: selected $test_path resolves through a symlink to outside backend/" >&2
      escaped_count=$((escaped_count + 1))
    fi
  done
  if [[ "$escaped_count" -gt 0 ]]; then
    echo "test.sh: no tests were run; remove the symlink(s) above or name the files you mean to run." >&2
    exit 2
  fi
fi

if [[ "$list_only" == "1" ]]; then
  [[ "$selected_count" -eq 0 ]] || printf '%s\n' "${selected_tests[@]}"
  exit 0
fi

if [[ "$selected_count" -eq 0 ]]; then
  echo "No backend unit tests selected."
  exit 0
fi

# A full local run is what turned one agent's two-file check into the whole suite
# on a shared host, so say so before starting rather than after.
broad_local_selection=100
if [[ "$running_in_ci" != "1" && "$selection_mode" == "all" ]]; then
  echo "==> test.sh: running the FULL backend unit suite ($selected_count files). CI runs it for every PR; locally prefer 'bash test.sh --changed' or 'bash test.sh tests/unit/test_<name>.py'." >&2
elif [[ "$running_in_ci" != "1" && "$selection_mode" == "changed" && "$selected_count" -gt "$broad_local_selection" ]]; then
  echo "==> test.sh: the selector picked $selected_count files for this diff, the same set CI runs for it. While iterating, pass the test files you are working on instead." >&2
fi

echo "Running $selected_count backend unit test file(s)."

# Locally, "auto" is half the cores, at least 2 and at most 8: a developer machine
# is shared with builds and other agents' test runs, and each invocation used to
# start one worker per core (ten lanes on an 18-core host: 180 slots, load ~380).
# Total CPU for a selection does not change with the worker count; the count only
# decides how much of the host one run claims. backend/tests/README.md has the
# measurement. CI runners are not shared and keep every core.
local_auto_worker_cap=8
resolve_worker_count() {
  local requested="${BACKEND_PYTEST_WORKERS:-auto}" cores
  if [[ "$requested" != "auto" ]]; then
    [[ "$requested" =~ ^[1-9][0-9]*$ ]] ||
      usage_error "BACKEND_PYTEST_WORKERS must be a positive integer or auto, not '$requested'"
    printf '%s\n' "$requested"
    return
  fi
  if command -v getconf >/dev/null 2>&1; then
    cores="$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)"
  elif command -v sysctl >/dev/null 2>&1; then
    cores="$(sysctl -n hw.ncpu 2>/dev/null || echo 4)"
  else
    cores="4"
  fi
  [[ "$cores" =~ ^[1-9][0-9]*$ ]] || cores=4
  if [[ "$running_in_ci" == "1" ]]; then
    printf '%s\n' "$cores"
    return
  fi
  local workers=$((cores / 2))
  [[ "$workers" -ge 2 ]] || workers=2
  [[ "$workers" -le "$cores" ]] || workers="$cores"
  [[ "$workers" -le "$local_auto_worker_cap" ]] || workers="$local_auto_worker_cap"
  printf '%s\n' "$workers"
}

if [[ "$use_file_isolation" == "1" || "$use_file_isolation" == "true" ]]; then
  worker_count="$(resolve_worker_count)"
  if [[ "$running_in_ci" == "1" ]]; then
    echo "test.sh: $worker_count file(s) at a time (BACKEND_PYTEST_WORKERS=${BACKEND_PYTEST_WORKERS:-auto}; CI auto uses every core)." >&2
  else
    echo "test.sh: $worker_count file(s) at a time (BACKEND_PYTEST_WORKERS=${BACKEND_PYTEST_WORKERS:-auto}; local auto is half the cores, 2 to $local_auto_worker_cap)." >&2
  fi

  # OPT-IN partition: run the files that are not known module-stub offenders in one
  # parallel pytest session instead of one process each.
  #
  # OFF BY DEFAULT, and the reason is measured, not cautious. The theory was that
  # per-file isolation is only owed to the files that mutate ``sys.modules`` at module
  # scope, that tests/.module_stub_legacy_allowlist enumerates them, and that the other
  # ~875 files could therefore share a session. The allowlist does not enumerate them:
  # scripts/check_module_stub_pollution.py only sees *direct* module-scope writes, and
  # the common pattern in this tree is a module-scope call to a same-file helper that
  # writes sys.modules (or an import of the deprecated tests/unit/memory_import_isolation).
  # Measured on this selection (930 files, 55 allowlisted):
  #   - collecting the 875 non-allowlisted files in one process SIGSEGVs. The upb
  #     protobuf backend aborts when an evicted google.cloud.firestore_v1 type module is
  #     re-executed and re-registers a file descriptor.
  #   - splitting them into 35 chunks of 25 and collecting each chunk separately still
  #     fails in 11 of 35 chunks (42 collection errors plus one segfault), so the
  #     contamination is dense rather than a handful of nameable offenders.
  #   - collecting 815 of them in one process is OOM-killed, and each xdist worker
  #     collects the whole selection, so memory scales with worker count too.
  # Making this the default would trade a slow suite for a broken one. It ships behind
  # the knob so the machinery and its contracts exist for whoever finishes the
  # import-purity work in backend/docs/test_isolation.md; flip the default then.
  parallel_session="${BACKEND_PYTEST_PARALLEL_SESSION:-0}"
  allowlist_path="${BACKEND_MODULE_STUB_ALLOWLIST:-tests/.module_stub_legacy_allowlist}"

  isolated_tests=()
  batched_tests=()
  if [[ "$parallel_session" != "1" && "$parallel_session" != "true" ]]; then
    isolated_tests=("${selected_tests[@]}")
  else
    isolate_everything=0
    # Allowlist entries are repo-relative (backend/tests/...); the selector emits
    # backend-relative paths (tests/...). Normalize both sides to backend-relative
    # before comparing, or the partition silently sends every offender to the batch.
    allowlist_entries=$'\n'
    if [[ -f "$allowlist_path" ]]; then
      while IFS= read -r allowlist_line || [[ -n "$allowlist_line" ]]; do
        entry="${allowlist_line%%#*}"
        entry="${entry#"${entry%%[![:space:]]*}"}"
        entry="${entry%"${entry##*[![:space:]]}"}"
        [[ -n "$entry" ]] || continue
        entry="${entry#./}"
        entry="${entry#backend/}"
        allowlist_entries+="$entry"$'\n'
      done < "$allowlist_path"
    else
      echo "Module-stub legacy allowlist not found at $allowlist_path; isolating every file." >&2
      isolate_everything=1
    fi

    for test_path in "${selected_tests[@]}"; do
      normalized="${test_path#./}"
      normalized="${normalized#backend/}"
      if [[ "$isolate_everything" == "1" || "$allowlist_entries" == *$'\n'"$normalized"$'\n'* ]]; then
        isolated_tests+=("$test_path")
      else
        batched_tests+=("$test_path")
      fi
    done
  fi

  # Bash 3.2 errors on ``"${empty[@]}"`` under ``set -u``; read the lengths with the
  # check relaxed and gate every expansion on them.
  set +u
  isolated_count="${#isolated_tests[@]}"
  batched_count="${#batched_tests[@]}"
  set -u
  if [[ "$batched_count" -gt 0 ]]; then
    echo "Partition: $batched_count file(s) in one parallel pytest session, $isolated_count file(s) in per-file isolation."
  fi

  active_pids=()
  active_status_files=()
  active_test_paths=()
  trap 'set +u; [ "${#active_test_paths[@]}" -gt 0 ] && echo "backend unit: cancelled with files in flight: ${active_test_paths[*]}" >&2 || true' TERM
  failed_test_paths=()
  failed=0
  status_dir="$(mktemp -d)"
  test_index=0

  # Count in the parent shell: command substitution here forked twice per
  # 20ms poll, competing with pytest workers throughout every isolated shard.
  active_count=0

  wait_for_worker_completion() {
    # Bash 5.1+ can wait for any tracked child, including one that completed
    # between the status-file scan and this call. Older shells keep polling.
    if (( BASH_VERSINFO[0] > 5 || (BASH_VERSINFO[0] == 5 && BASH_VERSINFO[1] >= 1) )); then
      wait -n "${active_pids[@]}" || true
    else
      sleep 0.02
    fi
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
    active_count="${#still_active[@]}"
    set -u
  }

  # GNU timeout is available on CI; keep macOS/Bash 3 hosts without it on
  # the existing execution path. Include Python so the array is never empty
  # (empty array expansion under set -u fails on Bash 3).
  file_budget="${BACKEND_UNIT_FILE_BUDGET_SECONDS:-300}"
  runner=("$PYTHON_BIN")
  if command -v timeout >/dev/null 2>&1; then
    runner=(timeout --signal=TERM --kill-after=30s "${file_budget}s" "$PYTHON_BIN")
  fi

  if [[ "$isolated_count" -gt 0 ]]; then
    for test_path in "${isolated_tests[@]}"; do
      status_file="$status_dir/$test_index.status"
      test_index=$((test_index + 1))
      (
        echo "::group::$test_path"
        # Per-file workers do not use loop-on-failure. Load the HTTP-server
        # fixture plugin only where its fixture is referenced; importing it
        # (and Werkzeug) in every isolated process adds suite-wide startup cost.
        file_pytest_args=("${pytest_args[@]}" -p no:xdist.looponfail)
        if [[ -f "${test_path%%::*}" ]]; then
          test_source="$(<"${test_path%%::*}")"
          httpserver_fixture_pattern='(^|[^[:alnum:]_])httpserver'
          if [[ ! "$test_source" =~ $httpserver_fixture_pattern ]]; then
            file_pytest_args+=(-p no:pytest_httpserver)
          fi
          unset test_source
        fi
        # Bash's clock avoids starting extra Python processes for every file.
        # Include collection/import and process shutdown, which pytest's
        # call-phase duration summary omits. Precision is one second.
        file_started=$SECONDS
        set +e
        "${runner[@]}" -m pytest "${file_pytest_args[@]}" "$test_path"
        status=$?
        set -e
        echo "BACKEND-UNIT-FILE-WALL $((SECONDS - file_started))s $test_path"
        if [[ "$status" -eq 124 ]]; then
          echo "::error title=Backend unit file timed out::$test_path exceeded ${file_budget}s (TERM, then KILL) and was terminated"
        fi
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
      active_count=$((active_count + 1))

      while [[ "$active_count" -ge "$worker_count" ]]; do
        reap_finished_children
        if [[ "$active_count" -lt "$worker_count" ]]; then
          break
        fi
        wait_for_worker_completion
      done
    done

    while [[ "$active_count" -gt 0 ]]; do
      reap_finished_children
      if [[ "$active_count" -gt 0 ]]; then
        wait_for_worker_completion
      fi
    done

  fi

  for status_file in "$status_dir"/*.status; do
    [[ -e "$status_file" ]] || continue
    IFS=$'\t' read -r status test_path < "$status_file"
    if [[ "$status" -ne 0 ]]; then
      echo "Backend unit test file failed: $test_path (status $status)"
      failed_test_paths+=("$test_path")
      failed=1
    fi
  done

  batch_unattributed=0
  if [[ "$batched_count" -gt 0 ]]; then
    batch_args=("${pytest_args[@]}")
    if "$PYTHON_BIN" -c "import xdist" >/dev/null 2>&1; then
      batch_args+=(-n "$worker_count" --dist=loadfile)
    else
      echo "pytest-xdist is not installed; running the parallel partition serially."
    fi

    batch_log="$status_dir/parallel-batch.log"
    echo "::group::Backend unit parallel session ($batched_count file(s))"
    set +e
    "$PYTHON_BIN" -m pytest "${batch_args[@]}" "${batched_tests[@]}" 2>&1 | tee "$batch_log"
    batch_status="${PIPESTATUS[0]}"
    set -e
    # Exit 5 means "collected nothing", which for a single file legitimately means "every
    # test in it was deselected by the marker". For the parallel session it also fires
    # when the session died: an xdist run whose workers all crash reports "no tests ran"
    # and exits 5. Mapping that to success turned a suite-wide segfault into a green run
    # during this change's own validation. Only honour it when nothing crashed.
    if [[ "$batch_status" -eq 5 && -n "$marker_expr" ]]; then
      if grep -qE 'crashed workers|Fatal Python error|INTERNALERROR|error(s)? during collection' "$batch_log"; then
        echo "Parallel session collected no tests because it crashed; not treating as skipped."
      else
        echo "No tests matched marker expression for the parallel partition; treating as skipped."
        batch_status=0
      fi
    fi
    echo "::endgroup::"

    if [[ "$batch_status" -ne 0 ]]; then
      failed=1
      # The parallel session is one process, so there is no per-file exit status to
      # read. pytest's short summary (FAILED/ERROR lines, on by default) names the node
      # id of every failure and every collection error. Session-level gates that fail
      # without failing a test -- the fast-unit duration guard -- announce their files
      # with the BACKEND-UNIT-FAILED-FILE marker from tests/conftest.py instead. Both
      # feed the same per-file report and rerun list.
      batch_failed_files="$(
        grep -E '^(FAILED|ERROR|BACKEND-UNIT-FAILED-FILE) ' "$batch_log" 2>/dev/null |
          awk '{print $2}' | sed 's/::.*$//' | sort -u || true
      )"
      if [[ -n "$batch_failed_files" ]]; then
        while IFS= read -r batch_failed_path; do
          [[ -n "$batch_failed_path" ]] || continue
          echo "::error title=Backend unit file failed::$batch_failed_path failed in the parallel session"
          echo "Backend unit test file failed: $batch_failed_path (status $batch_status)"
          failed_test_paths+=("$batch_failed_path")
        done <<< "$batch_failed_files"
      else
        batch_unattributed=1
        echo "::error title=Backend unit parallel session failed::exited with status $batch_status"
        echo "Backend unit parallel session failed (status $batch_status) without naming a file."
      fi
    fi
  fi

  if [[ "$failed" -ne 0 ]]; then
    rerun_list="/tmp/omi-backend-unit-failures.txt"
    echo
    echo "Backend unit suite failed."
    echo "Reproduce only the failed file(s) with the same test.sh runner and timing guard:"
    printf '  : > %q\n' "$rerun_list"
    set +u
    for test_path in "${failed_test_paths[@]}"; do
      printf '  echo %q >> %q\n' "$test_path" "$rerun_list"
    done
    set -u
    printf '  BACKEND_UNIT_TEST_FILE_LIST=%q bash test.sh\n' "$rerun_list"
    echo "Do not use bare pytest for fast-unit timing failures; it omits test.sh's guard settings."
    if [[ "$batch_unattributed" -ne 0 ]]; then
      echo "The parallel session failed without naming a file (crash, worker death, or a"
      echo "session-level guard). Re-run the selection one file per process by clearing"
      echo "  BACKEND_PYTEST_PARALLEL_SESSION"
    fi
  fi

  rm -rf "$status_dir"
  exit "$failed"
fi

if [[ "$use_session_xdist" == "1" ]]; then
  workers="${BACKEND_PYTEST_WORKERS:-auto}"
  if [[ "$workers" == "auto" && "$running_in_ci" != "1" ]]; then
    workers="$(resolve_worker_count)"
  fi
  pytest_args+=(-n "$workers" --dist=loadfile)
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
