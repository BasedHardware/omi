#!/bin/bash
# The native inner loop: kill the running shell, regenerate + rebuild, relaunch.
# Usage: OMI_BUILD_DIR=<scratch> OMI_SURFACE_PROFILE=<unique-id> scripts/run-shell.sh
# Serves the real @omi-core/surfaces dist/ from the app's fixed-port loopback (5290).
# A profile is passed as a URL namespace (`?profile=...`) by the shell; this
# deliberately avoids deleting WebKit/IndexedDB data when a clean run is needed.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
out="${OMI_BUILD_DIR:-$here/.build}"
app_name="${OMI_APP_NAME:-omi-core-tasks-shell}"
if [[ ! "$app_name" =~ ^omi-[A-Za-z0-9][A-Za-z0-9.-]*$ ]]; then
  echo "ERROR: OMI_APP_NAME must match ^omi-[A-Za-z0-9][A-Za-z0-9.-]*$ (got '$app_name')" >&2
  exit 1
fi
port="${OMI_SURFACE_PORT:-5290}"
if [[ ! "$port" =~ ^[0-9]+$ ]] || (( port < 1024 || port > 65535 )); then
  echo "ERROR: OMI_SURFACE_PORT must be an integer from 1024 to 65535 (got '$port')" >&2
  exit 1
fi
ready_timeout="${OMI_READY_TIMEOUT_SECONDS:-15}"
if [[ ! "$ready_timeout" =~ ^[0-9]+$ ]] || (( ready_timeout < 1 || ready_timeout > 60 )); then
  echo "ERROR: OMI_READY_TIMEOUT_SECONDS must be an integer from 1 to 60 (got '$ready_timeout')" >&2
  exit 1
fi
acceptance_wait_timeout="${OMI_ACCEPTANCE_WAIT_SECONDS:-15}"
if [[ ! "$acceptance_wait_timeout" =~ ^[0-9]+$ ]] || (( acceptance_wait_timeout < 1 || acceptance_wait_timeout > 300 )); then
  echo "ERROR: OMI_ACCEPTANCE_WAIT_SECONDS must be an integer from 1 to 300 (got '$acceptance_wait_timeout')" >&2
  exit 1
fi
app="$out/${app_name}.app"
executable="$app/Contents/MacOS/$app_name"
# Truncate the run log HERE, not at launch. HOW-TO-RUN.md tells people to grep
# this file for the ACCEPTANCE verdict. If this script exits before the launch
# line — a busy port, a failed build, a bad env var — the PREVIOUS run's
# "status=PASS" is still sitting in it and reads as today's evidence. That
# already happened once: a run that died in this very preamble was reported as
# "acceptance FAILED (exit 1) — ACCEPTANCE ... status=PASS", pairing this run's
# failure with the last run's verdict. An empty file is honest; a stale one is not.
[[ -d "$out" ]] && { : > "$out/${app_name}.run.log"; } 2>/dev/null || true
# Free THIS PORT only — never every instance of this executable.
#
# This was `pkill -f -x "$executable"`, and it silently destroyed the thing the
# launcher exists to produce. dev-stack.sh runs the shell twice from one build
# dir: a windowed app on 5290, then a headless acceptance probe on 5293. Same
# $executable, so the probe's first act was to kill the window a moment after
# reporting it "running" — then the probe exited on OMI_ACCEPTANCE_EXIT. Every
# summary line was true in isolation (the window did serve 2 reads before it
# died) and the net result was no app at all.
#
# The intent here is only ever "free the port I am about to bind", so scope it
# to that port, and still only to our own executable — never a stranger's.
# `|| true` is required, not defensive: `set -o pipefail` is on, and lsof exits 1
# when nothing holds the port — the common case — so the assignment would take
# that status and `set -e` would abort the script before it printed anything.
port_pid="$(lsof -nP -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | head -1 || true)"
if [[ -n "$port_pid" ]] && [[ "$(ps -o comm= -p "$port_pid" 2>/dev/null)" == "$executable" ]]; then
  kill "$port_pid" 2>/dev/null || true
fi
# Port may still be held briefly after kill; wait for free so relaunch binds 5290.
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if ! lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    break
  fi
  sleep 0.2
done
if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "ERROR: loopback port $port remained busy after stopping $app_name" >&2
  exit 1
