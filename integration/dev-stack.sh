#!/bin/bash
# ============================================================================
# omi dev-stack — bring up the whole local stack and put the apps in front of you
# ============================================================================
#
# ONE COMMAND:  integration/dev-stack.sh
#
# It boots the new backend, builds and serves the surfaces, then builds and
# launches the macOS app and the iOS simulator app pointed at your local stack.
# Ctrl-C stops everything it started. Re-running is safe.
#
# ---------------------------------------------------------------------------
# READ THIS FIRST — WHICH BACKEND IS ACTUALLY SERVING WHAT
# ---------------------------------------------------------------------------
# Tonight the stack runs TWO generations side by side, and the difference is
# the single easiest thing to misread:
#
#   Memories (read path)  ->  NEW backend, port 4851, ratified contracts 0.1.1
#   Tasks / Conversations / Folders -> LEGACY wire, port 4747, qa-api-server
#
# Only the memory READ path is ratified. Everything else is deliberately still
# on the legacy wire. When this script prints its summary it labels every
# domain with the generation that actually served it. A green legacy result is
# NOT a new-stack result.
#
#   *** KNOWN GAP as of 78d8bfbbb2 — read the report before believing any
#   *** "runs on the new backend" claim, including one this script prints.
#   ***
#   *** FE-CORE has landed the client HALF: `core/packages/adapters-platform/`
#   *** (the ratified memory-read client) and
#   *** `core/packages/domain/src/generation-selection.ts` (the host-driven
#   *** per-domain knob, which rejects an unavailable generation rather than
#   *** silently downgrading).
#   ***
#   *** What is still missing is the CONSUMER: `surfaces/src/production/
#   *** main.tsx` still calls `createLegacyProductionStoreFactory` and nothing
#   *** else. So every domain in the running app — memories included — is
#   *** served by the LEGACY wire. The pieces exist; they are not connected.
#   *** That last wire is FE-SURFACES' to land.
#
# ---------------------------------------------------------------------------
# USAGE
# ---------------------------------------------------------------------------
#   integration/dev-stack.sh                 # everything: backend + surfaces + macOS + iOS
#   integration/dev-stack.sh --only-backend  # just the new backend on 4851
#   integration/dev-stack.sh --only-macos    # backend + surfaces + macOS app
#   integration/dev-stack.sh --only-ios      # backend + surfaces + iOS simulator
#   integration/dev-stack.sh --no-ios        # skip iOS (fastest full desktop loop)
#   integration/dev-stack.sh --stop          # stop anything a previous run left behind
#   integration/dev-stack.sh --help
#
# RESET THE SEED DATA
#   curl 'http://127.0.0.1:4851/qa/reset?seed=12'          # 12 deterministic rows
#   curl 'http://127.0.0.1:4851/qa/reset?seed=7&hidden=retrieval-node-v1:seed-0003'
#   ...or just re-run this script; it reseeds on every boot.
#   --seed N sets the initial row count.
#
# POINT AT A DIFFERENT BACKEND
#   OMI_BACKEND_URL=http://127.0.0.1:4811 integration/dev-stack.sh --no-ios
#   (4811 is BE-SURFACE's binding. This script will NOT boot its own backend
#    when OMI_BACKEND_URL names a port other than 4851 — it expects yours to be
#    up already, and fails loudly with that exact message if it is not.)
#
# IS TRAFFIC ACTUALLY FLOWING?
#   curl -s http://127.0.0.1:4851/qa/stats
#   -> {"servedRequests":N,"servedReads":N,...}
#   This script prints those counters before and after it drives the apps, and
#   FAILS if the count is still zero after an app was launched in bridge mode.
#   Zero served requests with a happy-looking UI is the exact failure this
#   check exists for: a stalled bridge is indistinguishable from offline, and
#   a surface rendering fixtures looks identical to one rendering live data.
#
# FIXTURE ROUTES DO NOT COUNT
#   Any URL with `qa=...` (e.g. ?qa=memories&state=normal) selects an in-page
#   FIXTURE store and never touches the bridge or any backend. Those routes are
#   useful for rendering checks and are worthless as evidence that the stack is
#   wired. This script keeps them strictly separate and never lets a fixture
#   route back a served-traffic claim.
#
# TIME IS PINNED
#   Every child gets TZ=UTC and the fixture clock is anchored to
#   2026-01-15T12:00:00Z (midday UTC on purpose). Day-grouping in the UI
#   renders in local time, so without this, Today/Tomorrow/Later assertions
#   drift with your machine's timezone.
#
# PORTS IT USES     4851 new backend | 4852 surfaces | 4747 legacy fake
#                   5290 macOS shell's own loopback (it serves its bundled dist)
# ============================================================================
set -uo pipefail

