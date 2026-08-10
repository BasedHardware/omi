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
#   *** CLOSED as of 2026-08-08. The gap this notice used to describe — the
#   *** ratified client existing while `surfaces/src/production/main.tsx` still
#   *** only called `createLegacyProductionStoreFactory` — is connected. With
#   *** `--generation platform`, BOTH apps read memories from 4851.
#   ***
#   *** Verified on a clean run of this script: the backend's own counter went
#   *** domainReadsServed 0 -> 4 for macOS and 4 -> 6 when iOS joined, and both apps
#   *** log `rendered=memories-platform ... mismatch=no`.
#   ***
#   *** Still trust the CROSS-CHECK, not this script's own summary. `rendered`
#   *** (what was constructed) is the honest field; `selected` (what was asked
#   *** for) has been honored-then-ignored before.
#
# ---------------------------------------------------------------------------
# USAGE — FOR A HUMAN
# ---------------------------------------------------------------------------
#   integration/dev-stack.sh                 # everything: backend + surfaces + macOS + iOS
#   integration/dev-stack.sh --only-backend  # just the new backend on 4851
#   integration/dev-stack.sh --only-macos    # backend + surfaces + macOS app
#   integration/dev-stack.sh --only-ios      # backend + surfaces + iOS simulator
#   integration/dev-stack.sh --no-ios        # skip iOS (fastest full desktop loop)
#   integration/dev-stack.sh --stop          # stop anything a previous run left behind
#   integration/dev-stack.sh --help
#
# ---------------------------------------------------------------------------
# USAGE — FOR AN AGENT
# ---------------------------------------------------------------------------
# The plain invocation above ends in `while true; do sleep 3600; done`. That is
# right for a human with a terminal and fatal for an agent, which blocks forever
# on a command that has already succeeded. These four flags exist so a program
# can drive this script:
#
#   --up            boot, report, leave the stack RUNNING, write a pidfile, exit 0.
#   --assert        evaluate the named assertions; exit nonzero if any fails.
#                   Alone it boots, asserts, tears down, and exits with the verdict.
#                   With --up it leaves the stack up. With --attach it boots nothing.
#   --attach        assert against a stack that is ALREADY running. Boots nothing,
#                   stops nothing. This is how you check a stack you did not start.
#   --json          emit one machine-readable object for the run on stdout.
#   --status        what is running RIGHT NOW (add --json). Boots nothing.
#   --doctor        recovery check: deps; surface stamp; named dependency build
#                   outputs; adapters-platform mtime; ports; branches.
#
# HEADLESS IS THE DEFAULT. Any automated shape (--up, --assert, --json, --attach,
# or any non-TTY caller) puts NO window on screen and never takes focus. Only a
# person typing the plain command at a terminal, or an explicit --headed, gets a
# window. This is a default and not a flag to remember, because an agent loop
# that steals focus every 90 seconds is not one anybody will keep running.
# Headless costs no evidence: bridge traffic, JS evaluation and
# WKWebView.takeSnapshot all work with no window. Only window-composited
# screenshots need --headed.
#
# The agent-shaped command is:
#   integration/dev-stack.sh --no-ios --generation platform --up --assert --json
#
# EVERY EMISSION CARRIES RUN IDENTITY — a run id, a timestamp, the git SHA and
# the working-tree hash of both repos. Without that, --json is just a stale log
# that parses. A run that died early once left the PREVIOUS run's `status=PASS`
# sitting in a file to be read as today's evidence; provenance is what makes that
# impossible rather than merely unlikely.
#
# WHAT THE ASSERTIONS ARE, AND WHAT THEY ARE NOT. Each names its arbiter as
# {claim, measuredBy, corroboratedBy}, and any claim resting on ONE measurement
# is labelled as such in the output. They assert INVARIANTS — the selection that
# was honored is the one that rendered; the traffic was served to THIS run; the
# artifacts were built from THIS tree; the window is alive. They deliberately do
# NOT assert rendered content or row counts: this system is still moving, and a
# brittle assertion costs more than it catches.
#
# RESET THE SEED DATA
#   curl 'http://127.0.0.1:4851/qa/reset?seed=12'          # 12 deterministic memories
#   curl 'http://127.0.0.1:4851/qa/reset?seed=7&hidden=2'  # + 2 hidden-but-present
#   ...or just re-run this script; it reseeds on every boot.
#   --seed N sets the initial memory count.
#
#   `hidden` is a COUNT, not a row id. Since the W4 rebuild the backend serves the
#   registered read composition, whose public item ids are reader-scoped opaque
#   refs (`mem1_...`) — there is no raw row id to name, which is the point: the
#   retired door published fixture row ids straight onto the wire.
#
# POINT AT A DIFFERENT BACKEND
#   OMI_BACKEND_URL=http://127.0.0.1:4811 integration/dev-stack.sh --no-ios
#   (4811 is BE-SURFACE's binding. This script will NOT boot its own backend
#    when OMI_BACKEND_URL names a port other than 4851 — it expects yours to be
#    up already, and fails loudly with that exact message if it is not.)
#
# IS TRAFFIC ACTUALLY FLOWING?
#   curl -s http://127.0.0.1:4851/v1/qa/status
#   -> {"version":"qa-status-v1","served":{...},"seed":{...}}
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
# THE WRITE JOURNEY
#   Every --assert run also drives the scripted write journey — create, applied,
#   idempotent replay, forced stale epoch, dead letter — against a live write
#   door, and judges it with the SERVER's own fence counter joined to this run's
#   id. See integration/lib/write-journey.mjs for what each step's two arbiters
#   are and why a dispatch-side number never appears in the verdict.
#
#   THE DOOR IS THE REGISTERED DEV APP — `createLocalDevService`, bound directly to
#   4851 by `integration/lib/write-journey-door.mjs`. Memories, task writes,
#   task reads, QA control and their counters are one composition, one process,
#   one token and one store. The old memories-only 4851 plus ephemeral task door
#   was a split-brain stack: both processes were real, but neither measurement
#   described the advertised stack as a whole.
#
#   WHETHER THE JOURNEY GATES L3 IS NOT A FLAG. `write-journey.mjs
#   --print-door-plan` answers it from platform's WIRE_PATH_REGISTRY: with no
#   `/v1/tasks/ops` row the journey is reported and not gated (charter R11);
#   with the row it gates. Nobody has to remember to switch it.
#
#   Its control state is SEEDED BY THIS HARNESS (charter R3): nothing in
#   platform mints control state by design, so the local stack drives
#   observe/activate for its dev account only. The production publisher is
#   legacy's and is untouched.
#
# PORTS IT USES     4851 registered backend + write door | 4852 surfaces |
#                   4747 legacy fake. Cross-side tests continue to use
#                   ephemeral sockets and remain safe beside this live stack.
#                   5290 macOS shell's own loopback (it serves its bundled dist)
# ============================================================================
set -uo pipefail

# ── Locations ───────────────────────────────────────────────────────────────
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# ── WHERE THE REPOS ARE — ASKED, NOT COMPUTED ───────────────────────────────
# This was `WORKSPACE="$CORE_REPO/.."`, which is true of the checkout at
# <workspace>/core-foundation and false of every lane worktree — where
# `bin/omi-lane` puts lanes and where swarm-protocol §3a REQUIRES them to work.
# From a worktree it resolved the workspace to the worktree ROOT, so
# `$WORKSPACE/platform` did not exist and this script died in preflight: L3 was
# unrunnable from the only place a lane is allowed to run it.
#
# That is the SAME defect §10 was written about after wave 2, in the same shape,
# in the one lane the launch-gate shakedown does not exercise (it runs L0/L1/L2).
# `lib/provenance.mjs` had already been fixed and this file had not, which is
# exactly why §10 also says: when you find a path-resolution defect in one file,
# grep the tree for the shape before declaring it fixed.
#
# So there is now ONE resolver. `--paths` honours OMI_CORE_ROOT /
# OMI_PLATFORM_ROOT, resolves core from `git --show-toplevel` and the workspace
# from `git --git-common-dir`, and this script asks it.
REPO_PATHS_JSON="$(node "$HERE/lib/provenance.mjs" --paths 2>/dev/null || true)"
read -r CORE_REPO PLATFORM_REPO WORKSPACE <<<"$(printf '%s' "$REPO_PATHS_JSON" | node -e '
  let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{
    try{const j=JSON.parse(s);console.log(`${j["core-foundation"]} ${j.platform} ${j.workspace}`)}catch{console.log("")}
  })')"
