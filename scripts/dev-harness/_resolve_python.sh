#!/usr/bin/env bash

# Print the canonical locked backend interpreter when setup has created it.
dev_harness_canonical_python() {
  local repo_root candidate
  repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
  for candidate in \
    "$repo_root/backend/.venv/bin/python" \
    "$repo_root/backend/.venv/Scripts/python.exe"; do
    if [ -x "$candidate" ]; then
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
      printf '%s\n' "$candidate"
      return
    fi
  done

  printf '%s\n' "python3"
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
    echo "Run \`make dev-init\` first (creates backend/.venv and installs backend/requirements.txt)."
  } >&2
  return 1
}