# ── Locations ───────────────────────────────────────────────────────────────
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_REPO="$(cd "$HERE/.." && pwd)"
WORKSPACE="$(cd "$CORE_REPO/.." && pwd)"
PLATFORM_REPO="$WORKSPACE/platform"
TRACKER="$WORKSPACE/omi-frontend-unification-and-microapps-project-tracker"
# The PROMOTED shell (FE-SHELLS, core/shells/). The tracker prototype is NOT
# equivalent: its bridge counts requests at DISPATCH, so it reports a healthy
# nonzero servedCount while every request fails and the backend serves nothing.
# The promoted shell keys acceptance on succeededCount and emits a traffic
# breakdown. Driving the prototype is what made my first servedReads claim
# unreproducible. Override only if you know why.
MACOS_SHELL="${OMI_MACOS_SHELL:-$CORE_REPO/core/shells/macos}"
IOS_SHELL="$TRACKER/prototypes/flutter-webview"
LEGACY_FAKE="$TRACKER/prototypes/qa-api-server/server.mjs"
SURFACES="$CORE_REPO/core/packages/surfaces"

RUNDIR="${OMI_DEV_STACK_RUNDIR:-/tmp/omi-dev-stack}"
LOGDIR="$RUNDIR/logs"

BACKEND_PORT=4851
SURFACES_PORT=4852
LEGACY_PORT=4747
BACKEND_URL="${OMI_BACKEND_URL:-http://127.0.0.1:$BACKEND_PORT}"

SEED="${OMI_SEED:-7}"
# Which backend generation the APP should use for memories.
#   legacy   -> the old wire on 4747 (default; what every domain uses today)
#   platform -> the NEW backend on 4851 over the settled /v1/memories route
GENERATION="${OMI_GENERATION:-legacy}"
WANT_BACKEND=1 WANT_SURFACES=1 WANT_MACOS=1 WANT_IOS=1
export TZ=UTC

# ── Output helpers ──────────────────────────────────────────────────────────
if [[ -t 1 ]]; then B=$'\033[1m'; R=$'\033[31m'; G=$'\033[32m'; Y=$'\033[33m'; C=$'\033[36m'; Z=$'\033[0m'
else B=""; R=""; G=""; Y=""; C=""; Z=""; fi
say()  { printf '%s\n' "${C}▸${Z} $*"; }
ok()   { printf '%s\n' "${G}✓${Z} $*"; }
warn() { printf '%s\n' "${Y}!${Z} $*"; }
die()  { printf '%s\n' "${R}✗ $*${Z}" >&2; exit 1; }
# Every failure must say what to DO about it, not just what went wrong.
fixit() { printf '%s\n' "${R}✗ $1${Z}" >&2; shift; for l in "$@"; do printf '    %s\n' "$l" >&2; done; exit 1; }

# ── Args ────────────────────────────────────────────────────────────────────
STOP_ONLY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h) sed -n '2,90p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    --stop) STOP_ONLY=1; shift ;;
    --only-backend) WANT_SURFACES=0; WANT_MACOS=0; WANT_IOS=0; shift ;;
    --only-macos)   WANT_IOS=0; shift ;;
    --only-ios)     WANT_MACOS=0; shift ;;
    --no-ios)       WANT_IOS=0; shift ;;
    --seed) SEED="${2:?--seed needs a number}"; shift 2 ;;
    --generation) GENERATION="${2:?--generation needs legacy|platform}"; shift 2 ;;
    *) die "unknown option: $1  (try --help)" ;;
  esac
done

mkdir -p "$RUNDIR" "$LOGDIR"