if [[ -z "${CORE_REPO:-}" || -z "${PLATFORM_REPO:-}" ]]; then
  printf '%s\n' "✗ could not resolve the repo paths from integration/lib/provenance.mjs" >&2
  printf '    %s\n' "Run it yourself to see why:  node $HERE/lib/provenance.mjs --paths" >&2
  printf '    %s\n' "Or declare them:  export OMI_CORE_ROOT=… OMI_PLATFORM_ROOT=…" >&2
  exit 1
fi
TRACKER="$WORKSPACE/omi-frontend-unification-and-microapps-project-tracker"
# The PROMOTED shell (FE-SHELLS, core/shells/). The tracker prototype is NOT
# equivalent: its bridge counts requests at DISPATCH, so it reports a healthy
# nonzero servedCount while every request fails and the backend serves nothing.
# The promoted shell keys acceptance on succeededCount and emits a traffic
# breakdown. Driving the prototype is what made my first served-read claim
# unreproducible. Override only if you know why.
MACOS_SHELL="${OMI_MACOS_SHELL:-$CORE_REPO/core/shells/macos}"
IOS_SHELL="$TRACKER/prototypes/flutter-webview"
LEGACY_FAKE="$TRACKER/prototypes/qa-api-server/server.mjs"
SURFACES="$CORE_REPO/core/packages/surfaces"
REGISTERED_DOOR_LAUNCHER="$HERE/lib/write-journey-door.mjs"

RUNDIR="${OMI_DEV_STACK_RUNDIR:-/tmp/omi-dev-stack}"
LOGDIR="$RUNDIR/logs"

BACKEND_PORT=4851
SURFACES_PORT=4852
LEGACY_PORT=4747
BACKEND_URL="${OMI_BACKEND_URL:-http://127.0.0.1:$BACKEND_PORT}"

# The write door announces its own token and owner account; nothing here
# guesses either. A launcher that assumed the credential it remembered is how a
# run measures a principal it does not have.
WRITE_TOKEN="${OMI_BACKEND_TOKEN:-}"
WRITE_ACCOUNT="${OMI_BACKEND_ACCOUNT:-}"
WRITE_JOURNEY_EPOCH="${OMI_WRITE_JOURNEY_EPOCH:-7}"

SEED="${OMI_SEED:-7}"
# Which backend generation the APP should use for memories.
#   legacy   -> the old wire on 4747 (default; what every domain uses today)
#   platform -> the NEW backend on 4851 over the settled /v1/memories route
GENERATION="${OMI_GENERATION:-legacy}"
WANT_BACKEND=1 WANT_SURFACES=1 WANT_MACOS=1 WANT_IOS=1
export TZ=UTC

# ── Run identity ────────────────────────────────────────────────────────────
# A per-run client id, threaded to the shells and sent as `x-omi-client-id` on
# every bridge request.
#
# WHY: the launcher used to prove traffic with a `domainReadsServed before -> after`
# DELTA on a global counter. That delta is satisfied by ANY client — a stray
# curl, the acceptance probe, another agent's stack on the same machine, the
# user's own window left open from an hour ago. The claim we actually want to
# make is "the app **I** launched read the backend N times", and a delta cannot
# express it. A client id turns an aggregate into a JOINABLE KEY: the backend
# reports `reads.served` from `/v1/qa/control/stats?run=<this id>`, and nobody
# else's traffic can satisfy it. The global delta is still reported, because it
# is useful context — it is just no longer allowed to be the evidence.
RUN_ID="run-$(date -u +%Y%m%dT%H%M%SZ)-$$"
RUN_CLIENT_ID="$RUN_ID"
RUN_STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
export OMI_RUN_CLIENT_ID="$RUN_CLIENT_ID"

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
STOP_ONLY=0 STATUS_ONLY=0 DOCTOR_ONLY=0
MODE_UP=0 MODE_ASSERT=0 MODE_ATTACH=0 EMIT_JSON=0
# ── --red-proof: deliberately break this run, and require --assert to notice ──
# core/AGENTS.md rule 14: an invariant guard carries the mutation that makes it
# fail, and the reviewer APPLIES that mutation before accepting the guard.
#
# These live here as a first-class flag rather than as something a person once
# did by hand, because the seventh failure of the night was inside the
# acceptance path itself. An assertion path never seen red is exactly the
# failure class this program exists to eliminate, and "I checked it once" is not
# a property of the system — it is a property of the afternoon.
#
#   legacy-branch  drop `route=memories`, keeping `generation=platform`. The
#                  REAL historical defect: nothing is rejected, the selection is
#                  honored, route falls back to home, home takes the legacy
#                  branch, and the app looks perfect on the wrong backend.
#                  Must turn `no_generation_mismatch` red.
#   stale-dist     doctor the surfaces dist stamp so it describes source that is
#                  not checked out — a bundle built from another tree.
#                  Must turn `stamps_agree` red.
#   dead-backend   kill the backend after the apps have been driven.
#                  Must turn `backend_reachable` red.
#
# Runner: integration/red-proof-assert.sh (runs all three, requires each red).
RED_PROOF=""
# ── Headless by default ─────────────────────────────────────────────────────
# Resolved after arg parsing. HEADED=-1 means "nobody said", which becomes
# headed ONLY for a plain interactive human invocation. Every automated shape —
# --up, --assert, --json, --attach, or any non-TTY caller — is headless, and it
# is the DEFAULT rather than a flag someone has to remember, because a loop that
# steals focus every 90 seconds is not a loop anyone will run.
HEADED=-1 HEADED_EXPLICIT=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h) sed -n '2,130p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    --stop) STOP_ONLY=1; shift ;;
    --status) STATUS_ONLY=1; shift ;;
    --doctor) DOCTOR_ONLY=1; shift ;;
    --up) MODE_UP=1; shift ;;
    --assert) MODE_ASSERT=1; shift ;;
    --attach) MODE_ATTACH=1; shift ;;
    --json) EMIT_JSON=1; shift ;;
    --red-proof) RED_PROOF="${2:?--red-proof needs legacy-branch|stale-dist|dead-backend}"; shift 2 ;;
    --headed) HEADED=1; shift ;;
    --headless) HEADED=0; HEADED_EXPLICIT=1; shift ;;
    --only-backend) WANT_SURFACES=0; WANT_MACOS=0; WANT_IOS=0; shift ;;
    --only-macos)   WANT_IOS=0; shift ;;
    --only-ios)     WANT_MACOS=0; shift ;;
    --no-ios)       WANT_IOS=0; shift ;;
    --seed) SEED="${2:?--seed needs a number}"; shift 2 ;;
    --generation) GENERATION="${2:?--generation needs legacy|platform}"; shift 2 ;;
    *) die "unknown option: $1  (try --help)" ;;
  esac
done

