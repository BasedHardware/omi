#!/usr/bin/env bash
# Run through Firebase so Firestore is isolated and torn down automatically.
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$repo_root"

if [[ ! -x backend/.venv/bin/python ]]; then
  echo "Missing backend/.venv. Run backend/scripts/sync-python-deps.sh first." >&2
  exit 1
fi

# Firebase's Firestore emulator is a JVM process.  Prefer an already-configured
# Java, then make Homebrew's keg-only OpenJDK usable without asking every
# developer to modify a shell profile. Firebase CLI currently requires 21+.
if ! java -version >/dev/null 2>&1; then
  jdk_prefix="$(brew --prefix openjdk@21 2>/dev/null || true)"
  if [[ -n "$jdk_prefix" && -x "$jdk_prefix/libexec/openjdk.jdk/Contents/Home/bin/java" ]]; then
    export JAVA_HOME="$jdk_prefix/libexec/openjdk.jdk/Contents/Home"
    export PATH="$JAVA_HOME/bin:$PATH"
  fi
fi
if ! java -version >/dev/null 2>&1; then
  echo "Firebase's Firestore emulator needs Java 21+. Install it with: brew install openjdk@21" >&2
  exit 1
fi

# CI passes ``--state-dir`` (and any other runner argument) to the listen-pusher
# runner only, never to the subsequent pytest command.  Appending after ``&&``
# would leak the flag into pytest, which does not understand it.
#
# The state root is emitted as a token, not as the caller's path: the inner
# command is one shell string, so a path with a space is escaped inside it and a
# literal substitution in the supervisor would silently miss. The supervisor
# replaces the token with each attempt's own ``<root>/attempt-<n>``.
attempt_state_token='@ATTEMPT_STATE_DIR@'
lifecycle_only=false
if [[ "${1:-}" == "--lifecycle-only" ]]; then
  lifecycle_only=true
  shift
fi
runner_args=""
lifecycle_args=""
lifecycle_state=""
next_is_state=false
for argument in "$@"; do
  if [[ "$next_is_state" == true ]]; then
    lifecycle_state="$argument"
    next_is_state=false
    printf -v escaped_argument ' %q' "$attempt_state_token"
  elif [[ "$argument" == --state-dir=* ]]; then
    lifecycle_state="${argument#--state-dir=}"
    printf -v escaped_argument ' %q' "--state-dir=$attempt_state_token"
  else
    printf -v escaped_argument ' %q' "$argument"
  fi
  runner_args+="$escaped_argument"
  if [[ "$argument" == --state-dir ]]; then
    next_is_state=true
  elif [[ "$argument" == --keep ]]; then
    lifecycle_args+=" --keep"
  fi
done
if [[ -n "$lifecycle_state" ]]; then
  printf -v escaped_state ' %q' "$attempt_state_token/lifecycle-sim"
  lifecycle_args+=" --state-dir$escaped_state"
fi

runner_command="PYTHONPATH=backend backend/.venv/bin/python -m testing.listen_pusher_stack.run${runner_args} && PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests/unit/test_stale_processing_emulator_concurrency.py -v && PYTHONPATH=backend backend/.venv/bin/python -m testing.lifecycle_sim.run${lifecycle_args} --extra-test-module testing/lifecycle_properties/test_properties.py"
lifecycle_command="PYTHONPATH=backend backend/.venv/bin/python -m testing.lifecycle_sim.run${runner_args}"

# Firebase needs a concrete loopback port and can only bind it after this script
# released the probe socket that chose it. A Firestore client that lands on an
# HTTP responder in that window fails with `Trying to connect an http1.x server
# (HTTP status 400)` or an opaque 60s RetryError. emulator_supervisor.py gives
# every attempt a fresh port, proves Firestore gRPC readiness before the
# gauntlet starts, and retries only that startup class (max 3 attempts / 20 min).
emulator_args=(
  --project demo-omi-listen-stack
  --max-total-seconds "${OMI_STACK_EMULATOR_MAX_TOTAL_SECONDS:-900}"
  --readiness-timeout "${OMI_STACK_EMULATOR_READINESS_TIMEOUT:-120}"
)
if [[ -n "$lifecycle_state" ]]; then
  emulator_args+=(--log-dir "$lifecycle_state/emulator" --state-dir "$lifecycle_state")
fi

if [[ "$lifecycle_only" == true ]]; then
  PYTHONPATH=backend backend/.venv/bin/python -m testing.listen_pusher_stack.emulator_supervisor \
    --inner "$lifecycle_command" "${emulator_args[@]}"
  exit 0
fi

PYTHONPATH=backend backend/.venv/bin/python -m testing.listen_pusher_stack.emulator_supervisor \
  --inner "$runner_command" "${emulator_args[@]}"
