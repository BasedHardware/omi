#!/bin/bash
# Direct single-service L3 harness.
#
# One platform process, one run-scoped SQLite path, one run id, two real shells,
# and an exact shell x domain evidence join. There is no attach mode and no
# alternate service door. Missing platform or shell evidence is a failure.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATHS="$(node "$HERE/lib/provenance.mjs" --paths 2>/dev/null || true)"
read -r CORE_REPO PLATFORM_REPO <<<"$(printf '%s' "$PATHS" | node -e '
  let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{try{const j=JSON.parse(s);console.log(`${j["core-foundation"]} ${j.platform}`)}catch{console.log("")}})')"
[[ -n "${CORE_REPO:-}" && -n "${PLATFORM_REPO:-}" ]] || { echo "ERROR: could not resolve core/platform roots." >&2; exit 1; }

SERVICE_REL="apps/service/bin/dev-server.ts"
SERVICE_LAUNCHER="$PLATFORM_REPO/$SERVICE_REL"
SERVICE_URL="http://127.0.0.1:4851"
MACOS_ORIGIN="http://127.0.0.1:5290"
SURFACES="$CORE_REPO/core/packages/surfaces"
MACOS_LAUNCHER="$CORE_REPO/core/shells/macos/scripts/dev-run-macos.sh"
IOS_LAUNCHER="$CORE_REPO/core/shells/ios/scripts/dev-run-ios.sh"

MODE_ASSERT=0 MODE_JSON=0 MODE_UP=0 STOP_ONLY=0 DOCTOR_ONLY=0
DEVICE=""
RED_PROOF=""
while (( $# )); do
  case "$1" in
    --assert) MODE_ASSERT=1; shift ;;
    --json) MODE_JSON=1; shift ;;
    --up) MODE_UP=1; shift ;;
    --stop) STOP_ONLY=1; shift ;;
    --doctor) DOCTOR_ONLY=1; shift ;;
    --device) DEVICE="${2:?--device needs a simulator UDID}"; shift 2 ;;
    --red-proof) RED_PROOF="${2:?--red-proof needs stale-dist|dead-backend|generation-mismatch}"; shift 2 ;;
    --help|-h)
      sed -n '2,10p' "$0"
      printf '%s\n' "usage: integration/dev-stack.sh [--device <udid>] [--assert] [--json] [--up]"
      exit 0
      ;;
    *) echo "ERROR: unknown option $1" >&2; exit 2 ;;
  esac
done

RUNDIR="${OMI_DEV_STACK_RUNDIR:-/tmp/omi-dev-stack}"
PIDFILE="$RUNDIR/pids"
REPORTFILE="$RUNDIR/last-run.json"

stop_tracked() {
  [[ -f "$PIDFILE" ]] || return 0
  while read -r name pid; do
    [[ "$pid" =~ ^[0-9]+$ ]] || continue
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      for _ in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.1; done
      kill -0 "$pid" 2>/dev/null && kill -KILL "$pid" 2>/dev/null || true
      printf 'stopped %s (pid %s)\n' "$name" "$pid"
    fi
  done < "$PIDFILE"
  rm -f "$PIDFILE"
}

if (( STOP_ONLY )); then
  stop_tracked
  exit 0
fi

if (( DOCTOR_ONLY )); then
  "$HERE/doctor.sh"
  exit $?
fi

RUN_ID="run-$(date -u +%Y%m%dT%H%M%SZ)-$$"
RUN_STARTED="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
RUN_DIR="$RUNDIR/runs/$RUN_ID"
LOG_DIR="$RUN_DIR/logs"
DATABASE_PATH="$RUN_DIR/service.sqlite"
READINESS_PATH="$RUN_DIR/service-readiness.json"
MACOS_RESULT="$RUN_DIR/macos-consumer.json"
IOS_RESULT="$RUN_DIR/ios-consumer.json"
CONSUMER_RESULT="$RUN_DIR/consumer.json"
PRODUCER_RESULT="$RUN_DIR/producer.json"
FACTS_PATH="$RUN_DIR/facts.json"
mkdir -p "$LOG_DIR"
: > "$PIDFILE"

LEAVE_RUNNING=0
cleanup() {
  if (( LEAVE_RUNNING == 0 )); then stop_tracked; fi
  rm -f "$READINESS_PATH" "$FACTS_PATH"
  if (( LEAVE_RUNNING == 0 )); then rm -f "$DATABASE_PATH" "$DATABASE_PATH-shm" "$DATABASE_PATH-wal"; fi
}
trap cleanup EXIT INT TERM