# In attach mode nothing is booted and nothing is torn down. Say it once here
# rather than guarding every site: this script must be safe to run against a
# stack somebody else owns, including the user's own live one.
if [[ $MODE_ATTACH -eq 1 ]]; then WANT_BACKEND=0; WANT_SURFACES=0; fi

# Resolve the display mode. An automated caller never gets a window unless it
# asked for one in so many words.
if [[ $HEADED -eq -1 ]]; then
  if [[ $MODE_UP -eq 1 || $MODE_ASSERT -eq 1 || $MODE_ATTACH -eq 1 || $EMIT_JSON -eq 1 || ! -t 1 ]]; then
    HEADED=0
  else
    HEADED=1   # a person, at a terminal, who typed the plain command
  fi
fi

mkdir -p "$RUNDIR" "$LOGDIR"
STATEFILE="$RUNDIR/state.json"
FACTSFILE="$RUNDIR/facts.$RUN_ID.json"
REPORTFILE="$RUNDIR/last-run.json"
WRITE_DOOR_FILE="$RUNDIR/write-door.json"

# ── doctor ──────────────────────────────────────────────────────────────────
# Deliberately standalone and disposable: it boots nothing, needs no state from
# a previous run, and answers the question an agent actually has when something
# is wrong — "what about my machine is not ready?" — with an action per finding.
# Worth more than another test lane, because the failures it catches (missing
# node_modules, stale named build outputs, the wrong branch) are the ones that
# make every other lane lie. `doctor.sh` checks the surfaces provenance stamp
# and adapters-platform's source/output mtime. The companion check covers the
# manifest-declared type outputs of the workspace packages surfaces resolves
# through; neither check claims freshness for unnamed artifacts.
if [[ $DOCTOR_ONLY -eq 1 ]]; then
  doctor_status=0
  dependency_dist_status=0
  "$HERE/doctor.sh" || doctor_status=$?
  node "$HERE/check-surfaces-dependency-dist.mjs" || dependency_dist_status=$?
  (( doctor_status == 0 && dependency_dist_status == 0 ))
  exit $?
fi

# ── --status ────────────────────────────────────────────────────────────────
# State DISCOVERY, not state recall. Every field is probed live; the pidfile is
# used only to name things, never to claim they are running. A status command
# that reports its own bookkeeping is how "window should be open now" got
# printed for a dead process.
if [[ $STATUS_ONLY -eq 1 ]]; then
  port_holder() { lsof -nP -tiTCP:"$1" -sTCP:LISTEN 2>/dev/null | head -1; }
  b_pid="$(port_holder "$BACKEND_PORT")"; s_pid="$(port_holder "$SURFACES_PORT")"
  l_pid="$(port_holder "$LEGACY_PORT")"
  m_port=""; m_pid=""
  for p in 5290 5291 5292 5293 5294 5295 5296 5297 5298 5299; do
    h="$(port_holder "$p")"
    if [[ -n "$h" ]] && [[ "$(ps -o comm= -p "$h" 2>/dev/null)" == *omi-* ]]; then m_port="$p"; m_pid="$h"; break; fi
  done
  b_stats="$(curl -fsS --max-time 2 "$BACKEND_URL/v1/qa/status" 2>/dev/null || echo '')"
  if [[ $EMIT_JSON -eq 1 ]]; then
    RUN_ID="$RUN_ID" BACKEND_URL="$BACKEND_URL" B_PID="$b_pid" S_PID="$s_pid" L_PID="$l_pid" \
    M_PID="$m_pid" M_PORT="$m_port" B_STATS="$b_stats" REPORTFILE="$REPORTFILE" \
    node -e '
      const e=process.env, fs=require("fs");
      const j=(s)=>{try{return JSON.parse(s)}catch{return null}};
      let last=null; try{last=JSON.parse(fs.readFileSync(e.REPORTFILE,"utf8"))}catch{}
      process.stdout.write(JSON.stringify({
        schema:1, queriedAt:new Date().toISOString(), queryRunId:e.RUN_ID,
        backend:{url:e.BACKEND_URL,listening:e.B_PID!=="",pid:e.B_PID||null,stats:j(e.B_STATS)},
        surfaces:{port:4852,listening:e.S_PID!=="",pid:e.S_PID||null},
        legacy:{port:4747,listening:e.L_PID!=="",pid:e.L_PID||null},
        macos:{port:e.M_PORT?Number(e.M_PORT):null,running:e.M_PID!=="",pid:e.M_PID||null},
        // The previous run, clearly labelled as the PREVIOUS run. Reported
        // because it is useful, quarantined because it is not evidence about
        // NOW: reading a stale PASS as todays result is the exact failure
        // this whole program exists to eliminate. (No apostrophe in that
        // sentence on purpose - this block is inside a single-quoted bash
        // string, and one apostrophe ends it. Ask how I know.)
        lastRun:last?{id:last.run?.id,finishedAt:last.run?.finishedAt,result:last.result,
                      note:"evidence about THAT run, not about the stack right now"}:null,
      },null,2)+"\n");'
  else
    printf '%s\n' "${B}stack status${Z}  (probed live, $(date -u +%H:%M:%SZ))"
    printf '  %-14s %s\n' "backend"  "$([[ -n $b_pid ]] && echo "up (pid $b_pid) $BACKEND_URL" || echo "down")"
    printf '  %-14s %s\n' "surfaces" "$([[ -n $s_pid ]] && echo "up (pid $s_pid) :$SURFACES_PORT" || echo "down")"
    printf '  %-14s %s\n' "legacy"   "$([[ -n $l_pid ]] && echo "up (pid $l_pid) :$LEGACY_PORT" || echo "down")"
    printf '  %-14s %s\n' "macOS app" "$([[ -n $m_pid ]] && echo "up (pid $m_pid) :$m_port" || echo "down")"
    [[ -n "$b_stats" ]] && printf '  %-14s %s\n' "counters" "$b_stats"
  fi
  trap - EXIT; exit 0
fi

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
    # Match the working directory too, not just argv. The legacy wire runs as a
    # bare `node server.mjs` — its argv contains nothing identifying — so this
    # refused to clean up a server THIS SCRIPT had started, leaking one process
    # per run and telling the user to go kill it by hand. The identifying
    # information is in the cwd.
    local cwd; cwd="$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -1)"
    if [[ "$cmd" == *"$want"* || "$cwd" == *"$want"* ]]; then
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

# The write-door record now describes the SAME 4851 process as the backend.
# The pidfile/backend sweep owns stopping it; this helper only removes the
# discovery record so a later --attach cannot inherit stale credentials.
stop_write_door() {
  rm -f "$WRITE_DOOR_FILE"
}

CLEANED=0
# --up and --attach both mean "this process exits but the stack does not". The
# EXIT trap must honor that, or `--up` would kill everything it just booted one
# microsecond after reporting it healthy — a self-inflicted instance of the
# pkill incident that made "window should be open now" a lie.
LEAVE_RUNNING=0
cleanup() {
  [[ $CLEANED -eq 1 ]] && return; CLEANED=1
  if [[ $LEAVE_RUNNING -eq 1 ]]; then
    say "leaving the stack running (pidfile: $PIDFILE). Stop it with: integration/dev-stack.sh --stop"
    return
  fi
  echo; say "shutting down..."
  stop_tracked
  ok "stack stopped. Logs kept in $LOGDIR"
}
trap cleanup EXIT INT TERM

if [[ $STOP_ONLY -eq 1 ]]; then
  stop_tracked
  free_port "$BACKEND_PORT" "integration/lib/write-journey-door.mjs"
  free_port "$SURFACES_PORT" "dev-stack-static"
  free_port "$LEGACY_PORT" "qa-api-server"
  stop_write_door
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
[[ -f "$PLATFORM_REPO/apps/service/app-facing.ts" ]] || fixit \
  "registered composition missing: $PLATFORM_REPO/apps/service/app-facing.ts" \
  "Your platform checkout is on the wrong branch." \
  "  cd $PLATFORM_REPO && git checkout codex/track3-backend-integration"
