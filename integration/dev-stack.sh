#!/bin/bash
# Direct single-service L3 harness: one Bun service, one SQLite database, one
# raw run id, and the exact native macOS + iOS evidence documents.
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
OWNER_TOOL="$HERE/lib/process-owner.mjs"
LOG_SANITIZER="$HERE/lib/sanitize-log.mjs"
ARTIFACT_GUARD="$HERE/lib/artifact-safety.mjs"

MODE_ASSERT=0 MODE_JSON=0 MODE_UP=0 STOP_ONLY=0 DOCTOR_ONLY=0
DEVICE=""
REQUESTED_RUN_ID=""
RED_PROOF=""
while (( $# )); do
  case "$1" in
    --assert) MODE_ASSERT=1; shift ;;
    --json) MODE_JSON=1; shift ;;
    --up) MODE_UP=1; shift ;;
    --stop) STOP_ONLY=1; shift ;;
    --doctor) DOCTOR_ONLY=1; shift ;;
    --device) DEVICE="${2:?--device needs a simulator UDID}"; shift 2 ;;
    --run-id) REQUESTED_RUN_ID="${2:?--run-id needs a raw run id}"; shift 2 ;;
    --red-proof) RED_PROOF="${2:?--red-proof needs stale-dist|dead-backend|generation-mismatch}"; shift 2 ;;
    --help|-h)
      sed -n '2,8p' "$0"
      printf '%s\n' "usage: integration/dev-stack.sh [--run-id <raw-id>] [--device <udid>] [--assert] [--json] [--up|--stop]"
      exit 0
      ;;
    *) echo "ERROR: unknown option $1" >&2; exit 2 ;;
  esac
done

if (( MODE_UP && (MODE_ASSERT || MODE_JSON) )); then
  echo "ERROR: --up is service-only and cannot be combined with --assert or --json." >&2
  exit 2
fi
if (( STOP_ONLY && (MODE_UP || MODE_ASSERT || MODE_JSON) )); then
  echo "ERROR: --stop cannot be combined with a run mode." >&2
  exit 2
fi

RUNDIR="${OMI_DEV_STACK_RUNDIR:-/tmp/omi-dev-stack}"
OWNERFILE="$RUNDIR/service-owner.json"
REPORTFILE="$RUNDIR/last-run.json"
mkdir -p "$RUNDIR"

if (( STOP_ONLY )); then
  node "$OWNER_TOOL" stop --record "$OWNERFILE"
  exit $?
fi
if (( DOCTOR_ONLY )); then
  "$HERE/doctor.sh"
  exit $?
fi

RUN_ID="${REQUESTED_RUN_ID:-run-$(date -u +%Y%m%dT%H%M%SZ)-$$}"
node "$HERE/lib/evidence-cli.mjs" validate-run-id --run-id "$RUN_ID" >/dev/null || exit $?
RUN_STARTED="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
RUN_DIR="$RUNDIR/runs/$RUN_ID"
LOG_DIR="$RUN_DIR/logs"
DATABASE_PATH="$RUN_DIR/service.sqlite"
READINESS_PATH="$RUN_DIR/service-readiness.json"
TOKEN_PATH="$RUN_DIR/readiness-token"
MACOS_RESULT="$RUN_DIR/macos-consumer.json"
IOS_RESULT="$RUN_DIR/ios-consumer.json"
CONSUMER_RESULT="$RUN_DIR/consumer.json"
PRODUCER_RESULT="$RUN_DIR/producer.json"
FACTS_PATH="$RUN_DIR/facts.json"
SERVICE_LOG_PIPE="$RUN_DIR/service-log.pipe"
SERVICE_LOG_READY="$RUN_DIR/service-log-sanitizer-ready"
mkdir -p "$LOG_DIR"