# ── Child tracking + cleanup ────────────────────────────────────────────────
# Idempotency requirement: Ctrl-C and re-run must never leave an orphan holding
# 4851/4852. We track our own PIDs in a file AND sweep the ports by identity.
PIDFILE="$RUNDIR/pids"
track() { echo "$1 $2" >> "$PIDFILE"; }

stop_tracked() {
  [[ -f "$PIDFILE" ]] || return 0
  while read -r name pid; do
    [[ -n "${pid:-}" ]] || continue
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      for _ in 1 2 3 4 5 6 7 8 9 10; do kill -0 "$pid" 2>/dev/null || break; sleep 0.2; done
      kill -0 "$pid" 2>/dev/null && kill -KILL "$pid" 2>/dev/null || true
      say "stopped $name (pid $pid)"
    fi
  done < "$PIDFILE"
  rm -f "$PIDFILE"
}

# Sweep a port only if the listener is one of ours. Never kill a stranger's
# process just because it happens to hold the port — say so instead.
free_port() {
  local port="$1" want="$2"
  local pids; pids="$(lsof -nP -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  [[ -z "$pids" ]] && return 0
  for pid in $pids; do
    local cmd; cmd="$(ps -o command= -p "$pid" 2>/dev/null || true)"
    if [[ "$cmd" == *"$want"* ]]; then
      kill "$pid" 2>/dev/null || true
      for _ in 1 2 3 4 5; do kill -0 "$pid" 2>/dev/null || break; sleep 0.2; done
      kill -0 "$pid" 2>/dev/null && kill -KILL "$pid" 2>/dev/null || true
    else
      fixit "port $port is held by a process that is not ours (pid $pid)." \
        "command: $cmd" \
        "This script refuses to kill it. Stop it yourself, or free the port:" \
        "  kill $pid"
    fi
  done
}

CLEANED=0
cleanup() {
  [[ $CLEANED -eq 1 ]] && return; CLEANED=1
  echo; say "shutting down..."
  stop_tracked
  ok "stack stopped. Logs kept in $LOGDIR"
}
trap cleanup EXIT INT TERM

if [[ $STOP_ONLY -eq 1 ]]; then
  stop_tracked
  free_port "$BACKEND_PORT" "integration/server/serve.ts"
  free_port "$SURFACES_PORT" "dev-stack-static"
  free_port "$LEGACY_PORT" "qa-api-server"
  ok "stopped whatever a previous run left behind."
  trap - EXIT; exit 0
fi

# ── Preflight ───────────────────────────────────────────────────────────────
say "${B}preflight${Z}"
need() {
  command -v "$1" >/dev/null 2>&1 || fixit "missing required tool: $1" "${@:2}"
}
need bun  "Install it:  brew install oven-sh/bun/bun"
need node "Install Node 22+:  brew install node"
need pnpm "Install it:  npm i -g pnpm@10"
need lsof "lsof ships with macOS; your PATH may be broken."
[[ -d "$PLATFORM_REPO" ]] || fixit "backend repo not found at $PLATFORM_REPO" \
  "Expected the 'platform' checkout next to this one." \
  "  ls $WORKSPACE"
[[ -f "$PLATFORM_REPO/integration/server/serve.ts" ]] || fixit \
  "backend entrypoint missing: $PLATFORM_REPO/integration/server/serve.ts" \
  "Your platform checkout is on the wrong branch." \
  "  cd $PLATFORM_REPO && git checkout codex/track3-backend-integration"

if [[ $WANT_MACOS -eq 1 ]]; then
  need swiftc "Install Xcode command line tools:  xcode-select --install"
  [[ -x "$MACOS_SHELL/scripts/run-shell.sh" ]] || { warn "macOS shell prototype not found at $MACOS_SHELL — skipping macOS"; WANT_MACOS=0; }
fi
if [[ $WANT_IOS -eq 1 ]]; then
  if ! command -v xcrun >/dev/null 2>&1; then warn "xcrun missing — skipping iOS"; WANT_IOS=0;
  elif ! command -v flutter >/dev/null 2>&1; then warn "flutter missing — skipping iOS (install: mise use flutter)"; WANT_IOS=0;
  elif [[ ! -d "$IOS_SHELL/app" ]]; then warn "iOS shell prototype not found at $IOS_SHELL — skipping iOS"; WANT_IOS=0; fi