[[ -f "$REGISTERED_DOOR_LAUNCHER" ]] || fixit \
  "registered-door launcher missing: $REGISTERED_DOOR_LAUNCHER" \
  "Restore the integration files from this core-foundation lane."

if [[ $WANT_MACOS -eq 1 ]]; then
  need swiftc "Install Xcode command line tools:  xcode-select --install"
  [[ -x "$MACOS_SHELL/scripts/run-shell.sh" ]] || { warn "macOS shell prototype not found at $MACOS_SHELL — skipping macOS"; WANT_MACOS=0; }
fi
if [[ $WANT_IOS -eq 1 ]]; then
  # Pick the Flutter whose Dart can actually resolve the app's pubspec, not
  # whatever `flutter` happens to mean on PATH. The default here is 3.41.9
  # (Dart 3.11.5); the app declares `sdk: ^3.12.2` and fails version solving with
  # "Failed to update packages", which reads like a network error and is not one.
  # Prefer the newest mise-installed Flutter, fall back to PATH.
  FLUTTER_BIN="$(command -v flutter 2>/dev/null || true)"
  newest_flutter="$(ls -d "$HOME/.local/share/mise/installs/flutter"/[0-9]*.[0-9]*.[0-9]* 2>/dev/null \
    | sort -t. -k1,1n -k2,2n -k3,3n | tail -1)"
  if [[ -n "$newest_flutter" && -x "$newest_flutter/bin/flutter" ]]; then
    FLUTTER_BIN="$newest_flutter/bin/flutter"
  fi
  if ! command -v xcrun >/dev/null 2>&1; then warn "xcrun missing — skipping iOS"; WANT_IOS=0;
  elif [[ -z "$FLUTTER_BIN" ]]; then warn "flutter missing — skipping iOS (install: mise use flutter)"; WANT_IOS=0;
  elif [[ ! -d "$IOS_SHELL/app" ]]; then warn "iOS shell prototype not found at $IOS_SHELL — skipping iOS"; WANT_IOS=0; fi
fi
ok "tools present"

# Both the surfaces typecheck and the backend-only write journey resolve core
# workspace packages through their declared dist entrypoints. Installing only
# repairs node_modules; it says nothing about those ignored build outputs. Build
# the workspace before either consumer can run. This
# replaces late TS2305/ERR_MODULE_NOT_FOUND failures with an early named build
# failure and a log, rather than with an assertion that guessed at freshness.
if [[ $MODE_ATTACH -eq 0 ]]; then
  say "${B}core workspace${Z} — building local-stack packages"
  ( cd "$CORE_REPO/core" \
      && pnpm install --config.confirmModulesPurge=false --silent \
      && node "$HERE/check-surfaces-dependency-dist.mjs" --prepare-build \
      && pnpm -r build ) \
    > "$LOGDIR/core-workspace-build.log" 2>&1 \
    || fixit "core workspace build failed" \
      "Log: $LOGDIR/core-workspace-build.log" \
      "$(tail -15 "$LOGDIR/core-workspace-build.log")"
  ok "core workspace built"
fi

# Clear our own leftovers before binding anything — but NEVER in attach mode,
# where the entire contract is "measure what is already there". An attach that
# sweeps ports first would destroy the thing it was asked to inspect and then
# report on the wreckage.
if [[ $MODE_ATTACH -eq 0 ]]; then
  stop_tracked
  free_port "$BACKEND_PORT" "integration/lib/write-journey-door.mjs"
  free_port "$SURFACES_PORT" "dev-stack-static"
  stop_write_door
fi

# ── 1. New backend (4851) ───────────────────────────────────────────────────
BACKEND_OWNED=0
if [[ $MODE_ATTACH -eq 1 ]]; then
  say "${B}backend${Z} — attach mode: measuring the stack that is already up at $BACKEND_URL"
  curl -fsS --max-time 3 "$BACKEND_URL/v1/qa/status" >/dev/null 2>&1 || fixit \
    "attach mode, but nothing is answering at $BACKEND_URL/v1/qa/status" \
    "Attach asserts against a RUNNING stack; it boots nothing on purpose." \
    "Bring one up first:  integration/dev-stack.sh --no-ios --generation platform --up" \
    "Or see what is running:  integration/dev-stack.sh --status"
  ok "attached to $BACKEND_URL"
elif [[ "$BACKEND_URL" != "http://127.0.0.1:$BACKEND_PORT" ]]; then
  say "${B}backend${Z} — using external $BACKEND_URL (not booting our own)"
  curl -fsS --max-time 3 "$BACKEND_URL/health" >/dev/null 2>&1 || fixit \
    "no backend answering at $BACKEND_URL/health" \
    "You set OMI_BACKEND_URL, so this script did not boot one." \
    "Start that backend first, or unset OMI_BACKEND_URL to use the built-in one on $BACKEND_PORT."
  ok "external backend reachable at $BACKEND_URL"
elif [[ $WANT_BACKEND -eq 1 ]]; then
  say "${B}backend${Z} — booting the registered composition on $BACKEND_PORT (TZ=UTC, seed=$SEED)"
  # Direct `exec bun <file>`, not `bun run`: `bun run` leaves the listener in a
  # child process, so the pidfile owns the runner rather than the socket and
  # --stop kills the wrong PID.
  ( cd "$PLATFORM_REPO" && TZ=UTC exec bun "$REGISTERED_DOOR_LAUNCHER" \
      --platform-repo "$PLATFORM_REPO" --port "$BACKEND_PORT" --seed "$SEED" ) \
      > "$LOGDIR/backend.log" 2>&1 &
  BACKEND_RUNNER_PID=$!
  track backend-runner "$BACKEND_RUNNER_PID"
  BACKEND_OWNED=1
  for i in $(seq 1 40); do
    curl -fsS --max-time 1 "$BACKEND_URL/health" >/dev/null 2>&1 && break
    sleep 0.25
    [[ $i -eq 40 ]] && fixit "backend never became ready on $BACKEND_PORT" \
      "Log: $LOGDIR/backend.log" "$(tail -5 "$LOGDIR/backend.log" 2>/dev/null || echo '(no log)')"
  done
  read -r announced_url WRITE_TOKEN WRITE_ACCOUNT BACKEND_LISTENER_PID <<<"$(node -e '
    const fs=require("fs");
    let line=null;
    try { line=fs.readFileSync(process.argv[1],"utf8").split("\n").find((l)=>l.includes("registered_door_listening")); } catch {}
    if(!line){console.log("");process.exit(0)}
    try{const j=JSON.parse(line);console.log(`${j.url} ${j.devToken} ${j.ownerAccountId} ${j.pid}`)}catch{console.log("")}
  ' "$LOGDIR/backend.log" 2>/dev/null || echo "")"
  [[ "$announced_url" == "$BACKEND_URL" && -n "$WRITE_TOKEN" && -n "$WRITE_ACCOUNT" \
      && "$BACKEND_LISTENER_PID" =~ ^[0-9]+$ ]] || fixit \
    "registered backend became healthy but did not announce its own URL, token and account" \
    "Log: $LOGDIR/backend.log" \
    "This is a loud boot failure replacing the old silent two-door split."
  if [[ "$BACKEND_LISTENER_PID" != "$BACKEND_RUNNER_PID" ]]; then
    track backend-listener "$BACKEND_LISTENER_PID"
  fi
  ok "registered backend live at $BACKEND_URL  (seeded $SEED memories; tasks read + ops on the same door)"
fi

