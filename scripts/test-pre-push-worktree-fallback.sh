#!/usr/bin/env bash

# Regression for #10293: `make setup` and the pre-push hook aborted with
# "fatal: this operation must be run in a work tree" inside linked worktrees.
#
# #10401 fixed the Makefile and the installed hook dispatcher, but the scripts
# the dispatcher hands off to (scripts/pre-push, scripts/pre-push-singleflight,
# scripts/pr-preflight) and the Python entrypoints they exec
# (.github/scripts/preflight_runner.py, .github/scripts/pr_preflight.py) still
# resolved the repo root with an unguarded `git rev-parse --show-toplevel`. When
# the invoking git context resolves to a git dir rather than a work tree,
# show-toplevel exits 128 and each of those aborted the gate, forcing a
# --no-verify push that silently bypasses local checks.
#
# A bare GIT_DIR reproduces the exact condition (show-toplevel exits 128) while
# the working directory is a real work tree, so the fallback to it is correct.

set -euo pipefail

# This fixture itself runs as a selected pre-push check, so it may inherit the
# hook's linked-worktree Git environment. Resolve from the invoking directory
# when that context has a GIT_WORK_TREE without its matching GIT_DIR; the test
# below installs the bare GIT_DIR reproduction explicitly.
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
ROOT_CANON="$(cd "$ROOT" && pwd -P)"
# The fixture creates and selects its own bare Git directory below. Do not let
# a hook's partial linked-worktree environment leak into that reproduction.
unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
TMPDIR="$(mktemp -d "${TMPDIR:-/tmp}/omi-pre-push-wt.XXXXXX")"
trap 'rm -rf "$TMPDIR"' EXIT

BARE="$TMPDIR/bare.git"
git init -q --bare "$BARE"
BARE_ENV="$BARE"
if command -v cygpath >/dev/null 2>&1; then
  BARE_ENV="$(cygpath -am "$BARE")"
fi

# Sanity: confirm the reproduction actually triggers the 128 condition, so a
# future git that stops failing here turns this into a visible skip rather than a
# silently vacuous pass.
if GIT_DIR="$BARE_ENV" git -C "$ROOT" rev-parse --show-toplevel >/dev/null 2>&1; then
  echo "SKIP: this git does not surface the show-toplevel work-tree failure; cannot reproduce #10293." >&2
  exit 0
fi

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

# A stub Python that reports the working directory it was exec'd in, so the shell
# resolvers can be exercised without running the full gate. The current launchers
# resolve explicit interpreter variables before PATH, so inject both contracts.
STUB_BIN="$TMPDIR/bin"
mkdir -p "$STUB_BIN"
STUB_PYTHON="$STUB_BIN/python3"
cat >"$STUB_PYTHON" <<'EOF'
#!/usr/bin/env bash
printf 'CWD=%s\n' "$(pwd -P)"
EOF
chmod +x "$STUB_PYTHON"

# scripts/pre-push-singleflight and scripts/pr-preflight both resolve the root and
# cd into it before launching Python. Under the 128 condition they must reach the
# injected stub instead of aborting at resolution.
for script in pre-push-singleflight pr-preflight; do
  out="$(
    cd "$ROOT" &&
      GIT_DIR="$BARE_ENV" \
        PYTHON="$STUB_PYTHON" \
        BACKEND_PYTHON="$STUB_PYTHON" \
        OMI_PYTHON_EXECUTABLE="$STUB_PYTHON" \
        PATH="$STUB_BIN:$PATH" \
        bash "$ROOT/scripts/$script" 2>&1
  )" \
    || fail "scripts/$script aborted under the work-tree failure: $out"
  case "$out" in
    *"must be run in a work tree"*) fail "scripts/$script still aborts with the work-tree failure: $out" ;;
    "CWD=$ROOT_CANON") : ;;
    *) fail "scripts/$script resolved the wrong root under the work-tree failure: $out" ;;
  esac
done

# scripts/pre-push resolves the root, cd's into it, then fails fast on a missing
# base ref (this bare repo has no origin/main). The point is that it gets past
# resolution: the abort must be the base-ref failure, never the work-tree fatal.
out="$(cd "$ROOT" && GIT_DIR="$BARE_ENV" bash "$ROOT/scripts/pre-push" origin file://"$BARE" </dev/null 2>&1)" && true
case "$out" in
  *"must be run in a work tree"*) fail "scripts/pre-push still aborts with the work-tree failure: $out" ;;
  *"cannot find"*) : ;;
  *) fail "scripts/pre-push did not reach the base-ref check under the work-tree failure: $out" ;;
esac

# The Python entrypoints resolve the root directly. Prefer the interpreter already
# selected by the launcher, then the repository venv, then the host command.
PYTHON_EXECUTABLE="${OMI_PYTHON_EXECUTABLE:-${BACKEND_PYTHON:-}}"
if [[ -z "$PYTHON_EXECUTABLE" || ! -x "$PYTHON_EXECUTABLE" ]]; then
  for candidate in "$ROOT/backend/.venv/bin/python" "$ROOT/backend/.venv/Scripts/python.exe"; do
    if [[ -x "$candidate" ]]; then
      PYTHON_EXECUTABLE="$candidate"
      break
    fi
  done
fi
if [[ -z "$PYTHON_EXECUTABLE" || ! -x "$PYTHON_EXECUTABLE" ]]; then
  PYTHON_EXECUTABLE=""
  for command_name in python3 python py; do
    candidate="$(command -v "$command_name" || true)"
    if [[ -n "$candidate" && -x "$candidate" ]] &&
      "$candidate" -c "import pathlib" >/dev/null 2>&1; then
      PYTHON_EXECUTABLE="$candidate"
      break
    fi
  done
fi
[[ -n "$PYTHON_EXECUTABLE" && -x "$PYTHON_EXECUTABLE" ]] ||
  fail "no Python interpreter is available for the entrypoint probes"

# Both helpers must return the working directory rather than raise
# CalledProcessError. Compare inside Python so POSIX and Windows path spellings
# cannot make equivalent paths look different to the shell.
for probe in \
  "import preflight_runner as m; print(m.resolve_repo_root() == pathlib.Path.cwd().resolve())" \
  "import pr_preflight as m; print(m._resolve_repo_root().resolve() == pathlib.Path.cwd().resolve())"; do
  out="$(
    cd "$ROOT" &&
      GIT_DIR="$BARE_ENV" PYTHONUTF8=1 "$PYTHON_EXECUTABLE" -c \
        "import pathlib, sys; sys.path.insert(0, str(pathlib.Path.cwd() / '.github' / 'scripts')); $probe"
  )" \
    || fail "python resolver aborted under the work-tree failure: $probe"
  [ "$out" = "True" ] || fail "python resolver returned wrong root ($out) for: $probe"
done

echo "pre-push linked-worktree repo-root fallback test passed."