need() { command -v "$1" >/dev/null 2>&1 || { echo "ERROR: missing required tool $1" >&2; exit 1; }; }
for tool in bun node corepack lsof curl xcrun; do need "$tool"; done
[[ -f "$SERVICE_LAUNCHER" ]] || { echo "ERROR: required sibling launcher is absent: $SERVICE_LAUNCHER" >&2; exit 1; }
[[ -x "$MACOS_LAUNCHER" ]] || { echo "ERROR: macOS launcher is absent or not executable: $MACOS_LAUNCHER" >&2; exit 1; }
[[ -x "$IOS_LAUNCHER" ]] || { echo "ERROR: iOS launcher is absent or not executable: $IOS_LAUNCHER" >&2; exit 1; }

listener() { lsof -nP -iTCP:"$1" -sTCP:LISTEN 2>/dev/null || true; }
for port in 4851 5290; do
  held="$(listener "$port")"
  if [[ -n "$held" ]]; then
    echo "ERROR: required port $port is occupied; this harness will not kill it or drift ports." >&2
    printf '%s\n' "$held" >&2
    exit 1
  fi
done

printf 'run %s\n' "$RUN_ID"
printf 'service %s with SQLite %s\n' "$SERVICE_REL" "$DATABASE_PATH"
printf 'macOS origin %s; iOS origin omi-ui://local\n' "$MACOS_ORIGIN"

( cd "$CORE_REPO/core" \
    && corepack pnpm install --config.confirmModulesPurge=false --silent \
    && node "$HERE/check-surfaces-dependency-dist.mjs" --prepare-build \
    && corepack pnpm -r build ) > "$LOG_DIR/core-build.log" 2>&1 || {
  echo "ERROR: core workspace build failed; see $LOG_DIR/core-build.log" >&2
  tail -20 "$LOG_DIR/core-build.log" >&2
  exit 1
}

CORE_TREE="$(node "$HERE/lib/provenance.mjs" --repo core-foundation | node -e '
  let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{try{process.stdout.write(JSON.parse(s).treeHash??"")}catch{}})')"
SURFACE_TREE="$(node -e '
  const fs=require("fs");try{process.stdout.write(JSON.parse(fs.readFileSync(process.argv[1],"utf8")).treeHash??"")}catch{}' \
  "$SURFACES/dist/omi-build-stamp.json")"
[[ "$CORE_TREE" =~ ^[0-9a-f]{40}$ && "$SURFACE_TREE" =~ ^[0-9a-f]{40}$ ]] || {
  echo "ERROR: current shell/surface tree hashes are unavailable after build." >&2
  exit 1
}

# Direct execution is deliberate: no wrapper may announce another listener as
# this service. The companion writes a versioned readiness record containing
# its own executable, PID, run id, database path, evidence path, and dev token.
( cd "$PLATFORM_REPO" && \
  OMI_PORT=4851 \
  OMI_QA_DB="$DATABASE_PATH" \
  OMI_RUN_ID="$RUN_ID" \
  OMI_DEV_READY_RECORD="$READINESS_PATH" \
  OMI_DEV_EVIDENCE=1 \
  TZ=UTC \
  exec bun "$SERVICE_REL" ) > "$LOG_DIR/service.log" 2>&1 &
SERVICE_PID=$!
printf 'service %s\n' "$SERVICE_PID" >> "$PIDFILE"

ready=0
for _ in $(seq 1 80); do
  if [[ -s "$READINESS_PATH" ]] && curl -fsS --max-time 1 "$SERVICE_URL/ready" >/dev/null 2>&1; then ready=1; break; fi
  kill -0 "$SERVICE_PID" 2>/dev/null || break
  sleep 0.25
done
if (( ready == 0 )); then
  echo "ERROR: direct platform service emitted no valid readiness candidate within 20s." >&2
  echo "Required: $READINESS_PATH using schema omi.dev-service-readiness.v1." >&2
  tail -15 "$LOG_DIR/service.log" >&2
  exit 1
fi

READINESS_JSON="$(node "$HERE/lib/evidence-cli.mjs" validate-readiness \
  --record "$READINESS_PATH" --run-id "$RUN_ID" --database "$DATABASE_PATH" --pid "$SERVICE_PID")" || exit $?
DEV_TOKEN="$(printf '%s' "$READINESS_JSON" | node -e '
  let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{try{process.stdout.write(JSON.parse(s).devToken??"")}catch{}})')"
[[ -n "$DEV_TOKEN" ]] || { echo "ERROR: readiness record supplied no dev token." >&2; exit 1; }

OMI_API_TOKEN="$DEV_TOKEN" \
OMI_SURFACE_PORT=5290 \
OMI_SURFACES_DIST="$SURFACES/dist" \
OMI_BUILD_DIR="$RUN_DIR/macos-build" \
OMI_APP_NAME="omi-on-single-service-evidence" \
"$MACOS_LAUNCHER" --api "$SERVICE_URL" --evidence-out "$MACOS_RESULT" --run-id "$RUN_ID" \
  > "$LOG_DIR/macos.log" 2>&1