if [[ $WANT_BACKEND -eq 1 || "$BACKEND_URL" != "http://127.0.0.1:$BACKEND_PORT" ]]; then
  [[ -n "$WRITE_TOKEN" ]] && echo "    dev token:  ${B}$WRITE_TOKEN${Z}   (QA only, loopback only)"
  echo "    try it:     curl -s '$BACKEND_URL/v1/qa/status'"
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

# ── 1b. The write door, and the scripted write journey ──────────────────────
# THE DOOR IS THE REGISTERED APP, and there is now only one of it.
#
# Until OPS landed `apps/service/routes/tasks-ops.ts` this booted
# `integration/control/fence-server.ts` — a harness that stood up its own
# Bun.serve, answered the same `/v1/tasks/ops`, and returned
# `202 {"fence":"admitted"}` where the real route returns
# `200 {applied, idempotent}`. Two doors, diverged at the byte level. R5
# pre-ruled that it could not survive the registered route and OPS retired it;
# fable's R14 quarantines every measurement taken against it while both stood.
#
# `integration/lib/write-journey-door.mjs` is process glue, not a replacement
# composition: it constructs no route, handler or store of its own. It imports
# `createLocalDevService` — the dev-shaped app used by the dev server and route
# tests, with deterministic scripted adapters supplied explicitly by that
# factory. The production-shaped `createLocalService` deliberately refuses
# missing adapters. The launcher binds the dev composition directly to 4851.
# The URL, dev token and owner are
# read from its one-line JSON announcement; nothing here guesses them.
#
# R34 removes the separate-process exception: the journey must read the
# counters and store owned by the exact 4851 process that serves memories and
# the final /v1/tasks probe. A missing token/account is therefore a loud
# preflight failure; booting an ephemeral substitute would recreate the defect.
JOURNEY_FILE=""
JOURNEY_STATUS=""
WRITE_DOOR_URL=""
DOOR_PLAN="$(node "$HERE/lib/write-journey.mjs" --print-door-plan --platform-repo "$PLATFORM_REPO" 2>/dev/null || echo '')"
DOOR_STAGE="$(printf '%s' "$DOOR_PLAN" | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{try{console.log(JSON.parse(s).stage)}catch{console.log("")}})')"

if [[ $MODE_ATTACH -eq 1 ]]; then
  # Attach never boots. Reuse the door the run that owns this stack recorded.
  if [[ -f "$WRITE_DOOR_FILE" ]]; then
    read -r WRITE_DOOR_URL WRITE_TOKEN WRITE_ACCOUNT <<<"$(node -e '
      const j=JSON.parse(require("fs").readFileSync(process.argv[1],"utf8"));
      console.log(`${j.url} ${j.devToken} ${j.ownerAccountId}`);' "$WRITE_DOOR_FILE" 2>/dev/null || echo "")"
    if [[ "$WRITE_DOOR_URL" == "$BACKEND_URL" ]]; then
      say "${B}write door${Z} — attach mode: reusing the registered backend door at $WRITE_DOOR_URL"
    else
      WRITE_DOOR_URL="" WRITE_TOKEN="" WRITE_ACCOUNT=""
    fi
  fi
  [[ -z "$WRITE_DOOR_URL" ]] && warn "attach mode: no write door recorded by the run that booted this stack — the journey will not run"
else
  WRITE_DOOR_URL="$BACKEND_URL"
  if [[ -n "$WRITE_TOKEN" && -n "$WRITE_ACCOUNT" ]]; then
    # Remember the announced identity so --attach can reuse this exact door.
    WRITE_DOOR_URL="$WRITE_DOOR_URL" WRITE_TOKEN="$WRITE_TOKEN" WRITE_ACCOUNT="$WRITE_ACCOUNT" \
      WRITE_DOOR_FILE="$WRITE_DOOR_FILE" node -e '
        const e=process.env;
        require("fs").writeFileSync(e.WRITE_DOOR_FILE, JSON.stringify({
          url:e.WRITE_DOOR_URL, devToken:e.WRITE_TOKEN, ownerAccountId:e.WRITE_ACCOUNT,
          port:Number(new URL(e.WRITE_DOOR_URL).port), wroteAt:new Date().toISOString(),
        }, null, 2));'
    ok "write door is the registered backend at $WRITE_DOOR_URL  (owner $WRITE_ACCOUNT)"
  else
    fixit "the registered backend supplied no door token/account; refusing to boot a substitute" \
      "For an external backend, set OMI_BACKEND_TOKEN and OMI_BACKEND_ACCOUNT." \
      "For the built-in backend, inspect $LOGDIR/backend.log."
  fi
fi

if [[ -n "$WRITE_DOOR_URL" ]]; then
  JOURNEY_FILE="$RUNDIR/write-journey.$RUN_ID.json"
  # NOT piped. `cmd | tail` hands back tail's status, and that has already
  # produced one false "the assertion path is broken" report in this repo.
  node "$HERE/lib/write-journey.mjs" \
    --door "$WRITE_DOOR_URL" --control "$WRITE_DOOR_URL" \
    --token "$WRITE_TOKEN" --account "$WRITE_ACCOUNT" \
    --run "$RUN_ID" --epoch "$WRITE_JOURNEY_EPOCH" \
    --platform-repo "$PLATFORM_REPO" \
    ${WRITE_JOURNEY_EXTRA:-} \
    --out "$JOURNEY_FILE" > "$LOGDIR/write-journey.log" 2>&1
  JOURNEY_STATUS=$?
  if [[ $JOURNEY_STATUS -eq 0 ]]; then
    ok "write journey completed (stage ${DOOR_STAGE:-?}) — verdict in the run report below (raw: $JOURNEY_FILE)"
  else
    warn "write journey FAILED (exit $JOURNEY_STATUS) — see $LOGDIR/write-journey.log"
  fi
fi

if [[ $WANT_SURFACES -eq 0 && $WANT_MACOS -eq 0 && $WANT_IOS -eq 0 ]]; then
  echo
  [[ -n "$JOURNEY_FILE" && -f "$JOURNEY_FILE" ]] \
    && node "$HERE/lib/write-journey.mjs" --format "$JOURNEY_FILE"
  if [[ $MODE_UP -eq 1 ]]; then
    LEAVE_RUNNING=1
    ok "backend only, left running. Stop it with: integration/dev-stack.sh --stop"
    exit ${JOURNEY_STATUS:-0}
  fi
  # `--only-backend --assert` used to fall through to `sleep 3600` — an
  # automated caller asking for a verdict got a hang instead, which is the same
  # class of trap `--up` and `--assert` were added to remove. It now returns the
  # only verdict a backend-only run can honestly produce: the write journey's.
  # No app was driven, so nothing here claims the app works.
  if [[ $MODE_ASSERT -eq 1 ]]; then
    [[ -z "$JOURNEY_FILE" ]] && warn "backend only, --assert, and no write journey ran: this run asserted NOTHING"
    exit ${JOURNEY_STATUS:-1}
  fi
  ok "backend only. Ctrl-C to stop."
  while true; do sleep 3600; done
fi

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
if [[ $MODE_ATTACH -eq 1 ]]; then
  say "${B}surfaces${Z} — attach mode: not building, not serving"
  curl -fsS --max-time 2 "http://127.0.0.1:$SURFACES_PORT/" >/dev/null 2>&1 \
    && ok "surfaces already served at http://127.0.0.1:$SURFACES_PORT/" \
    || warn "nothing serving surfaces on $SURFACES_PORT (attach mode does not start one)"
