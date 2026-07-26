#!/usr/bin/env bash
# Run the qualification lease CLI through the exact backend interpreter that
# qualification just provisioned. Lease errors are deliberately relayed to
# stderr: callers reserve stdout for the successful lease JSON capability.
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage:
  qualification-lease-command.sh acquire <worktree> <lease-id> <owner-pid> <port-offset> <retained-runs>
  qualification-lease-command.sh preflight-fault-cleanup <worktree> <lease-id> <token> <result-path>
  qualification-lease-command.sh release <worktree> <lease-id> <token> <retained-runs> <retention-age-seconds>
USAGE
  exit 2
}

[[ $# -ge 1 ]] || usage
action="$1"
shift
lease_token=""

resolve_qualification_python() {
  local worktree="$1"
  local override="${OMI_QUALIFICATION_PYTHON:-}"
  local worktree_python="$worktree/backend/.venv/bin/python"
  local shared_python=""

  if [[ -n "${HOME:-}" ]]; then
    shared_python="$HOME/workspace/omi/backend/.venv/bin/python"
  fi

  if [[ -n "$override" ]]; then
    if [[ -f "$override" && -x "$override" ]]; then
      printf '%s/%s\n' "$(cd "$(dirname "$override")" && pwd -P)" "$(basename "$override")"
      return 0
    fi
    echo "qualification failed: OMI_QUALIFICATION_PYTHON is not an executable file: $override; attempted safe interpreter paths: OMI_QUALIFICATION_PYTHON=$override" >&2
    return 127
  fi

  if [[ -f "$worktree_python" && -x "$worktree_python" ]]; then
    printf '%s\n' "$worktree_python"
    return 0
  fi
  if [[ -n "$shared_python" && -f "$shared_python" && -x "$shared_python" ]]; then
    printf '%s\n' "$shared_python"
    return 0
  fi

  if [[ -n "$shared_python" ]]; then
    echo "qualification failed: no executable dependency interpreter; attempted safe interpreter paths: worktree=$worktree_python; shared=$shared_python; set OMI_QUALIFICATION_PYTHON to an executable path to override" >&2
  else
    echo "qualification failed: no executable dependency interpreter; attempted safe interpreter paths: worktree=$worktree_python; shared=<HOME-unavailable>/workspace/omi/backend/.venv/bin/python; set OMI_QUALIFICATION_PYTHON to an executable path to override" >&2
  fi
  return 127
}

run_lease_command() {
  local worktree="$1"
  shift
  local lease_python
  local output status detail stderr_file
  lease_python="$(resolve_qualification_python "$worktree")" || return $?

  stderr_file="$(mktemp "${TMPDIR:-/tmp}/omi-qualification-lease-command.XXXXXX")" || {
    echo "qualification failed: could not capture lease ${action} diagnostics" >&2
    return 1
  }

  # The harness resolves its repo root from cwd, so run it inside the exact
  # tag-pinned cache worktree. Stdout remains the acquire capability channel;
  # stderr is retained only for an actionable failure diagnostic.
  if output="$(
    (
      cd "$worktree" || exit $?
      PYTHONPATH="scripts/dev-harness${PYTHONPATH:+:$PYTHONPATH}" "$lease_python" -m dev_harness.cli qualification-lease "$action" "$@"
    ) 2>"$stderr_file"
  )"; then
    rm -f "$stderr_file"
    if [[ "$action" == "acquire" ]]; then
      printf '%s\n' "$output"
    fi
    return 0
  else
    status=$?
  fi

  detail="${output//$'\n'/ } $(tr '\n' ' ' < "$stderr_file")"
  rm -f "$stderr_file"
  if [[ -n "$lease_token" ]]; then
    detail="${detail//"$lease_token"/[redacted]}"
  fi
  detail="${detail:0:500}"
  if [[ -n "$detail" ]]; then
    echo "qualification failed: lease ${action} exited ${status}: ${detail}" >&2
  else
    echo "qualification failed: lease ${action} exited ${status} without a diagnostic" >&2
  fi
  return "$status"
}

case "$action" in
  acquire)
    [[ $# -eq 5 ]] || usage
    worktree="$1"
    run_lease_command "$worktree" --lease-id "$2" --owner-pid "$3" --port-offset "$4" --retained-runs "$5"
    ;;
  preflight-fault-cleanup)
    [[ $# -eq 4 ]] || usage
    worktree="$1"
    lease_token="$3"
    run_lease_command "$worktree" --lease-id "$2" --token "$3" --result "$4"
    ;;
  release)
    [[ $# -eq 5 ]] || usage
    worktree="$1"
    lease_token="$3"
    run_lease_command "$worktree" --lease-id "$2" --token "$3" --retained-runs "$4" --retention-age-seconds "$5"
    ;;
  *)
    usage
    ;;
esac