LEAVE_RUNNING=0
OWNER_WRITTEN=0
SERVICE_PID=""
SERVICE_LOGGER_PID=""
cleanup() {
  local stop_rc=0
  if (( LEAVE_RUNNING )); then return; fi
  if (( OWNER_WRITTEN )); then
    node "$OWNER_TOOL" stop --record "$OWNERFILE" >/dev/null 2>&1 || stop_rc=$?
  elif [[ "$SERVICE_PID" =~ ^[0-9]+$ ]] && kill -0 "$SERVICE_PID" 2>/dev/null; then
    kill "$SERVICE_PID" 2>/dev/null || true
    wait "$SERVICE_PID" 2>/dev/null || true
  fi
  if [[ "$SERVICE_LOGGER_PID" =~ ^[0-9]+$ ]]; then wait "$SERVICE_LOGGER_PID" 2>/dev/null || true; fi
  [[ ! -p "$SERVICE_LOG_PIPE" ]] || rm -f -- "$SERVICE_LOG_PIPE"
  [[ ! -e "$SERVICE_LOG_READY" ]] || rm -f -- "$SERVICE_LOG_READY"
  if (( stop_rc == 0 )); then rm -rf -- "$RUN_DIR"; fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

need() { command -v "$1" >/dev/null 2>&1 || { echo "ERROR: missing required tool $1" >&2; exit 1; }; }
for tool in bun node lsof curl mkfifo; do need "$tool"; done
[[ -f "$SERVICE_LAUNCHER" ]] || { echo "ERROR: required sibling launcher is absent: $SERVICE_LAUNCHER" >&2; exit 1; }
node "$OWNER_TOOL" prepare --record "$OWNERFILE" >/dev/null || exit $?

listener() { lsof -nP -iTCP:"$1" -sTCP:LISTEN 2>/dev/null || true; }
occupied=0
held="$(listener 4851)"
if [[ -n "$held" ]]; then
  echo "ERROR: required port 4851 is occupied; this harness will not kill it or start a second listener." >&2
  printf '%s\n' "$held" >&2
  occupied=1
fi
if (( MODE_UP == 0 )); then
  held="$(listener 5290)"
  if [[ -n "$held" ]]; then
    echo "ERROR: required port 5290 is occupied; this harness will not kill it or drift ports." >&2
    printf '%s\n' "$held" >&2
    occupied=1
  fi
fi
(( occupied == 0 )) || exit 1

printf 'run %s\n' "$RUN_ID"
printf 'service %s with one run-scoped SQLite database\n' "$SERVICE_REL"
rm -f -- "$SERVICE_LOG_PIPE" "$SERVICE_LOG_READY" "$LOG_DIR/service.log"
mkfifo "$SERVICE_LOG_PIPE" || { echo "ERROR: could not create the service log sanitizer pipe." >&2; exit 1; }
node "$LOG_SANITIZER" --stream --out "$LOG_DIR/service.log" \
  --readiness "$READINESS_PATH" --ready-out "$SERVICE_LOG_READY" \
  < "$SERVICE_LOG_PIPE" >/dev/null 2>&1 &
SERVICE_LOGGER_PID=$!
( cd "$PLATFORM_REPO" && \
  OMI_PORT=4851 \
  OMI_QA_DB="$DATABASE_PATH" \
  OMI_RUN_ID="$RUN_ID" \
  OMI_DEV_READY_RECORD="$READINESS_PATH" \
  OMI_DEV_EVIDENCE=1 \
  TZ=UTC \
  exec bun "$SERVICE_REL" ) > "$SERVICE_LOG_PIPE" 2>&1 &
SERVICE_PID=$!

ready=0
for _ in $(seq 1 80); do
  if [[ -s "$READINESS_PATH" ]] && curl -fsS --max-time 1 "$SERVICE_URL/ready" >/dev/null 2>&1; then ready=1; break; fi
  kill -0 "$SERVICE_PID" 2>/dev/null || break
  sleep 0.25
done
if (( ready == 0 )); then
  echo "ERROR: direct platform service emitted no valid readiness candidate within 20s." >&2
  tail -15 "$LOG_DIR/service.log" >&2
  exit 1
fi

rm -f -- "$TOKEN_PATH"
node "$HERE/lib/evidence-cli.mjs" validate-readiness \
  --record "$READINESS_PATH" --run-id "$RUN_ID" --database "$DATABASE_PATH" \
  --pid "$SERVICE_PID" --token-out "$TOKEN_PATH" >/dev/null || exit $?
DEV_TOKEN="$(read -r value < "$TOKEN_PATH"; printf '%s' "$value")"
rm -f -- "$TOKEN_PATH"
[[ -n "$DEV_TOKEN" ]] || { echo "ERROR: readiness record supplied no dev token." >&2; exit 1; }

log_ready=0
for _ in $(seq 1 80); do
  if [[ -s "$SERVICE_LOG_READY" ]]; then log_ready=1; break; fi
  kill -0 "$SERVICE_LOGGER_PID" 2>/dev/null || break
  sleep 0.025
done
rm -f -- "$SERVICE_LOG_PIPE"
if (( log_ready == 0 )); then
  echo "ERROR: service diagnostics were not accepted by the streaming sanitizer." >&2
  exit 1
fi
rm -f -- "$SERVICE_LOG_READY"
node "$ARTIFACT_GUARD" --readiness "$READINESS_PATH" --path "$LOG_DIR" >/dev/null || exit $?

SNAPSHOT="$(node "$OWNER_TOOL" snapshot --pid "$SERVICE_PID")" || exit $?
PROCESS_START_IDENTITY="$(printf '%s' "$SNAPSHOT" | node -e '
  let s="";process.stdin.on("data",d=>s+=d).on("end",()=>process.stdout.write(JSON.parse(s).startIdentity))')"
OWNER_TOKEN="$(node "$OWNER_TOOL" new-token)" || exit $?
node "$OWNER_TOOL" write --record "$OWNERFILE" --run-id "$RUN_ID" --pid "$SERVICE_PID" \
  --owner-token "$OWNER_TOKEN" --start-identity "$PROCESS_START_IDENTITY" \
  --database "$DATABASE_PATH" --readiness "$READINESS_PATH" >/dev/null || exit $?
OWNER_WRITTEN=1

if (( MODE_UP )); then
  LEAVE_RUNNING=1
  printf 'service-ready run=%s pid=%s owner=%s\n' "$RUN_ID" "$SERVICE_PID" "$OWNERFILE"
  exit 0
fi

# Everything below this line belongs only to the full two-shell assertion run.
# --up has already returned, so it cannot invoke a build or either native shell.
for tool in corepack xcrun; do need "$tool"; done
[[ -x "$MACOS_LAUNCHER" ]] || { echo "ERROR: macOS launcher is absent or not executable: $MACOS_LAUNCHER" >&2; exit 1; }
[[ -x "$IOS_LAUNCHER" ]] || { echo "ERROR: iOS launcher is absent or not executable: $IOS_LAUNCHER" >&2; exit 1; }
printf 'macOS origin %s; iOS origin omi-ui://local\n' "$MACOS_ORIGIN"

CORE_BUILD_RAW="$LOG_DIR/core-build.raw.log"
( cd "$CORE_REPO/core" \
  && corepack pnpm install --config.confirmModulesPurge=false --silent \
  && node "$HERE/check-surfaces-dependency-dist.mjs" --prepare-build \
  && corepack pnpm -r build ) > "$CORE_BUILD_RAW" 2>&1
core_build_status=$?
node "$LOG_SANITIZER" --in "$CORE_BUILD_RAW" --out "$LOG_DIR/core-build.log"
rm -f -- "$CORE_BUILD_RAW"
if (( core_build_status != 0 )); then
  echo "ERROR: core workspace build failed; see the run-scoped core build log." >&2
  tail -20 "$LOG_DIR/core-build.log" >&2
  exit "$core_build_status"
fi

CORE_TREE="$(node "$HERE/lib/provenance.mjs" --repo core-foundation | node -e '
  let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{try{process.stdout.write(JSON.parse(s).treeHash??"")}catch{}})')"
