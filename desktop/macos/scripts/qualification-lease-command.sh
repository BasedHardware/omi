#!/usr/bin/env bash
# Run the qualification lease CLI through the exact backend interpreter that
# qualification just provisioned. Lease errors are deliberately relayed to
# stderr: callers reserve stdout for the successful lease JSON capability.
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage:
  qualification-lease-command.sh acquire <worktree> <lease-id> <owner-pid> <port-offset> <retained-runs>
  qualification-lease-command.sh release <worktree> <lease-id> <token> <retained-runs> <retention-age-seconds>
USAGE
  exit 2
}

[[ $# -ge 1 ]] || usage
action="$1"
shift
lease_token=""

run_lease_command() {
  local worktree="$1"
  shift
  local lease_python="$worktree/backend/.venv/bin/python"
  local output status detail stderr_file
  if [[ ! -x "$lease_python" ]]; then
    echo "qualification failed: backend virtualenv is missing at $lease_python; lease ${action} cannot run" >&2
    return 127
  fi

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