else
say "${B}surfaces${Z} — using bundle from the core workspace build"
[[ -f "$SURFACES/dist/index.html" ]] || fixit "workspace build produced no surfaces dist/index.html" \
  "Log: $LOGDIR/core-workspace-build.log"
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
if [[ "$RED_PROOF" == "stale-dist" ]]; then
  # Doctor the EVIDENCE CHANNEL, not the bundle: a well-formed stamp describing
  # source that is not checked out is exactly what a dist built an hour and three
  # commits ago looks like. Rebuilding from an older commit would prove the same
  # thing far more slowly.
  warn "RED-PROOF stale-dist: rewriting the surfaces build stamp to describe a tree that is not checked out."
  node -e '
    const fs=require("fs"), p=process.argv[1];
    const s=JSON.parse(fs.readFileSync(p,"utf8"));
    s.treeHash="0".repeat(40);
    fs.writeFileSync(p, JSON.stringify(s,null,2)+"\n");
  ' "$SURFACES/dist/omi-build-stamp.json"
fi
ok "surfaces at http://127.0.0.1:$SURFACES_PORT/ — $(node "$HERE/lib/provenance.mjs" --repo core-foundation --artifact surfaces-dist 2>/dev/null | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{try{const j=JSON.parse(s);console.log(`built from ${j.commit.slice(0,12)}/tree:${j.treeHash.slice(0,12)}${j.dirty?"+dirty":""}`)}catch{console.log("provenance unavailable")}})')"
fi

# ── 4. Shell configuration, shared by BOTH apps ─────────────────────────────
STATS_BEFORE="$(curl -s "$BACKEND_URL/v1/qa/status" 2>/dev/null || echo '{}')"

# Set OUTSIDE the macOS block on purpose: iOS consumes the same three values as
# --dart-defines. While this lived inside `if [[ $WANT_MACOS -eq 1 ]]`, running
# --only-ios silently produced an iOS app with no API base URL and no route — a
# bridge-disabled app that boots, looks fine, and reads nothing.
#
# WITHOUT OMI_API_BASE_URL a shell registers no HTTP handler at all and the
# surface truthfully renders "bridge unavailable" — it looks broken and serves
# zero requests.
if [[ "$GENERATION" == "platform" ]]; then
  # The app's memories surface reads the NEW backend over GET /v1/memories.
  export OMI_API_BASE_URL="$BACKEND_URL"
  # The registered composition announces one token for memories, task ops and
  # task reads. Keeping the retired memories-harness token here would recreate
  # the two-door split as two credentials even after the processes were joined.
  export OMI_API_TOKEN="$WRITE_TOKEN"
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

# ── 4a. macOS app ───────────────────────────────────────────────────────────
MACOS_PID_ALIVE=0 MACOS_SURFACE_ANSWERS=0 SHELL_PID="" SHELL_PORT="" ACCEPT_RUNLOG=""
if [[ $WANT_MACOS -eq 1 && $MODE_ATTACH -eq 1 ]]; then
  # Attach mode cannot re-drive the app — relaunching it would be booting, which
  # attach exists not to do. So it reports on the run that DID launch it, and
  # says so. The alternative (silently reusing this run's fresh client id against
  # an app that never saw it) would manufacture a zero and call the stack broken.
  say "${B}macOS app${Z} — attach mode: reading the run that launched it"
  if [[ -f "$STATEFILE" ]]; then
    RUN_CLIENT_ID="$(node -e 'try{console.log(JSON.parse(require("fs").readFileSync(process.argv[1],"utf8")).clientId||"")}catch{console.log("")}' "$STATEFILE")"
    SHELL_PORT="$(node -e 'try{console.log(JSON.parse(require("fs").readFileSync(process.argv[1],"utf8")).macosPort||"")}catch{console.log("")}' "$STATEFILE")"
    # The PRESERVED copy, not the live run log. The live one belongs to the
    # windowed app and was truncated at its launch; the acceptance evidence for
    # the run that booted this stack is the copy the booting run saved.
    ACCEPT_RUNLOG="$LOGDIR/macos-acceptance.runlog"
    [[ -n "$SHELL_PORT" ]] && curl --fail --silent --max-time 2 "http://127.0.0.1:$SHELL_PORT/" >/dev/null 2>&1 && MACOS_SURFACE_ANSWERS=1
    SHELL_PID="$(lsof -nP -tiTCP:"${SHELL_PORT:-0}" -sTCP:LISTEN 2>/dev/null | head -1)"
    [[ -n "$SHELL_PID" ]] && MACOS_PID_ALIVE=1
    ok "attached to run ${RUN_CLIENT_ID:-unknown} (macOS on port ${SHELL_PORT:-unknown})"
  else
    warn "no state file at $STATEFILE — cannot join traffic to the run that launched this stack."
    warn "   Per-client read counting will be reported as UNJOINABLE rather than as zero."
    RUN_CLIENT_ID=""
  fi