fi
"$here/scripts/build-shell.sh"
# Launch the executable directly so OMI_SURFACE_* and privileged API custody
# stay in the child environment. LaunchServices/open is not a reliable env
# propagation boundary; the token is never placed in argv.
log="$out/${app_name}.run.log"
"$executable" >"$log" 2>&1 &
pid=$!
echo "launched: $app pid=$pid  (loopback http://127.0.0.1:${port}/)"
ready=0
for ((i = 1; i <= ready_timeout; i++)); do
  if curl --fail --silent --show-error --max-time 1 "http://127.0.0.1:${port}/" >/dev/null 2>&1; then
    ready=1
    break
  fi
  # In acceptance-exit mode, preserve a child that fails before readiness as
  # the authoritative exit status rather than turning it into a generic curl
  # timeout. A zombie is still waitable, so inspect its process state first.
  if [[ -n "${OMI_ACCEPTANCE_EXIT:-}" || -n "${OMI_CONSUMER_EVIDENCE_EXIT:-}" || -n "${OMI_PROBE_EXIT:-}" ]]; then
    child_state="$(ps -o stat= -p "$pid" 2>/dev/null | tr -d '[:space:]')"
    if [[ -z "$child_state" || "$child_state" == Z* ]]; then
      set +e
      wait "$pid"
      child_status=$?
      set -e
      echo "ERROR: shell exited before readiness (status $child_status)" >&2
      exit "$child_status"
    fi
  fi
  sleep 1
done
if (( ready == 0 )); then
  if [[ -n "${OMI_ACCEPTANCE_EXIT:-}" || -n "${OMI_CONSUMER_EVIDENCE_EXIT:-}" || -n "${OMI_PROBE_EXIT:-}" ]]; then
    child_state="$(ps -o stat= -p "$pid" 2>/dev/null | tr -d '[:space:]')"
    if [[ -z "$child_state" || "$child_state" == Z* ]]; then
      set +e
      wait "$pid"
      child_status=$?
      set -e
      echo "ERROR: shell exited before readiness (status $child_status)" >&2
      exit "$child_status"
    fi
  fi
  kill "$pid" 2>/dev/null || true
  set +e
  wait "$pid"
  child_status=$?
  set -e
  echo "ERROR: shell did not serve http://127.0.0.1:${port}/ within ${ready_timeout}s" >&2
  exit 1
fi
echo "ready: http://127.0.0.1:${port}/"
if [[ -n "${OMI_SURFACE_PROFILE:-}" ]]; then
  echo "profile: URL namespace provided (value withheld)"
fi

# Interactive mode intentionally returns after HTTP readiness. Acceptance and
# fixture-probe modes are different: the app emits its host-observed verdict or
# snapshot and exits itself; wait for that exact child status, but bound the
# wait so a wedged probe cannot leave CI hanging. The watchdog targets only this
# PID and is reaped below.
if [[ -n "${OMI_ACCEPTANCE_EXIT:-}" || -n "${OMI_CONSUMER_EVIDENCE_EXIT:-}" || -n "${OMI_PROBE_EXIT:-}" ]]; then
  timeout_marker="$out/${app_name}.acceptance-timeout.$$"
  rm -f "$timeout_marker"
  (
    sleep "$acceptance_wait_timeout"
    child_state="$(ps -o stat= -p "$pid" 2>/dev/null | tr -d '[:space:]')"
    if [[ -n "$child_state" && "$child_state" != Z* ]]; then
      : >"$timeout_marker"
      kill "$pid" 2>/dev/null || true
      # Do not let a wedged child defeat the bound; this remains scoped to the
      # exact executable PID and never broad-kills a process group.
      sleep 1
      child_state="$(ps -o stat= -p "$pid" 2>/dev/null | tr -d '[:space:]')"
      if [[ -n "$child_state" && "$child_state" != Z* ]]; then
        kill -KILL "$pid" 2>/dev/null || true
      fi
    fi
  ) &
  watchdog_pid=$!
  set +e
  wait "$pid"
  child_status=$?
  set -e
  kill "$watchdog_pid" 2>/dev/null || true
  wait "$watchdog_pid" 2>/dev/null || true
  if [[ -f "$timeout_marker" ]]; then
    rm -f "$timeout_marker"
    echo "ERROR: acceptance child did not exit within ${acceptance_wait_timeout}s" >&2
    exit 124
  fi
  rm -f "$timeout_marker"
  if [[ -n "${OMI_CONSUMER_EVIDENCE_EXIT:-}" && ! -s "${OMI_CONSUMER_EVIDENCE_PATH:-}" ]]; then
    echo "ERROR: native consumer evidence result is missing or empty" >&2
    exit 1
  fi
  exit "$child_status"
fi
