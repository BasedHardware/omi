#!/usr/bin/env bash

# Cheap pre-push always uses this interpreter. desktop-flow-lint imports PyYAML;
# harness wrappers import python-dotenv via dev_harness.cli. A directory named
# `.venv` is not proof it can run those gates (Spine A: incomplete venv made
# `git push` fail at check_desktop_flow_lint_if_needed).
dev_harness_venv_covers_cheap_gates() {
  local python_bin="$1"
  [ -n "$python_bin" ] || return 1
  "$python_bin" -c 'import dotenv, yaml' >/dev/null 2>&1
}

# The pre-push gate's check scripts use PEP 604 unions and `match` statements at
# module scope, so the selected interpreter must support Python >= 3.10 syntax.
# macOS ships Xcode CLT `python3` 3.9 where bare `python3` would otherwise crash
# the gate regardless of the diff being pushed.
dev_harness_python_floor_ok() {
  local python_bin="$1"
  [ -n "$python_bin" ] || return 1
  "$python_bin" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1
}

# dev_harness_python serves the whole pre-push harness, whose floor is 3.10.
# The backend itself is pinned tighter: every backend pylock declares
# `>=3.11,<3.12` and mobile_doctor rejects a non-3.11 backend venv, so
# provisioning (dev-init) prefers this interpreter when one is discoverable
# without installing anything: the PATH name first, then the uv-managed
# toolchain — the same runtime `make lane-backend` / `make lane-bootstrap`
# provision.
# Strict pinned-range probe for the backend runtime: the backend pylock
# declares `>=3.11,<3.12` and mobile_doctor rejects any other version, so a
# 3.10 or 3.12+ interpreter is as unusable for the backend venv as a 3.9 one.
dev_harness_venv_python_is_pinned_311() {
  [ -n "$1" ] || return 1
  "$1" -c 'import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] < (3, 12) else 1)' >/dev/null 2>&1
}

# Homebrew's keg-only 3.11 (`brew install python@3.11` — the remedy this
# resolver advertises) has no PATH link when a newer python3 shadows it;
# probe the same absolute prefixes dev_harness_python enumerates (Codex P1).
dev_harness_backend_pinned_prefixes() {
  cat <<'PREFIXES'
/opt/homebrew/opt/python@3.11/bin/python3.11
/usr/local/opt/python@3.11/bin/python3.11
/opt/homebrew/bin/python3.11
/usr/local/bin/python3.11
PREFIXES
}

dev_harness_backend_pinned_python() {
  # An explicit PYTHON= selection is the caller's interpreter choice (the same
  # override dev_harness_python honors); accept it when it passes the pin.
  if [ -n "${PYTHON:-}" ] && dev_harness_venv_python_is_pinned_311 "$PYTHON"; then
    printf '%s\n' "$PYTHON"
    return 0
  fi
  if command -v python3.11 >/dev/null 2>&1 \
    && dev_harness_venv_python_is_pinned_311 python3.11; then
    printf '%s\n' python3.11
    return 0
  fi
  local prefix_candidate
  for prefix_candidate in $(dev_harness_backend_pinned_prefixes); do
    if [ -x "$prefix_candidate" ] \
      && dev_harness_venv_python_is_pinned_311 "$prefix_candidate"; then
      printf '%s\n' "$prefix_candidate"
      return 0
    fi
  done
  local uv_bin candidate
  uv_bin="$(command -v uv 2>/dev/null)" || return 1
  candidate="$("$uv_bin" python find 3.11 2>/dev/null)" || return 1
  [ -n "$candidate" ] || return 1
  # Git Bash: `uv python find` prints a native Windows path, which the bash
  # `[ -x ]` probe cannot execute until converted to the POSIX form.
  if command -v cygpath >/dev/null 2>&1; then
    candidate="$(cygpath -u "$candidate" 2>/dev/null || printf '%s' "$candidate")"
  fi
  if [ -x "$candidate" ] && dev_harness_venv_python_is_pinned_311 "$candidate"; then
    printf '%s\n' "$candidate"
    return 0
  fi
  return 1
}