elif [[ $WANT_MACOS -eq 1 ]]; then
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
  # ORDER MATTERS, and it is not stylistic. Acceptance runs FIRST because it is
  # a self-terminating probe that shares one build dir with the windowed app:
  # running it second meant rebuilding the .app binary underneath a live process
  # and (before the fix in run-shell.sh) killing that process outright. Probe,
  # let it exit, then bring up the window that stays.

  # BRIDGE ACCEPTANCE. A separate, headless run of the same app that exits with
  # its own verdict. The app reports a HOST-OBSERVED served count and passes
  # only when it is nonzero: probes prove nothing, and a stalled bridge is
  # indistinguishable from offline. We propagate the CHILD's exit status —
  # waiting only for HTTP readiness would report success while this failed.
  ACCEPT_PORT=$((SHELL_PORT + 3))
  # The acceptance probe is headless ALWAYS, even in a headed run. It is
  # automation by definition, it is never the window a human QAs, and it used to
  # put a second window on screen and steal focus from the first.
  say "${B}macOS bridge acceptance${Z} — headless run on $ACCEPT_PORT, asserts nonzero served traffic"
  # OMI_PROBE_JS reads __OMI_RUNTIME_STATE__ out of the LIVE webview and prints it
  # on a PROBE_JS line. This is the independent measurement of what the app
  # actually did: `rendered` is what was constructed, `selected` is only what was
  # asked for, and the night's headline defect was a selection that was honored
  # and then never used. Reusing the shell's existing probe seam rather than
  # adding a channel — a second channel is a second thing that silently stops
  # working, and nobody notices because its absence looks like a pass.
  ( cd "$MACOS_SHELL" && OMI_BUILD_DIR="$MACOS_SHELL/.build/on-integration" \
      OMI_APP_NAME="omi-on-integration" OMI_SURFACES_DIST="$SURFACES/dist" \
      OMI_SURFACE_PORT="$ACCEPT_PORT" OMI_ACCEPTANCE_EXIT=1 TZ=UTC OMI_HEADED=0 \
      OMI_PROBE_JS='JSON.stringify(globalThis.__OMI_RUNTIME_STATE__ ?? null)' \
      OMI_PROBE_DELAY="${OMI_PROBE_DELAY:-2}" OMI_PROBE_SETTLE="${OMI_PROBE_SETTLE:-1}" \
      ./scripts/run-shell.sh ) > "$LOGDIR/macos-acceptance.log" 2>&1
  accept_status=$?
  # PRESERVE THE ACCEPTANCE LOG IMMEDIATELY, under a name only this run uses.
  #
  # The windowed launch below runs the same app from the same build dir, and
  # run-shell.sh truncates `<app_name>.run.log` in its preamble (correctly — a
  # stale log read as today's evidence is what it was fixed for). So the
  # acceptance probe's ACCEPTANCE and PROBE_JS lines are DESTROYED by the launch
  # that follows, and the report read an empty file.
  #
  # This was caught by the assertions not firing, not by reading the code: the
  # first green L3 reported PASS with `no_generation_mismatch` silently absent
  # and the shell's success count shown as "n/a". A run whose evidence is deleted
  # by the next step of the same run is precisely "the artifact measured is not
  # the artifact produced" — inside the harness built to catch it.
  ACCEPT_RUNLOG="$LOGDIR/macos-acceptance.runlog"
  cp "$MACOS_SHELL/.build/on-integration/omi-on-integration.run.log" "$ACCEPT_RUNLOG" 2>/dev/null || true
  accept_line="$(grep -o 'ACCEPTANCE .*' "$ACCEPT_RUNLOG" 2>/dev/null | tail -1)"
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

  # THE WINDOW YOU ACTUALLY QA WITH. Launched last so nothing that follows can
  # rebuild or kill it.
  if [[ $HEADED -eq 1 ]]; then
    say "${B}macOS app${Z} — building and launching a VISIBLE window on $SHELL_PORT (bundles the dist you just built)"
  else
    say "${B}macOS app${Z} — building and launching HEADLESS on $SHELL_PORT (no window; --headed to show one)"
  fi
  ( cd "$MACOS_SHELL" && OMI_BUILD_DIR="$MACOS_SHELL/.build/on-integration" \
      OMI_APP_NAME="omi-on-integration" OMI_SURFACES_DIST="$SURFACES/dist" \
      OMI_SURFACE_PORT="$SHELL_PORT" TZ=UTC OMI_HEADED="$HEADED" \
      ./scripts/run-shell.sh ) > "$LOGDIR/macos.log" 2>&1
  shell_launch_status=$?
  # "Launched successfully" and "there is a window in front of you" are different
  # claims, and this script used to print the second while only checking the
  # first. It reported "window should be open now" for a process that had already
  # been killed. So re-verify independently: the pid the launcher recorded must
  # still be alive AND its loopback must still answer. Both, because a live
  # process with a dead surface is just as useless to QA as no process.
  SHELL_PID="$(sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p' "$LOGDIR/macos.log" | tail -1)"
  if [[ $shell_launch_status -ne 0 ]]; then
    warn "macOS shell failed to launch — see $LOGDIR/macos.log"
    tail -8 "$LOGDIR/macos.log" | sed 's/^/    /'
  elif [[ -z "$SHELL_PID" ]] || ! kill -0 "$SHELL_PID" 2>/dev/null; then
    warn "macOS shell exited right after launch (pid ${SHELL_PID:-unknown} is gone) — there is NO window to QA."
    echo "    log: $LOGDIR/macos.log"
  elif ! curl --fail --silent --max-time 2 "http://127.0.0.1:$SHELL_PORT/" >/dev/null 2>&1; then
    warn "macOS shell pid $SHELL_PID is alive but its surface on $SHELL_PORT does not answer."
    echo "    log: $LOGDIR/macos.log"
  else
    track macos "$SHELL_PID"
    MACOS_PID_ALIVE=1 MACOS_SURFACE_ANSWERS=1
    ok "macOS app running — pid $SHELL_PID, surface answering at http://127.0.0.1:$SHELL_PORT/"
    if [[ $HEADED -eq 1 ]]; then
      echo "    the window is open now (verified: process alive + surface responded)"
    else
      # Say what is true. "Running headless" and "there is a window" are exactly
      # the pair of claims this script has already been caught conflating once.
      echo "    running headless — there is NO window on screen (this is the default)"
      echo "    to look at it:  integration/dev-stack.sh --no-ios --generation platform --headed"
    fi
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
    # The iOS shell takes ALL of its configuration as COMPILE-TIME --dart-defines.
    # Passing none — which is what this did — is why the documented caveat said
    # "iOS renders the prototype probe page, not the product UI". It was never a
    # routing bug in the app: with no defines it falls back to SURFACE_MODE=ship,
    # loads from a file: origin, and logs "[bridge-http] disabled". The app could
    # do the real thing the whole time; nobody was asking it to.
    #
    #   SURFACE_MODE=scheme  mounts the bundle at the frozen omi-ui://local origin
    #                        (ADR-009 — IndexedDB is origin-keyed, so this must not
    #                        drift), instead of a file: URL.
    #   SCHEME_BUNDLE=surfaces  the real @omi-core/surfaces build, not probe v1.
    #   OMI_API_*            the shell's privileged HTTP custody. Never handed to
    #                        the webview; the token stays on the Dart side.
    #
    # --debug, not --release: release mode is unsupported for this simulator
    # target (iPhone 17 Pro / arm64 sim) and dies partway through the build.
    ios_defines=(
      --dart-define=SURFACE_MODE=scheme
      --dart-define=SCHEME_BUNDLE=surfaces
      --dart-define=OMI_API_BASE_URL="$OMI_API_BASE_URL"
      --dart-define=OMI_API_TOKEN="$OMI_API_TOKEN"
    )
    # Same reasoning as the macOS shell: generation alone leaves route=home, which
    # takes the legacy branch. Both, or neither.
    [[ -n "${OMI_SURFACE_QUERY:-}" ]] && ios_defines+=( --dart-define=SURFACE_QUERY="$OMI_SURFACE_QUERY" )
    ( cd "$IOS_SHELL/app" && TZ=UTC "$FLUTTER_BIN" run -d "$UDID" --debug "${ios_defines[@]}" ) > "$LOGDIR/ios.log" 2>&1 &
    track ios $!
    say "iOS build started in background (cold builds take ~100s) using $("$FLUTTER_BIN" --version 2>/dev/null | head -1 | cut -d' ' -f1-2). Log: $LOGDIR/ios.log"
  fi
fi

# ── 6. Did anything actually flow? ──────────────────────────────────────────
sleep 3
STATS_AFTER="$(curl -s "$BACKEND_URL/v1/qa/status" 2>/dev/null || echo '{}')"
RUN_STATS_AFTER="$(curl -sG --data-urlencode "run=$RUN_CLIENT_ID" "$BACKEND_URL/v1/qa/control/stats" 2>/dev/null || echo '{}')"
read_before="$(echo "$STATS_BEFORE" | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{try{console.log(JSON.parse(s).served?.domainReadsServed??0)}catch{console.log(0)}})')"
read_after="$(echo "$STATS_AFTER" | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{try{console.log(JSON.parse(s).served?.domainReadsServed??0)}catch{console.log(0)}})')"

echo
printf '%s\n' "${B}══════════════════ stack up ══════════════════${Z}"
printf '  %-22s %s\n' "new backend"  "$BACKEND_URL   (memories read path, ratified 0.1.1)"
printf '  %-22s %s\n' "legacy wire"  "http://127.0.0.1:$LEGACY_PORT   (tasks, conversations, folders)"
printf '  %-22s %s\n' "surfaces"     "http://127.0.0.1:$SURFACES_PORT/"
[[ $WANT_MACOS -eq 1 ]] && printf "  %-22s %s\n" "macOS app" "http://127.0.0.1:${SHELL_PORT:-5290}/  (app window)"
[[ $WANT_IOS  -eq 1 ]] && printf '  %-22s %s\n' "iOS app" "simulator ${UDID:-none}"
echo
printf '  %s\n' "${B}served by the NEW backend:${Z} domainReadsServed ${read_before} -> ${read_after}"
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
printf '  %s\n' "status:    curl -s $BACKEND_URL/v1/qa/status"
printf '  %s\n' "this run:  curl -sG --data-urlencode 'run=$RUN_CLIENT_ID' '$BACKEND_URL/v1/qa/control/stats'"
printf '  %s\n' "reset:     curl -s -X POST -H 'Authorization: Bearer $WRITE_TOKEN' '$BACKEND_URL/v1/qa/reset'"
printf '  %s\n' "logs:      $LOGDIR"
printf '  %s\n' "stop:      Ctrl-C  (or: integration/dev-stack.sh --stop)"
echo