fi
ok "tools present"

# Clear our own leftovers before binding anything.
stop_tracked
free_port "$BACKEND_PORT" "integration/server/serve.ts"
free_port "$SURFACES_PORT" "dev-stack-static"

# ── 1. New backend (4851) ───────────────────────────────────────────────────
BACKEND_OWNED=0
if [[ "$BACKEND_URL" != "http://127.0.0.1:$BACKEND_PORT" ]]; then
  say "${B}backend${Z} — using external $BACKEND_URL (not booting our own)"
  curl -fsS --max-time 3 "$BACKEND_URL/health" >/dev/null 2>&1 || fixit \
    "no backend answering at $BACKEND_URL/health" \
    "You set OMI_BACKEND_URL, so this script did not boot one." \
    "Start that backend first, or unset OMI_BACKEND_URL to use the built-in one on $BACKEND_PORT."
  ok "external backend reachable at $BACKEND_URL"
elif [[ $WANT_BACKEND -eq 1 ]]; then
  say "${B}backend${Z} — booting new stack on $BACKEND_PORT (TZ=UTC, seed=$SEED)"
  ( cd "$PLATFORM_REPO" && TZ=UTC OMI_INTEGRATION_PORT="$BACKEND_PORT" \
      bun run integration/server/serve.ts ) > "$LOGDIR/backend.log" 2>&1 &
  track backend $!
  BACKEND_OWNED=1
  for i in $(seq 1 40); do
    curl -fsS --max-time 1 "$BACKEND_URL/health" >/dev/null 2>&1 && break
    sleep 0.25
    [[ $i -eq 40 ]] && fixit "backend never became ready on $BACKEND_PORT" \
      "Log: $LOGDIR/backend.log" "$(tail -5 "$LOGDIR/backend.log" 2>/dev/null || echo '(no log)')"
  done
  curl -fsS "$BACKEND_URL/qa/reset?seed=$SEED" >/dev/null || die "seed failed"
  ok "backend live at $BACKEND_URL  (seeded $SEED rows)"
fi

if [[ $WANT_BACKEND -eq 1 || "$BACKEND_URL" != "http://127.0.0.1:$BACKEND_PORT" ]]; then
  echo "    dev token:  ${B}omi-integration-qa-key-v1${Z}   (QA only, loopback only)"
  echo "    try it:     curl -s '$BACKEND_URL/qa/stats'"
fi

# Loopback-only proof: lsof says 127.0.0.1, AND a LAN curl must FAIL.
if [[ $BACKEND_OWNED -eq 1 ]]; then
  bind_rows="$(lsof -nP -iTCP:"$BACKEND_PORT" -sTCP:LISTEN 2>/dev/null || true)"
  if echo "$bind_rows" | grep -qE '(\*|0\.0\.0\.0):'"$BACKEND_PORT"; then
    die "backend is bound to a wildcard address, not loopback. Refusing to continue."
  fi
  lan_ip="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"
  if [[ -n "$lan_ip" ]]; then
    if curl -fsS --max-time 2 "http://$lan_ip:$BACKEND_PORT/health" >/dev/null 2>&1; then
      die "backend answered on the LAN address $lan_ip:$BACKEND_PORT. It must be loopback-only."
    fi
    ok "loopback-only confirmed (lsof + LAN probe to $lan_ip refused)"
  else
    warn "no LAN address found; LAN-reachability probe SKIPPED (not proven, not passed)"
  fi
fi

[[ $WANT_SURFACES -eq 0 && $WANT_MACOS -eq 0 && $WANT_IOS -eq 0 ]] && {
  echo; ok "backend only. Ctrl-C to stop."; while true; do sleep 3600; done; }