# Print the canonical locked backend interpreter when setup has created it.
# A venv must BOTH import the cheap-gate deps AND satisfy the 3.10 floor: a
# 3.9-created venv with dotenv/yaml installed would otherwise pass the import
# probe and still crash the PEP 604 check scripts at import time.
dev_harness_canonical_python() {
  local repo_root candidate
  repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
  for candidate in \
    "$repo_root/backend/.venv/bin/python" \
    "$repo_root/backend/.venv/Scripts/python.exe"; do
    if [ -x "$candidate" ]; then
      if ! dev_harness_venv_covers_cheap_gates "$candidate"; then
        echo "dev-harness: $candidate exists but cannot import yaml and dotenv (incomplete venv); ignoring it. Run: make lane-bootstrap" >&2
        continue
      fi
      if ! dev_harness_python_floor_ok "$candidate"; then
        echo "dev-harness: $candidate is below the 3.10 floor the pre-push check scripts require; ignoring it. Run: make lane-bootstrap" >&2
        continue
      fi
      printf '%s\n' "$candidate"
      return
    fi
  done
  return 1
}

# Print the interpreter for local dev-harness commands. PYTHON is an explicit
# caller choice; otherwise prefer the canonical venv while retaining support
# for existing checkouts that use the legacy backend/venv location.
dev_harness_python() {
  if [ -n "${PYTHON:-}" ]; then
    printf '%s\n' "$PYTHON"
    return
  fi

  local repo_root candidate
  if candidate="$(dev_harness_canonical_python)"; then
    printf '%s\n' "$candidate"
    return
  fi

  repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
  for candidate in \
    "$repo_root/backend/venv/bin/python" \
    "$repo_root/backend/venv/Scripts/python.exe"; do
    if [ -x "$candidate" ]; then
      if ! dev_harness_venv_covers_cheap_gates "$candidate"; then
        echo "dev-harness: $candidate exists but cannot import yaml and dotenv (incomplete venv); ignoring it. Run: make lane-bootstrap" >&2
        continue
      fi
      if ! dev_harness_python_floor_ok "$candidate"; then
        echo "dev-harness: $candidate is below the 3.10 floor the pre-push check scripts require; ignoring it. Run: make lane-bootstrap" >&2
        continue
      fi
      printf '%s\n' "$candidate"
      return
    fi
  done

  # PATH fallback: bare `python3` is often macOS system Python 3.9 (Xcode CLT),
  # which cannot import the pre-push check scripts (PEP 604 unions at module
  # scope). Prefer an explicit versioned interpreter first; keep bare `python3`
  # only when it actually satisfies the floor.
  # Among floor-qualified candidates prefer one that can also import the
  # cheap-gate deps (yaml + python-dotenv): this resolver is shared by
  # mobile-session.sh, dev-up.sh and the pre-push gates, so a version-newer
  # interpreter without those packages must not shadow an import-capable one.
  # When no candidate has the imports, keep the documented floor-only outcome
  # so the gate reports the missing module instead of a version crash.
  local fallback floor_only
  floor_only=""
  for fallback in python3.14 python3.13 python3.12 python3.11 python3.10 python3; do
    if dev_harness_python_floor_ok "$fallback"; then
      if dev_harness_venv_covers_cheap_gates "$fallback"; then
        printf '%s\n' "$fallback"
        return
      fi
      [ -n "$floor_only" ] || floor_only="$fallback"
    fi
  done

  # Hooks and cron contexts often run a stripped PATH (/usr/bin:/bin) where no
  # versioned name is reachable even though Homebrew's interpreters exist.
  # Absolute prefixes only: still floor-probed, still overridden by PYTHON=.
  local prefix_bin version
  for prefix_bin in \
    /opt/homebrew/opt/python@3.14/bin \
    /opt/homebrew/opt/python@3.13/bin \
    /opt/homebrew/opt/python@3.12/bin \
    /opt/homebrew/opt/python@3.11/bin \
    /opt/homebrew/opt/python@3.10/bin \
    /opt/homebrew/bin \
    /usr/local/opt/python@3.14/bin \
    /usr/local/opt/python@3.13/bin \
    /usr/local/opt/python@3.12/bin \
    /usr/local/opt/python@3.11/bin \
    /usr/local/opt/python@3.10/bin \
    /usr/local/bin; do
    [ -d "$prefix_bin" ] || continue
    for version in 3.14 3.13 3.12 3.11 3.10; do
      candidate="$prefix_bin/python$version"
      if dev_harness_python_floor_ok "$candidate"; then
        if dev_harness_venv_covers_cheap_gates "$candidate"; then
          printf '%s\n' "$candidate"
          return
        fi
        [ -n "$floor_only" ] || floor_only="$candidate"
      fi
    done
  done
  if [ -n "$floor_only" ]; then
    printf '%s\n' "$floor_only"
    return
  fi

  printf '%s\n' "python3"
}