if [[ "$RED_PROOF" == "dead-backend" ]]; then
  warn "RED-PROOF dead-backend: killing the backend now that the apps have been driven."
  free_port "$BACKEND_PORT" "integration/lib/write-journey-door.mjs"
  STATS_AFTER="$(curl -s --max-time 2 "$BACKEND_URL/v1/qa/status" 2>/dev/null || echo '')"
  RUN_STATS_AFTER="$(curl -sG --max-time 2 --data-urlencode "run=$RUN_CLIENT_ID" "$BACKEND_URL/v1/qa/control/stats" 2>/dev/null || echo '')"
fi

# ── 7. The run report ───────────────────────────────────────────────────────
# Everything above prints FACTS as it goes. This step turns them into a single
# object with run identity attached, evaluates the named assertions, and is the
# only thing allowed to say "pass".
#
# The facts are written to a file and handed to node rather than assembled by
# string-concatenation in bash, because the one thing this program cannot afford
# is a report that is subtly about a different run than the one that produced it.
# A file named for THIS run id cannot be confused with the last one.
[[ -n "$SHELL_PID" ]] && kill -0 "$SHELL_PID" 2>/dev/null && MACOS_PID_ALIVE=1 || true

MACOS_FACTS=null
# WINDOWED: in attach mode the window is still a fair question — we just did not
# open it. Ask it whenever we know which port it should be on; staying silent
# would be another assertion that quietly opts out instead of reporting that it
# cannot measure.
#
# This comment lives HERE, above the command, and not inside the backslash
# continuation below, because a `#` line in the middle of a continuation chain
# silently swallows the rest of the command: bash joined the continuation to the
# comment, the env assignments after it never applied, and `node` ran without
# ACCEPT_RUNLOG or SHELL_PID. Two assertions went red with "pid unknown" and "no
# PROBE_JS line" while the stack was perfectly healthy — a real bug found by the
# assertions rather than by reading the diff, which is the entire point.
WINDOWED_FACT="$([[ $MODE_ATTACH -eq 1 && -z "${SHELL_PORT:-}" ]] && echo 0 || echo 1)"
if [[ $WANT_MACOS -eq 1 ]]; then
  MACOS_FACTS="$(ACCEPT_RUNLOG="${ACCEPT_RUNLOG:-}" SHELL_PORT="${SHELL_PORT:-}" SHELL_PID="${SHELL_PID:-}" \
    PID_ALIVE="$MACOS_PID_ALIVE" SURFACE_ANSWERS="$MACOS_SURFACE_ANSWERS" \
    LAUNCH_STATUS="${shell_launch_status:-}" BUILD_DIR="$MACOS_SHELL/.build/on-integration" \
    WINDOWED="$WINDOWED_FACT" \
    node -e '
      const fs=require("fs"), e=process.env;
      let log=""; try{ log=fs.readFileSync(e.ACCEPT_RUNLOG,"utf8") }catch{}
      process.stdout.write(JSON.stringify({
        port:e.SHELL_PORT?Number(e.SHELL_PORT):null, pid:e.SHELL_PID||null,
        windowed:e.WINDOWED==="1", pidAlive:e.PID_ALIVE==="1", surfaceAnswers:e.SURFACE_ANSWERS==="1",
        launchStatus:e.LAUNCH_STATUS===""?null:Number(e.LAUNCH_STATUS),
        acceptanceLog:log, buildDir:e.BUILD_DIR, appName:"omi-on-integration",
      }));')"
fi

RUN_ID="$RUN_ID" STARTED_AT="$RUN_STARTED_AT" CLIENT_ID="$RUN_CLIENT_ID" GENERATION="$GENERATION" \
BACKEND_URL="$BACKEND_URL" STATS_BEFORE="$STATS_BEFORE" STATS_AFTER="$STATS_AFTER" RUN_STATS_AFTER="$RUN_STATS_AFTER" \
MACOS_FACTS="$MACOS_FACTS" ATTACH="$MODE_ATTACH" WANT_SURFACES="$WANT_SURFACES" \
MODE="$([[ $MODE_ATTACH -eq 1 ]] && echo attach || { [[ $MODE_UP -eq 1 ]] && echo up || echo run; })" \
FACTSFILE="$FACTSFILE" JOURNEY_FILE="${JOURNEY_FILE:-}" \
node -e '
  const e=process.env, fs=require("fs");
  // The journey verdict is read from the FILE the journey itself wrote, not
  // re-derived here and not scraped from its log. A launcher that re-judged the
  // journey could disagree with the journey, and only one of the two would be
  // in the report.
  let writeJourney=null;
  if (e.JOURNEY_FILE) { try { writeJourney=JSON.parse(fs.readFileSync(e.JOURNEY_FILE,"utf8")) } catch {} }
  fs.writeFileSync(e.FACTSFILE, JSON.stringify({
    runId:e.RUN_ID, startedAt:e.STARTED_AT, clientId:e.CLIENT_ID||null, generation:e.GENERATION,
    mode:e.MODE, attach:e.ATTACH==="1", backendUrl:e.BACKEND_URL,
    wantSurfaces:e.WANT_SURFACES==="1",
    backendStatsBefore:e.STATS_BEFORE, backendStatsAfter:e.STATS_AFTER,
    backendRunStatsAfter:e.RUN_STATS_AFTER,
    macos:JSON.parse(e.MACOS_FACTS), ios:null,
    writeJourneyPath:e.JOURNEY_FILE||null, writeJourney,
  }, null, 2));'

# Remember what this run was, so a later --attach can join traffic to it by
# client id instead of guessing.
RUN_ID="$RUN_ID" CLIENT_ID="$RUN_CLIENT_ID" SHELL_PORT="${SHELL_PORT:-}" GENERATION="$GENERATION" \
BACKEND_URL="$BACKEND_URL" STATEFILE="$STATEFILE" \
node -e '
  const e=process.env;
  require("fs").writeFileSync(e.STATEFILE, JSON.stringify({
    runId:e.RUN_ID, clientId:e.CLIENT_ID, macosPort:e.SHELL_PORT?Number(e.SHELL_PORT):null,
    generation:e.GENERATION, backendUrl:e.BACKEND_URL, wroteAt:new Date().toISOString(),
  }, null, 2));'

# `--out` always writes the machine copy, whatever the human asked to see, so
# `--status` can report the last run without re-deriving it — and so the human
# and machine renderings are guaranteed to be the SAME object.
report_args=(--facts "$FACTSFILE" --out "$REPORTFILE")
[[ $EMIT_JSON   -eq 1 ]] && report_args+=(--json)
[[ $MODE_ASSERT -eq 1 ]] && report_args+=(--assert)
node "$HERE/lib/run-report.mjs" "${report_args[@]}"
report_status=$?
rm -f "$FACTSFILE"

# ── 8. How this process ends ────────────────────────────────────────────────
# Three different callers want three different endings, and conflating them is
# what made this script unusable from a program: a human wants the stack to stay
# up until Ctrl-C, an agent wants it to stay up and the COMMAND to return, and CI
# wants a verdict and nothing left behind.
if [[ $MODE_ATTACH -eq 1 ]]; then
  LEAVE_RUNNING=1                       # attach never owned anything
  exit $report_status
fi
if [[ $MODE_UP -eq 1 ]]; then
  LEAVE_RUNNING=1
  echo
  ok "stack left running. pidfile: $PIDFILE  |  status: integration/dev-stack.sh --status"
  exit $report_status
fi
if [[ $MODE_ASSERT -eq 1 ]]; then
  # --assert without --up is the CI shape: assert, tear down, exit the verdict.
  exit $report_status
fi
while true; do sleep 3600; done
