#!/usr/bin/env bash
# Seeded acceptance journeys — canonical runner (SCA-488 / C2).
#
# One executable definition per behavior lives in integration_test/journeys/.
# This runner executes them on a chosen lane, collects session-evidence-v1
# shaped receipts, rejects zero-test results, and exits nonzero on any
# failure. C4 (verification integration) consumes this surface; do not add a
# second runner.
#
# Lanes:
#   hermetic  — host flutter-tester, loopback fixture backend, faked external
#               I/O at declared boundaries (default)
#   simulator — a booted iOS simulator running the real app (requires the C1
#               session harness backend + Auth emulator; pass its base URL)
#
# Usage:
#   bash integration_test/journeys/run_journeys.sh [--lane hermetic|simulator]
#        [--runs N] [--filter NAME] [--evidence-dir DIR] [--list]
#        [--api-base URL] [--device UDID]
#   --list prints the discovered journeys and exits 0 without running anything.
set -euo pipefail

cd "$(dirname "$0")/../.."

LANE="hermetic"
RUNS=1
FILTER=""
EVIDENCE_DIR=""
API_BASE=""
DEVICE=""
LIST_ONLY=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --lane) LANE="$2"; shift 2 ;;
    --runs) RUNS="$2"; shift 2 ;;
    --filter) FILTER="$2"; shift 2 ;;
    --evidence-dir) EVIDENCE_DIR="$2"; shift 2 ;;
    --api-base) API_BASE="$2"; shift 2 ;;
    --device) DEVICE="$2"; shift 2 ;;
    --list) LIST_ONLY=true; shift ;;
    *) echo "unknown option: $1" >&2; exit 64 ;;
  esac
done

if [[ -z "$EVIDENCE_DIR" ]]; then
  EVIDENCE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/journeys_XXXXXX")"
fi
mkdir -p "$EVIDENCE_DIR"
readonly EVIDENCE_DIR

# Mechanical discovery (SCA-490 / C4): every j<N>_<behavior>_test.dart in
# this directory is a journey. A new definition joins the suite by existing;
# there is no handwritten list to forget to update.
JOURNEYS=()
for f in integration_test/journeys/j[0-9]_*_test.dart; do
  [[ -f "$f" ]] || { echo "no journey definitions found under integration_test/journeys/" >&2; exit 66; }
  JOURNEYS+=("$(basename "$f")")
done

if $LIST_ONLY; then
  printf '%s\n' "${JOURNEYS[@]}"
  exit 0
fi

if [[ -n "$FILTER" ]]; then
  MATCHING=()
  for j in "${JOURNEYS[@]}"; do [[ "$j" == *"$FILTER"* ]] && MATCHING+=("$j"); done
  # An empty selection is drift, not success: a filter that matches nothing
  # must fail (exit 65) rather than execute zero runs and report PASS.
  if [[ ${#MATCHING[@]} -eq 0 ]]; then
    echo "selection drift: filter '$FILTER' matched no discovered journey (${JOURNEYS[*]})" >&2
    exit 65
  fi
  JOURNEYS=("${MATCHING[@]}")
fi

failures=0
for run in $(seq 1 "$RUNS"); do
  for journey in "${JOURNEYS[@]}"; do
    path="integration_test/journeys/$journey"
    [[ -f "$path" ]] || { echo "missing journey definition: $path" >&2; exit 66; }

    args=(test)
    if [[ "$LANE" == "hermetic" ]]; then
      # Host lane: flutter-tester. Without an explicit device the tool picks a
      # connected phone/simulator and tries a device build instead.
      args+=(-d flutter-tester --concurrency=1)
    elif [[ "$LANE" == "simulator" ]]; then
      [[ -n "$DEVICE" ]] || { echo "--lane simulator requires --device UDID" >&2; exit 64; }
      args+=(-d "$DEVICE" --flavor dev)
    else
      echo "unknown lane: $LANE" >&2; exit 64
    fi
    args+=("$path")

    echo "── run $run/$RUNS [$LANE] $journey"
    status=1
    for attempt in 1 2; do
      set +e
      OMI_JOURNEY_LANE="$LANE" \
      OMI_JOURNEY_EVIDENCE_DIR="$EVIDENCE_DIR" \
      ${API_BASE:+OMI_API_BASE_URL="$API_BASE"} \
      flutter "${args[@]}" 2>&1 | tee "$EVIDENCE_DIR/${journey%.dart}_run${run}.log" | tail -2
      status=${PIPESTATUS[0]}
      set -e
      # Bounded launch-infra retry ONLY: a tool-level failure to launch the
      # test bundle (device selection/build flake) is retried once and the
      # retry is visible in the log. An executed-but-failing test is NEVER
      # retried here — it must surface as a failure.
      if [[ $status -ne 0 ]] && grep -q "Failed to load\|Failed to build bundle\|Failed to launch app" "$EVIDENCE_DIR/${journey%.dart}_run${run}.log"; then
        echo "  (launch-infra failure; one bounded retry — never applied to executed test failures)" >&2
        continue
      fi
      break
    done

    # Zero-execution guard: a run that executed no tests never equals success.
    if grep -q "No tests ran\|Some tests failed\|Failed to load" "$EVIDENCE_DIR/${journey%.dart}_run${run}.log"; then
      echo "✗ $journey run $run: zero-execution or load failure (never success)" >&2
      failures=$((failures + 1))
      continue
    fi
    if [[ $status -ne 0 ]]; then
      echo "✗ $journey run $run: exit $status" >&2
      failures=$((failures + 1))
    else
      echo "✓ $journey run $run"
    fi
  done
done

echo
echo "Evidence receipts: $EVIDENCE_DIR ($(ls "$EVIDENCE_DIR" | wc -l | tr -d ' ') files)"
if [[ $failures -gt 0 ]]; then
  echo "RESULT: FAIL ($failures failing run(s))" >&2
  exit 1
fi
echo "RESULT: PASS ($((RUNS * ${#JOURNEYS[@]})) run(s) executed)"