SURFACE_TREE="$(node -e '
  const fs=require("fs");try{process.stdout.write(JSON.parse(fs.readFileSync(process.argv[1],"utf8")).treeHash??"")}catch{}' \
  "$SURFACES/dist/omi-build-stamp.json")"
[[ "$CORE_TREE" =~ ^[0-9a-f]{40}$ && "$SURFACE_TREE" =~ ^[0-9a-f]{40}$ ]] || {
  echo "ERROR: current shell/surface tree hashes are unavailable after build." >&2
  exit 1
}

MACOS_RAW="$LOG_DIR/macos.raw.log"
OMI_API_TOKEN="$DEV_TOKEN" \
OMI_SURFACE_PORT=5290 \
OMI_SURFACES_DIST="$SURFACES/dist" \
OMI_BUILD_DIR="$RUN_DIR/macos-build" \
OMI_APP_NAME="omi-on-single-service-evidence" \
"$MACOS_LAUNCHER" --api "$SERVICE_URL" --evidence-out "$MACOS_RESULT" --run-id "$RUN_ID" \
  > "$MACOS_RAW" 2>&1
macos_status=$?
node "$HERE/lib/sanitize-log.mjs" --in "$MACOS_RAW" --out "$LOG_DIR/macos.log" --redact "$DEV_TOKEN" --redact "$SERVICE_URL"
rm -f -- "$MACOS_RAW"
(( macos_status == 0 )) || { echo "ERROR: macOS evidence launch failed ($macos_status); see the sanitized run-scoped log." >&2; exit "$macos_status"; }