# Advise callers who received a below-floor interpreter name (not a path). The
# gate cannot verify a name from a different interpreter, so pr_preflight.py
# re-checks the floor from inside Python and reports this guidance on failure.
dev_harness_python_floor_advisory() {
  cat <<'ADVISORY'
The dev harness selected bare `python3`, but it reports a version below the
3.10 floor the pre-push check scripts require (PEP 604 unions at module scope).
On macOS the PATH `python3` is often Xcode CLT Python 3.9.
Fix: run `make lane-bootstrap` to create backend/.venv (the canonical
interpreter), or install Python >= 3.10 (e.g. `brew install python@3.12`) and
put it on PATH, or select one explicitly with `PYTHON=/path/to/python3.12`.
ADVISORY
}

dev_harness_python_uses_windows_paths() {
  local python_bin="$1"
  local resolved resolved_lower
  resolved="$(command -v "$python_bin" 2>/dev/null || printf '%s' "$python_bin")"
  # bash 3.2 (macOS) has no ${var,,}; use tr for case-insensitive .exe match
  resolved_lower="$(printf '%s' "$resolved" | tr '[:upper:]' '[:lower:]')"
  case "$resolved_lower" in
    *.exe)
      return 0
      ;;
  esac
  return 1
}

# Join import roots with the separator understood by the selected interpreter,
# not the Bash host. Git Bash launches native Windows Python for .venv/Scripts,
# whose sys.path separator is ';' even though the surrounding shell uses ':'.
dev_harness_pythonpath() {
  local python_bin="$1"
  shift

  local separator=":"
  local entry
  local value=""
  if dev_harness_python_uses_windows_paths "$python_bin"; then
    separator=";"
  fi

  for entry in "$@"; do
    [ -n "$entry" ] || continue
    if [ -n "$value" ]; then
      value="${value}${separator}${entry}"
    else
      value="$entry"
    fi
  done
  if [ -n "${PYTHONPATH:-}" ]; then
    if [ -n "$value" ]; then
      value="${value}${separator}${PYTHONPATH}"
    else
      value="$PYTHONPATH"
    fi
  fi
  printf '%s\n' "$value"
}

# Name the provisioning step instead of letting an import traceback stand in for
# it. The harness's own prerequisite check lives inside the Python CLI, so an
# interpreter without backend/requirements.txt installed dies at
# `import dev_harness.cli` before that check can report anything.
dev_harness_require_cli() {
  local python_bin="$1"
  local pythonpath="$2"
  local probe

  if probe="$(PYTHONPATH="$pythonpath" "$python_bin" -c 'import dev_harness.cli' 2>&1)"; then
    return 0
  fi

  {
    echo "Omi dev harness is not provisioned: $python_bin cannot import dev_harness.cli"
    printf '%s\n' "$probe" | tail -n 1 | sed 's/^/  /'
    echo "Run \`make lane-bootstrap\` first (Python 3.11 venv + cheap-gate packages). Uvicorn/pyright: \`make lane-backend\`. Locked pylock sync remains \`make setup-backend\`."
  } >&2
  return 1
}
