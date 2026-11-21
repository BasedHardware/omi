#!/usr/bin/env bash
# Decide how the backend unit shards select tests, once per workflow run, so
# every shard partitions the same selection.
#
#   mode=all      run the full suite (nightly, ci:full label, kill switch, or
#                 any lookup failure; also workflow_dispatch and non-main pushes)
#   mode=pr       pull request: changed files against the live base (unchanged)
#   mode=main     push to main: changed files since the last main push run of
#                 this workflow that succeeded, plus a rotating 1/8 slice of the
#                 full suite, so the whole suite still runs every ~8 pushes and
#                 the nightly full run stays the backstop
#
# Outputs (GITHUB_OUTPUT): mode, main_base, rotation, reason.
# Rotation slice K is the count of green main push runs modulo N.
# Kill switches (repository variables, on unless set to 0/false/off):
#   BACKEND_UNIT_MAIN_SELECTION  -- off: main pushes run the full suite again
#   BACKEND_UNIT_GRAPH_SELECTION -- read by the selector itself
set -euo pipefail

: "${GITHUB_OUTPUT:?}"
ROTATION_SLICES="${ROTATION_SLICES:-8}"
WORKFLOW_FILE="${WORKFLOW_FILE:-backend-unit-tests.yml}"

emit() {
  printf 'mode=%s\nmain_base=%s\nrotation=%s\nreason=%s\n' "$1" "${2:-}" "${3:-}" "$4" >> "$GITHUB_OUTPUT"
  echo "Backend unit plan: mode=$1 base=${2:-none} rotation=${3:-none} ($4)"
  exit 0
}

is_off() {
  case "$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]' | tr -d ' ')" in
    0 | false | off | no) return 0 ;;
    *) return 1 ;;
  esac
}

if [ -n "${NIGHTLY_MAIN_SHA:-}" ]; then
  emit all "" "" "nightly full run"
fi

case "${EVENT_NAME:-}" in
  pull_request)
    # A re-run keeps the original event payload, so read the current labels:
    # "add ci:full, then Re-run all jobs" forces the full unit suite. A
    # failed read keeps ordinary PR selection (the nightly still runs all).
    if labels="$(gh api --method GET "repos/$REPO/issues/$PR_NUMBER/labels" --jq '.[].name' 2>/dev/null)"; then
      if grep -Fxq 'ci:full' <<<"$labels"; then
        emit all "" "" "ci:full label"
      fi
    else
      echo "::warning::Could not read PR labels; ci:full is not applied to backend unit selection."
    fi
    emit pr "" "" "pull request changed files"
    ;;
  push)
    if [ "${REF:-}" != refs/heads/main ]; then
      emit all "" "" "push to ${REF:-unknown ref}"
    fi
    if is_off "${MAIN_SELECTION:-}"; then
      emit all "" "" "BACKEND_UNIT_MAIN_SELECTION kill switch is off"
    fi
    lookup=""
    if ! lookup="$(gh api --method GET \
      "repos/$REPO/actions/workflows/$WORKFLOW_FILE/runs?branch=main&event=push&status=success&per_page=1" \
      --jq '"\(.total_count) \(.workflow_runs[0].head_sha // "")"' 2>/dev/null)"; then
      emit all "" "" "last successful main run lookup failed"
    fi
    green_count="${lookup%% *}"
    base="${lookup#* }"
    if ! [[ "$base" =~ ^[0-9a-f]{40}$ ]]; then
      emit all "" "" "no successful main push run to diff from"
    fi
    if ! [[ "$green_count" =~ ^[0-9]+$ ]]; then
      emit all "" "" "green main run count unavailable for rotation"
    fi
    # Keyed by the number of green main push runs, not run_number (which PR
    # runs also consume): consecutive green main runs walk slices 0..N-1, and
    # a red run repeats its slice on the next push.
    emit main "$base" "$((green_count % ROTATION_SLICES))/$ROTATION_SLICES" "changed since last green main run"
    ;;
  *)
    emit all "" "" "event ${EVENT_NAME:-unknown}"
    ;;
esac