# ── 2. Legacy wire (4747) — what the apps actually consume today ────────────
if [[ -f "$LEGACY_FAKE" ]]; then
  if lsof -nP -iTCP:"$LEGACY_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    ok "legacy wire already up on $LEGACY_PORT (reusing)"
  else
    say "${B}legacy wire${Z} — booting qa-api-server on $LEGACY_PORT"
    ( cd "$(dirname "$LEGACY_FAKE")" && node server.mjs ) > "$LOGDIR/legacy.log" 2>&1 &
    track legacy $!
    for i in $(seq 1 20); do
      lsof -nP -iTCP:"$LEGACY_PORT" -sTCP:LISTEN >/dev/null 2>&1 && break; sleep 0.25
    done
    ok "legacy wire on http://127.0.0.1:$LEGACY_PORT (token omi-qa-fake-token-v1)"
  fi
else
  warn "legacy qa-api-server not found — the apps will show 'bridge unavailable' for legacy domains"
fi

# ── 3. Surfaces ─────────────────────────────────────────────────────────────
say "${B}surfaces${Z} — building @omi-core/surfaces"
( cd "$CORE_REPO/core" && pnpm install --config.confirmModulesPurge=false --silent && pnpm --filter @omi-core/surfaces build ) \
  > "$LOGDIR/surfaces-build.log" 2>&1 \
  || fixit "surfaces build failed" "Log: $LOGDIR/surfaces-build.log" "$(tail -15 "$LOGDIR/surfaces-build.log")"
[[ -f "$SURFACES/dist/index.html" ]] || fixit "surfaces build produced no dist/index.html" \
  "Log: $LOGDIR/surfaces-build.log"
ok "surfaces built -> $SURFACES/dist"

