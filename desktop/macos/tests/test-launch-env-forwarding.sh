#!/usr/bin/env bash
# `open` launches the app from launchd rather than from run.sh's shell, so an
# environment override documented in run.sh --help reaches the app only if it
# is forwarded with `open --env`. Before this guard,
# OMI_FORCE_CANONICAL_MEMORY_ATLAS was documented but never forwarded, so the
# canonical-atlas QA override silently did nothing on the normal launch path.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN="$ROOT/run.sh"

BUILD_FUNCTION="$(sed -n '/^build_launch_env_args()/,/^}/p' "$RUN")"

if [[ -z "$BUILD_FUNCTION" ]]; then
  echo "FAIL: build_launch_env_args is missing from $RUN" >&2
  exit 1
fi

# Unset: no --env arguments, so a normal launch is untouched.
(
  unset OMI_FORCE_CANONICAL_MEMORY_ATLAS
  eval "$BUILD_FUNCTION"
  build_launch_env_args

  if [ "${#LAUNCH_ENV_ARGS[@]}" -ne 0 ]; then
    echo "FAIL: expected no --env arguments when the override is unset, got: ${LAUNCH_ENV_ARGS[*]}" >&2
    exit 1
  fi
)

# Set: forwarded verbatim as an `open --env` pair.
(
  export OMI_FORCE_CANONICAL_MEMORY_ATLAS=1
  eval "$BUILD_FUNCTION"
  build_launch_env_args

  if [ "${#LAUNCH_ENV_ARGS[@]}" -ne 2 ]; then
    echo "FAIL: expected 2 --env arguments, got ${#LAUNCH_ENV_ARGS[@]}: ${LAUNCH_ENV_ARGS[*]}" >&2
    exit 1
  fi
  test "${LAUNCH_ENV_ARGS[0]}" = "--env"
  test "${LAUNCH_ENV_ARGS[1]}" = "OMI_FORCE_CANONICAL_MEMORY_ATLAS=1"
)

# Every `open` invocation on the launch path must carry the forwarded env, or
# the override works on some launch transports and not others.
OPEN_CALLS="$(grep -cE '^[[:space:]]*if ! open ' "$RUN" || true)"
# FC-shell-unset-array-under-nounset: expand the optional array with the
# `${arr[@]+"${arr[@]}"}` form, never bare `"${arr[@]}"`, so an empty array
# cannot trap `unbound variable` if this path ever runs under `set -u` on the
# bash 3.2 that ships with macOS.
OPEN_CALLS_WITH_ENV="$(grep -cE '^[[:space:]]*if ! open .*\$\{LAUNCH_ENV_ARGS\[@\]\+"\$\{LAUNCH_ENV_ARGS\[@\]\}"\}' "$RUN" || true)"

if [ "$OPEN_CALLS" -eq 0 ]; then
  echo "FAIL: no 'open' launch invocations found in $RUN" >&2
  exit 1
fi

if [ "$OPEN_CALLS" -ne "$OPEN_CALLS_WITH_ENV" ]; then
  echo "FAIL: $OPEN_CALLS 'open' launch invocations but only $OPEN_CALLS_WITH_ENV forward LAUNCH_ENV_ARGS in the nounset-safe form" >&2
  exit 1
fi

if grep -qE '^[[:space:]]*if ! open .*[^+]"\$\{LAUNCH_ENV_ARGS\[@\]\}"' "$RUN"; then
  echo "FAIL: bare \"\${LAUNCH_ENV_ARGS[@]}\" expansion traps under set -u on bash 3.2 (FC-shell-unset-array-under-nounset)" >&2
  exit 1
fi

# Documented overrides must stay documented: help text and forwarding agree.
if ! grep -q "OMI_FORCE_CANONICAL_MEMORY_ATLAS=1  Non-production-only local QA override" "$RUN"; then
  echo "FAIL: OMI_FORCE_CANONICAL_MEMORY_ATLAS is forwarded but no longer documented in run.sh --help" >&2
  exit 1
fi

echo "PASS: launch env forwarding"