ios_args=(--api "$SERVICE_URL" --evidence-out "$IOS_RESULT" --run-id "$RUN_ID")
[[ -n "$DEVICE" ]] && ios_args+=(--device "$DEVICE")
IOS_RAW="$LOG_DIR/ios.raw.log"
OMI_API_TOKEN="$DEV_TOKEN" \
OMI_SURFACES_DIST="$SURFACES/dist" \
"$IOS_LAUNCHER" "${ios_args[@]}" > "$IOS_RAW" 2>&1
ios_status=$?
node "$HERE/lib/sanitize-log.mjs" --in "$IOS_RAW" --out "$LOG_DIR/ios.log" --redact "$DEV_TOKEN" --redact "$SERVICE_URL"
rm -f -- "$IOS_RAW"
(( ios_status == 0 )) || { echo "ERROR: iOS evidence launch failed ($ios_status); see the sanitized run-scoped log." >&2; exit "$ios_status"; }

node "$HERE/lib/evidence-cli.mjs" merge-consumer \
  --macos "$MACOS_RESULT" --ios "$IOS_RESULT" --run-id "$RUN_ID" --out "$CONSUMER_RESULT" || exit $?

curl -fsS --max-time 5 \
  -H "Authorization: Bearer $DEV_TOKEN" \
  -G --data-urlencode "run=$RUN_ID" \
  "$SERVICE_URL/v1/qa/evidence" > "$PRODUCER_RESULT" || {
  echo "ERROR: platform companion did not expose producer evidence for the raw run id." >&2
  exit 1
}

if [[ "$RED_PROOF" == "stale-dist" || "$RED_PROOF" == "generation-mismatch" ]]; then
  node "$HERE/lib/evidence-cli.mjs" mutate --file "$CONSUMER_RESULT" --kind "$RED_PROOF" || exit $?
elif [[ -n "$RED_PROOF" && "$RED_PROOF" != "dead-backend" ]]; then
  echo "ERROR: unknown red proof $RED_PROOF" >&2
  exit 2
fi
if [[ "$RED_PROOF" == "dead-backend" ]]; then
  node "$OWNER_TOOL" stop --record "$OWNERFILE" >/dev/null || exit $?
  OWNER_WRITTEN=0
fi

REACHABLE_AFTER=0
curl -fsS --max-time 2 "$SERVICE_URL/ready" >/dev/null 2>&1 && REACHABLE_AFTER=1
FINISHED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
RUN_ID="$RUN_ID" RUN_STARTED="$RUN_STARTED" FINISHED_AT="$FINISHED_AT" \
DATABASE_PATH="$DATABASE_PATH" REACHABLE_AFTER="$REACHABLE_AFTER" \
CONSUMER_RESULT="$CONSUMER_RESULT" PRODUCER_RESULT="$PRODUCER_RESULT" \
CORE_TREE="$CORE_TREE" SURFACE_TREE="$SURFACE_TREE" FACTS_PATH="$FACTS_PATH" SERVICE_PID="$SERVICE_PID" \
node -e '
  const fs=require("fs"),e=process.env,r=(p)=>JSON.parse(fs.readFileSync(p,"utf8"));
  fs.writeFileSync(e.FACTS_PATH,JSON.stringify({
    schema:"omi.dev-stack-facts.v1",runId:e.RUN_ID,startedAt:e.RUN_STARTED,finishedAt:e.FINISHED_AT,
    expectedShellTreeHash:e.CORE_TREE,expectedSurfaceTreeHash:e.SURFACE_TREE,
    service:{databasePath:e.DATABASE_PATH,launchedPid:Number(e.SERVICE_PID),reachableAfter:e.REACHABLE_AFTER==="1"},
    launchers:{macos:{status:"pass",exitCode:0},ios:{status:"pass",exitCode:0}},
    consumer:r(e.CONSUMER_RESULT),producer:r(e.PRODUCER_RESULT),
  },null,2)+"\n");' || exit $?

report_args=(--facts "$FACTS_PATH" --readiness "$READINESS_PATH" --out "$REPORTFILE")
(( MODE_JSON )) && report_args+=(--json)
(( MODE_ASSERT )) && report_args+=(--assert)
node "$HERE/lib/run-report.mjs" "${report_args[@]}"
report_status=$?
retained_paths=("$LOG_DIR" "$MACOS_RESULT" "$IOS_RESULT" "$CONSUMER_RESULT" "$PRODUCER_RESULT" "$FACTS_PATH")
[[ ! -f "$REPORTFILE" ]] || retained_paths+=("$REPORTFILE")
artifact_args=(--readiness "$READINESS_PATH")
for retained_path in "${retained_paths[@]}"; do artifact_args+=(--path "$retained_path"); done
node "$ARTIFACT_GUARD" "${artifact_args[@]}" >/dev/null || exit $?
exit "$report_status"