say "${B}surfaces${Z} — serving on $SURFACES_PORT"
( cd "$SURFACES/dist" && exec -a dev-stack-static node -e '
  const http=require("http"),fs=require("fs"),p=require("path");
  const types={".html":"text/html",".js":"text/javascript",".css":"text/css",".json":"application/json",".svg":"image/svg+xml",".woff2":"font/woff2"};
  http.createServer((req,res)=>{
    const u=new URL(req.url,"http://x"); let f=p.join(process.cwd(),decodeURIComponent(u.pathname));
    if(!f.startsWith(process.cwd())){res.writeHead(403).end();return;}
    if(fs.existsSync(f)&&fs.statSync(f).isDirectory())f=p.join(f,"index.html");
    if(!fs.existsSync(f))f=p.join(process.cwd(),"index.html");
    res.writeHead(200,{"content-type":types[p.extname(f)]||"application/octet-stream"});
    fs.createReadStream(f).pipe(res);
  }).listen(4852,"127.0.0.1");
' ) > "$LOGDIR/surfaces-serve.log" 2>&1 &
track surfaces $!
for i in $(seq 1 20); do curl -fsS --max-time 1 "http://127.0.0.1:$SURFACES_PORT/" >/dev/null 2>&1 && break; sleep 0.25; done
curl -fsS --max-time 2 "http://127.0.0.1:$SURFACES_PORT/" >/dev/null 2>&1 \
  || fixit "surfaces server never came up on $SURFACES_PORT" "Log: $LOGDIR/surfaces-serve.log"
ok "surfaces at http://127.0.0.1:$SURFACES_PORT/"

# ── 4. macOS app ────────────────────────────────────────────────────────────
STATS_BEFORE="$(curl -s "$BACKEND_URL/qa/stats" 2>/dev/null || echo '{}')"
if [[ $WANT_MACOS -eq 1 ]]; then
  # The shell's loopback port defaults to 5290 and is NOT in the port registry,
  # so two people running a macOS shell collide and the second one dies with a
  # bare "port remained busy". Pick a free port instead, and say which.
  SHELL_PORT="${OMI_SHELL_PORT:-5290}"
  if lsof -nP -iTCP:"$SHELL_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    holder="$(ps -o command= -p "$(lsof -nP -tiTCP:"$SHELL_PORT" -sTCP:LISTEN 2>/dev/null | head -1)" 2>/dev/null | sed 's#.*/##')"
    for candidate in 5291 5292 5293 5294 5295 5296 5297 5298 5299; do
      if ! lsof -nP -iTCP:"$candidate" -sTCP:LISTEN >/dev/null 2>&1; then
        warn "port $SHELL_PORT is taken by another shell (${holder:-unknown}); using $candidate instead"
        SHELL_PORT="$candidate"; break
      fi
    done
  fi
  # WITHOUT OMI_API_BASE_URL the shell registers no HTTP handler at all and the
  # surface truthfully renders "bridge unavailable" — the app looks broken and
  # serves zero requests. This is the legacy wire because that is what the
  # surfaces actually consume today; see the KNOWN GAP note at the top.
  if [[ "$GENERATION" == "platform" ]]; then
    # The app's memories surface reads the NEW backend over GET /v1/memories.
    export OMI_API_BASE_URL="$BACKEND_URL"
    export OMI_API_TOKEN="omi-integration-qa-key-v1"
    # BOTH are required. `generation=platform` alone leaves route=home, which takes
    # the legacy branch and dispatches legacy calls at the platform backend - they
    # fail, and a dispatch-counting shell calls that a PASS.
    export OMI_SURFACE_QUERY="route=memories&generation=platform"
    say "generation=platform — memories will read the NEW backend at $BACKEND_URL"
  else
    export OMI_API_BASE_URL="http://127.0.0.1:$LEGACY_PORT"
    export OMI_API_TOKEN="omi-qa-fake-token-v1"
    unset OMI_SURFACE_QUERY
  fi

  say "${B}macOS app${Z} — building and launching on $SHELL_PORT (bundles the dist you just built)"
  ( cd "$MACOS_SHELL" && OMI_BUILD_DIR="$MACOS_SHELL/.build/on-integration" \
      OMI_APP_NAME="omi-on-integration" OMI_SURFACES_DIST="$SURFACES/dist" \
      OMI_SURFACE_PORT="$SHELL_PORT" TZ=UTC ./scripts/run-shell.sh ) > "$LOGDIR/macos.log" 2>&1
  if [[ $? -ne 0 ]]; then
    warn "macOS shell failed to launch — see $LOGDIR/macos.log"
    tail -8 "$LOGDIR/macos.log" | sed 's/^/    /'
  else
    ok "macOS app running — its surface is at http://127.0.0.1:$SHELL_PORT/"
    echo "    window should be open now; if not, check $LOGDIR/macos.log"
  fi

  # BRIDGE ACCEPTANCE. A separate, headless run of the same app that exits with
  # its own verdict. The app reports a HOST-OBSERVED served count and passes
  # only when it is nonzero: probes prove nothing, and a stalled bridge is
  # indistinguishable from offline. We propagate the CHILD's exit status —
  # waiting only for HTTP readiness would report success while this failed.
  ACCEPT_PORT=$((SHELL_PORT + 3))
  say "${B}macOS bridge acceptance${Z} — headless run on $ACCEPT_PORT, asserts nonzero served traffic"
  ( cd "$MACOS_SHELL" && OMI_BUILD_DIR="$MACOS_SHELL/.build/on-integration" \
      OMI_APP_NAME="omi-on-integration" OMI_SURFACES_DIST="$SURFACES/dist" \
      OMI_SURFACE_PORT="$ACCEPT_PORT" OMI_ACCEPTANCE_EXIT=1 TZ=UTC \
      ./scripts/run-shell.sh ) > "$LOGDIR/macos-acceptance.log" 2>&1
  accept_status=$?
  accept_line="$(grep -o 'ACCEPTANCE .*' "$MACOS_SHELL/.build/on-integration/omi-on-integration.run.log" 2>/dev/null | tail -1)"
  if [[ $accept_status -eq 0 && "$accept_line" == *"status=PASS"* ]]; then
    ok "bridge acceptance reported PASS — $accept_line"
    # NEVER trust this line on its own. A shell that counts dispatches reports
    # PASS while the backend serves zero; that is exactly how a false green got
    # published from this launcher. The backend's own counter is the arbiter,
    # and it is cross-checked in the summary below.
    if [[ "$accept_line" == *"httpError="* && "$accept_line" != *"httpError=0"* ]]; then
      warn "…but the shell recorded HTTP errors — requests reached a backend that refused them:"
      warn "   ${accept_line#*ACCEPTANCE }"
    fi
  else
    warn "bridge acceptance FAILED (exit $accept_status) — ${accept_line:-no acceptance line emitted}"
    echo "    log: $LOGDIR/macos-acceptance.log"
  fi
fi

# ── 5. iOS simulator ────────────────────────────────────────────────────────
if [[ $WANT_IOS -eq 1 ]]; then
  UDID="$(xcrun simctl list devices booted -j 2>/dev/null | node -e '
    let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{
      try{const j=JSON.parse(s);for(const k of Object.keys(j.devices||{}))
        for(const d of j.devices[k])if(d.state==="Booted"&&/iPhone|iPad/.test(d.name)){console.log(d.udid);return;}
      }catch{}});' )"
  if [[ -z "$UDID" ]]; then
    warn "no booted iOS simulator found — skipping iOS"
    echo "    boot one:  xcrun simctl boot 'iPhone 17 Pro' && open -a Simulator"
  else
    say "${B}iOS app${Z} — bundling surfaces and running on simulator $UDID"
    ( cd "$IOS_SHELL" && SURFACES_DIST="$SURFACES/dist" node tools/build-surfaces-bundle.mjs ) \
      > "$LOGDIR/ios-bundle.log" 2>&1 \
      || warn "iOS surface bundling failed — see $LOGDIR/ios-bundle.log"
    ( cd "$IOS_SHELL/app" && TZ=UTC flutter run -d "$UDID" --release ) > "$LOGDIR/ios.log" 2>&1 &
    track ios $!
    say "iOS build started in background (cold builds take ~100s). Log: $LOGDIR/ios.log"
  fi