macos_status=$?
(( macos_status == 0 )) || { echo "ERROR: macOS evidence launch failed ($macos_status); see $LOG_DIR/macos.log" >&2; exit "$macos_status"; }
node "$HERE/lib/evidence-cli.mjs" stamp-shell --file "$MACOS_RESULT" --shell macos --run-id "$RUN_ID" --exit-code "$macos_status" || exit $?

ios_args=(--api "$SERVICE_URL" --evidence-out "$IOS_RESULT" --run-id "$RUN_ID")
[[ -n "$DEVICE" ]] && ios_args+=(--device "$DEVICE")
OMI_API_TOKEN="$DEV_TOKEN" \
OMI_SURFACES_DIST="$SURFACES/dist" \
"$IOS_LAUNCHER" "${ios_args[@]}" > "$LOG_DIR/ios.log" 2>&1
ios_status=$?
(( ios_status == 0 )) || { echo "ERROR: iOS evidence launch failed ($ios_status); see $LOG_DIR/ios.log" >&2; exit "$ios_status"; }
node "$HERE/lib/evidence-cli.mjs" stamp-shell --file "$IOS_RESULT" --shell ios --run-id "$RUN_ID" --exit-code "$ios_status" || exit $?

node "$HERE/lib/evidence-cli.mjs" merge-consumer \
  --macos "$MACOS_RESULT" --ios "$IOS_RESULT" --run-id "$RUN_ID" --out "$CONSUMER_RESULT" || exit $?

curl -fsS --max-time 5 \
  -H "Authorization: Bearer $DEV_TOKEN" \
  -G --data-urlencode "run=$RUN_ID" \
  "$SERVICE_URL/v1/qa/evidence" > "$PRODUCER_RESULT" || {
  echo "ERROR: platform companion did not expose producer evidence for $RUN_ID." >&2
  exit 1
}

if [[ "$RED_PROOF" == "stale-dist" || "$RED_PROOF" == "generation-mismatch" ]]; then
  node "$HERE/lib/evidence-cli.mjs" mutate --file "$CONSUMER_RESULT" --kind "$RED_PROOF" || exit $?
elif [[ -n "$RED_PROOF" && "$RED_PROOF" != "dead-backend" ]]; then
  echo "ERROR: unknown red proof $RED_PROOF" >&2
  exit 2
fi
if [[ "$RED_PROOF" == "dead-backend" ]]; then
  kill "$SERVICE_PID" 2>/dev/null || true
  for _ in $(seq 1 20); do kill -0 "$SERVICE_PID" 2>/dev/null || break; sleep 0.1; done
fi

REACHABLE_AFTER=0
curl -fsS --max-time 2 "$SERVICE_URL/ready" >/dev/null 2>&1 && REACHABLE_AFTER=1
FINISHED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
RUN_ID="$RUN_ID" RUN_STARTED="$RUN_STARTED" FINISHED_AT="$FINISHED_AT" \
READINESS_PATH="$READINESS_PATH" DATABASE_PATH="$DATABASE_PATH" REACHABLE_AFTER="$REACHABLE_AFTER" \
MACOS_RESULT="$MACOS_RESULT" IOS_RESULT="$IOS_RESULT" CONSUMER_RESULT="$CONSUMER_RESULT" PRODUCER_RESULT="$PRODUCER_RESULT" \
CORE_TREE="$CORE_TREE" SURFACE_TREE="$SURFACE_TREE" FACTS_PATH="$FACTS_PATH" SERVICE_PID="$SERVICE_PID" \
node -e '
  const fs=require("fs"),e=process.env,r=(p)=>JSON.parse(fs.readFileSync(p,"utf8"));
  fs.writeFileSync(e.FACTS_PATH,JSON.stringify({
    runId:e.RUN_ID,startedAt:e.RUN_STARTED,finishedAt:e.FINISHED_AT,
    expectedShellTreeHash:e.CORE_TREE,expectedSurfaceTreeHash:e.SURFACE_TREE,
    service:{databasePath:e.DATABASE_PATH,launchedPid:Number(e.SERVICE_PID),reachableAfter:e.REACHABLE_AFTER==="1",readiness:r(e.READINESS_PATH)},
    shells:{macos:r(e.MACOS_RESULT),ios:r(e.IOS_RESULT)},
    consumer:r(e.CONSUMER_RESULT),producer:r(e.PRODUCER_RESULT),
  },null,2)+"\n");' || exit $?

report_args=(--facts "$FACTS_PATH" --out "$REPORTFILE")
(( MODE_JSON )) && report_args+=(--json)
(( MODE_ASSERT )) && report_args+=(--assert)
node "$HERE/lib/run-report.mjs" "${report_args[@]}"
report_status=$?

if (( MODE_UP )); then LEAVE_RUNNING=1; fi
exit "$report_status"