fi

# ── 6. Did anything actually flow? ──────────────────────────────────────────
sleep 3
STATS_AFTER="$(curl -s "$BACKEND_URL/qa/stats" 2>/dev/null || echo '{}')"
read_before="$(echo "$STATS_BEFORE" | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{try{console.log(JSON.parse(s).servedReads??0)}catch{console.log(0)}})')"
read_after="$(echo "$STATS_AFTER" | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{try{console.log(JSON.parse(s).servedReads??0)}catch{console.log(0)}})')"

echo
printf '%s\n' "${B}══════════════════ stack up ══════════════════${Z}"
printf '  %-22s %s\n' "new backend"  "$BACKEND_URL   (memories read path, ratified 0.1.1)"
printf '  %-22s %s\n' "legacy wire"  "http://127.0.0.1:$LEGACY_PORT   (tasks, conversations, folders)"
printf '  %-22s %s\n' "surfaces"     "http://127.0.0.1:$SURFACES_PORT/"
[[ $WANT_MACOS -eq 1 ]] && printf "  %-22s %s\n" "macOS app" "http://127.0.0.1:${SHELL_PORT:-5290}/  (app window)"
[[ $WANT_IOS  -eq 1 ]] && printf '  %-22s %s\n' "iOS app" "simulator ${UDID:-none}"
echo
printf '  %s\n' "${B}served by the NEW backend:${Z} servedReads ${read_before} -> ${read_after}"
if [[ "$read_after" == "0" && "$GENERATION" == "platform" ]]; then
  printf '  %s\n' "${R}FAIL: you asked for generation=platform and the new backend served ZERO${Z}"
  printf '  %s\n' "${R}reads. The app is NOT on the new backend, whatever it looks like.${Z}"
  printf '  %s\n' "${R}Check the log for OMI_GENERATION_REJECTED.${Z}"
elif [[ "$read_after" == "0" ]]; then
  printf '  %s\n' "${Y}Zero reads on the new backend - expected on the default legacy${Z}"
  printf '  %s\n' "${Y}generation. Re-run with --generation platform to put memories on the${Z}"
  printf '  %s\n' "${Y}new backend. Do not read a working app as proof the new stack is wired.${Z}"
else
  printf '  %s\n' "${G}The app read the NEW backend ${read_after} time(s) over GET /v1/memories.${Z}"
fi
echo
printf '  %s\n' "poke it:   curl -s $BACKEND_URL/qa/stats"
printf '  %s\n' "reseed:    curl -s '$BACKEND_URL/qa/reset?seed=12'"
printf '  %s\n' "logs:      $LOGDIR"
printf '  %s\n' "stop:      Ctrl-C  (or: integration/dev-stack.sh --stop)"
echo

while true; do sleep 3600; done
