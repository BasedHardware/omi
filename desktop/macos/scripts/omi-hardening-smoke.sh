#!/bin/bash
# omi-hardening-smoke.sh — re-runnable runtime tripwire for hardened acceptance rows.
#
# Re-runs the proven runtime probes that verified the hardening acceptance matrix
# (auth token storage, log hygiene, settings navigation, PTT guard, agent-kill
# recovery, expired-token refresh, shutdown flush) against a NAMED TEST BUNDLE so
# a row that regresses upstream is caught the next run, not the next audit wave.
#
# Usage:
#   omi-hardening-smoke.sh run [--bundle-id com.omi.omi-smoke] [--port 47797]
#                              [--only p1,p2] [--skip p1,p2] [--report-dir DIR]
#                              [--launch|--attach] [--timeout-mult X] [--dry-run]
#   omi-hardening-smoke.sh list            # probe ids in canonical run order
#   omi-hardening-smoke.sh scan <dir>      # credential-pattern scan (exit 1 if dirty)
#   omi-hardening-smoke.sh help
#
# Probes (canonical order — destructive probes deliberately last):
#   auth-06        prod bundle keeps no auth tokens in UserDefaults (passive read)
#   set-04         app logs contain no credential patterns
#   set-01         bridge settings navigation reaches sub-sections (case-tolerant)
#   mic-06         20 rapid PTT toggles leave no orphan capture
#   chat-03        kill -9 of the agent subprocess recovers on the next ask
#   auth-03        expired idToken refreshes on relaunch without sign-out  [relaunches app]
#   lnch-07        SIGTERM flushes <=5s with no local-DB loss              [stops app]
#   self-hygiene   the report dir itself contains no credential patterns
#
# Exit codes: 0 all selected probes PASS · 1 any FAIL · 2 usage error / production
# bundle refused · 3 no FAILs but at least one BLOCKED (harness could not run).
#
# Safety: refuses to manage anything but com.omi.omi-* named test bundles. The ONLY
# production interaction is the read-only `defaults read` in auth-06. NEVER point
# this script at com.omi.computer-macos, Omi Dev, or any user-facing install.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
OMI_CTL="$SCRIPT_DIR/omi-ctl"

PROD_BUNDLE_ID="com.omi.computer-macos"
DEFAULT_BUNDLE_ID="com.omi.omi-smoke"
DEFAULT_PORT=47797
PROBES="auth-06 set-04 set-01 mic-06 chat-03 auth-03 lnch-07 self-hygiene"

# Credential patterns shared by set-04 and `scan` (keep in sync with the
# evidence-hygiene rules: JWT, Google API key, bearer, omi tokens, Firebase
# refresh token, inline refreshToken values).
CRED_PATTERNS='eyJ[A-Za-z0-9_-]{40,}|AIza[0-9A-Za-z_-]{30,}|Bearer [A-Za-z0-9._-]{20,}|omi_mcp_[a-z0-9]{10,}|omi_auto_[a-z0-9]{16,}|AMf-[A-Za-z0-9_-]{20,}|refresh[Tt]oken["'"'"': =]+[A-Za-z0-9_/+-]{20,}'

log() { printf '%s\n' "$*" >&2; }
die() { log "omi-hardening-smoke: $*"; exit 2; }

# ---------------------------------------------------------------------------
# scan — credential-pattern sweep over a directory (also probe 8)
# ---------------------------------------------------------------------------
cmd_scan() {
  local dir="${1:-}"
  [ -n "$dir" ] || die "usage: omi-hardening-smoke.sh scan <dir>"
  [ -d "$dir" ] || die "scan: no such directory: $dir"
  local dirty status
  set +e
  dirty="$(grep -rlE "$CRED_PATTERNS" -- "$dir" 2>&1)"
  status=$?
  set -e
  if [ "$status" -eq 0 ]; then
    log "scan: credential patterns found in:"
    printf '%s\n' "$dirty" >&2
    return 1
  fi
  if [ "$status" -ne 1 ]; then
    # grep >=2 means it could not scan (unreadable files, bad args) — that is a
    # scan FAILURE, never a clean result.
    log "scan: could not scan $dir (grep exit $status)"
    printf '%s\n' "$dirty" >&2
    return 2
  fi
  log "scan: clean ($dir)"
  return 0
}

cmd_list() { for p in $PROBES; do printf '%s\n' "$p"; done; }

cmd_help() { awk '/^# /{sub(/^# ?/,""); print} /^set -euo/{exit}' "$0"; }

# ---------------------------------------------------------------------------
# run — state
# ---------------------------------------------------------------------------
BUNDLE_ID="$DEFAULT_BUNDLE_ID"
PORT="$DEFAULT_PORT"
REPORT_DIR=""
ONLY=""
SKIP=""
MODE="launch"        # launch | attach
TIMEOUT_MULT=1
DRY_RUN=0
APP_PID=""
APP_SPAWNED=0
RESULTS_TSV=""
STARTED_AT=""

parse_run_args() {
  while [ $# -gt 0 ]; do
    case "$1" in
      --bundle-id) [ $# -ge 2 ] || die "--bundle-id needs a value"; BUNDLE_ID="$2"; shift 2 ;;
      --port) [ $# -ge 2 ] || die "--port needs a value"; PORT="$2"; shift 2 ;;
      --only) [ $# -ge 2 ] || die "--only needs a value"; ONLY="$2"; shift 2 ;;
      --skip) [ $# -ge 2 ] || die "--skip needs a value"; SKIP="$2"; shift 2 ;;
      --report-dir) [ $# -ge 2 ] || die "--report-dir needs a value"; REPORT_DIR="$2"; shift 2 ;;
      --launch) MODE="launch"; shift ;;
      --attach) MODE="attach"; shift ;;
      --timeout-mult) [ $# -ge 2 ] || die "--timeout-mult needs a value"; TIMEOUT_MULT="$2"; shift 2 ;;
      --dry-run) DRY_RUN=1; shift ;;
      *) die "unknown flag for run: $1" ;;
    esac
  done
  case "$PORT" in (*[!0-9]*|'') die "--port must be numeric" ;; esac
  if [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then die "--port must be in 1-65535"; fi
  case "$TIMEOUT_MULT" in (*[!0-9]*|'') die "--timeout-mult must be a positive integer" ;; esac
  [ "$TIMEOUT_MULT" -ge 1 ] || die "--timeout-mult must be >= 1"
  validate_probe_csv "$ONLY"
  validate_probe_csv "$SKIP"
  refuse_non_test_bundle
  [ -n "$REPORT_DIR" ] || REPORT_DIR="${TMPDIR:-/tmp}/omi-hardening-smoke/$(date -u +%Y%m%dT%H%M%SZ)"
}

validate_probe_csv() {
  local csv="$1" item known
  [ -n "$csv" ] || return 0
  for item in $(printf '%s' "$csv" | tr ',' ' '); do
    known=0
    for p in $PROBES; do [ "$p" = "$item" ] && known=1; done
    [ "$known" = 1 ] || die "unknown probe id: $item (see: omi-hardening-smoke.sh list)"
  done
}

refuse_non_test_bundle() {
  if [ "$BUNDLE_ID" = "$PROD_BUNDLE_ID" ]; then
    die "refusing to run against the production bundle ($PROD_BUNDLE_ID)"
  fi
  case "$BUNDLE_ID" in
    com.omi.omi-*) : ;;
    *) die "refusing bundle '$BUNDLE_ID' — only com.omi.omi-* named test bundles are supported" ;;
  esac
}

probe_selected() {
  local id="$1" item
  if [ -n "$ONLY" ]; then
    for item in $(printf '%s' "$ONLY" | tr ',' ' '); do [ "$item" = "$id" ] && return 0; done
    return 1
  fi
  if [ -n "$SKIP" ]; then
    for item in $(printf '%s' "$SKIP" | tr ',' ' '); do [ "$item" = "$id" ] && return 1; done
  fi
  return 0
}

record() {
  # record <id> <STATUS> <seconds> <reason...>
  local id="$1" status="$2" secs="$3"; shift 3
  printf '%s\t%s\t%s\t%s\n' "$id" "$status" "$secs" "$*" >>"$RESULTS_TSV"
  log "[$status] $id${*:+ — $*}"
}

now_s() { date +%s; }

app_name() { printf '%s' "${BUNDLE_ID#com.omi.}"; }
app_dir() { printf '/Applications/%s.app' "$(app_name)"; }
app_binary() { printf '%s/Contents/MacOS/Omi Computer' "$(app_dir)"; }
app_log() { printf '%s/app.log' "$REPORT_DIR"; }
token_file() { printf '%s/omi-automation-%s.token' "${TMPDIR:-/tmp}" "$PORT"; }

bridge() { OMI_AUTOMATION_PORT="$PORT" "$OMI_CTL" "$@"; }

bridge_state_field() {
  # bridge_state_field <jsonKey> — empty string if unavailable
  bridge state 2>/dev/null | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
r = d.get("result", d)
v = r.get(sys.argv[1])
print("" if v is None else v)
' "$1" 2>/dev/null || true
}

defaults_key_presence() {
  # defaults_key_presence <domain> <key> — prints "present len=N" or "absent";
  # NEVER prints the value (redact-at-capture).
  local v
  if v="$(defaults read "$1" "$2" 2>/dev/null)"; then
    printf 'present len=%s' "$(printf '%s' "$v" | wc -c | tr -d ' ')"
  else
    printf 'absent'
  fi
}

defaults_read_raw() { defaults read "$1" "$2" 2>/dev/null || true; }

launch_app() {
  local deadline binary
  binary="$(app_binary)"
  [ -x "$binary" ] || return 1
  rm -f "$(token_file)"
  OMI_AUTOMATION_PORT="$PORT" OMI_ENABLE_LOCAL_AUTOMATION=1 \
    nohup "$binary" >>"$(app_log)" 2>&1 &
  APP_PID=$!
  # Detach from job control so bash doesn't print "Terminated" when probes
  # SIGTERM the app deliberately.
  disown "$APP_PID" 2>/dev/null || true
  APP_SPAWNED=1
  # Cold starts can take >60s to accept bridge connections (agent VM provisioning,
  # realtime warmup compete at launch) — 120s keeps marginal starts from reading
  # as BLOCKED. Scaled by --timeout-mult.
  deadline=$(( $(now_s) + 120 * TIMEOUT_MULT ))
  while [ "$(now_s)" -lt "$deadline" ]; do
    if [ -f "$(token_file)" ] && bridge state >/dev/null 2>&1; then return 0; fi
    kill -0 "$APP_PID" 2>/dev/null || return 1
    sleep 2
  done
  return 1
}

stop_app() {
  # stop_app — SIGTERM the pid we spawned; prints exit latency in centiseconds.
  local i=0
  [ -n "$APP_PID" ] || { printf '0'; return 0; }
  kill -TERM "$APP_PID" 2>/dev/null || { APP_PID=""; printf '0'; return 0; }
  while kill -0 "$APP_PID" 2>/dev/null; do
    i=$((i + 1))
    [ "$i" -ge $((60 * TIMEOUT_MULT)) ] && { printf '%s' $((i * 10)); return 1; }
    sleep 0.1
  done
  APP_PID=""
  printf '%s' $((i * 10))
}

cleanup_trap() {
  # Kill only the exact PID this harness spawned — never pkill by name.
  if [ "$APP_SPAWNED" = 1 ] && [ -n "$APP_PID" ] && kill -0 "$APP_PID" 2>/dev/null; then
    kill -TERM "$APP_PID" 2>/dev/null || true
  fi
}

# ---------------------------------------------------------------------------
# probes
# ---------------------------------------------------------------------------
probe_auth_06() {
  # Tokens must not rest in UserDefaults on the PRODUCTION bundle (passive,
  # read-only). Non-prod token presence is by-design (auth seeding) — recorded
  # informationally, never asserted.
  local t0 keys k prod_hits=0 lines=""
  t0=$(now_s)
  keys="auth_idToken auth_refreshToken auth_tokenExpiry auth_tokenUserId"
  if ! defaults read "$PROD_BUNDLE_ID" >/dev/null 2>&1; then
    record auth-06 PASS $(( $(now_s) - t0 )) "prod-not-installed (no $PROD_BUNDLE_ID defaults domain)"
    return
  fi
  for k in $keys; do
    lines="$lines prod:$k=$(defaults_key_presence "$PROD_BUNDLE_ID" "$k")"
    case "$(defaults_key_presence "$PROD_BUNDLE_ID" "$k")" in present*) prod_hits=$((prod_hits + 1)) ;; esac
  done
  for k in $keys; do
    lines="$lines test:$k=$(defaults_key_presence "$BUNDLE_ID" "$k")"
  done
  printf '%s\n' "$lines" | tr ' ' '\n' >"$REPORT_DIR/auth-06.log"
  if [ "$prod_hits" -eq 0 ]; then
    record auth-06 PASS $(( $(now_s) - t0 )) "prod bundle: all 4 token keys absent"
  else
    record auth-06 FAIL $(( $(now_s) - t0 )) "prod bundle has $prod_hits token key(s) in UserDefaults"
  fi
}

probe_set_04() {
  local t0 f total=0 hits
  t0=$(now_s)
  {
    for f in /private/tmp/omi-dev.log /private/tmp/omi.log; do
      if [ ! -r "$f" ]; then echo "$f: not present/readable"; continue; fi
      hits="$(grep -cE "$CRED_PATTERNS" "$f" 2>/dev/null || true)"
      hits="${hits:-0}"
      echo "$f: $hits credential-pattern hits ($(wc -l <"$f" | tr -d ' ') lines)"
      total=$((total + hits))
    done
    echo "total=$total"
  } >"$REPORT_DIR/set-04.log"
  if [ "$total" -eq 0 ]; then
    record set-04 PASS $(( $(now_s) - t0 )) "0 credential patterns across app logs"
  else
    record set-04 FAIL $(( $(now_s) - t0 )) "$total credential-pattern hits in app logs (see set-04.log)"
  fi
}

probe_set_01() {
  local t0 want got fails=0 pre
  t0=$(now_s)
  if ! bridge state >/dev/null 2>&1; then
    record set-01 BLOCKED $(( $(now_s) - t0 )) "bridge unreachable"
    return
  fi
  : >"$REPORT_DIR/set-01.log"
  for pair in "rewind:Rewind" "plan-usage:Plan and Usage" "floating_bar:Floating Bar" "transcription:Transcription"; do
    want="${pair#*:}"
    bridge navigate settings "${pair%%:*}" >/dev/null 2>&1 || true
    sleep 0.5
    got="$(bridge_state_field selectedSettingsSection)"
    echo "navigate settings '${pair%%:*}' -> '$got' (want '$want')" >>"$REPORT_DIR/set-01.log"
    [ "$got" = "$want" ] || fails=$((fails + 1))
  done
  pre="$(bridge_state_field selectedSettingsSection)"
  bridge navigate settings "nonsense-section" >/dev/null 2>&1 || true
  sleep 0.5
  got="$(bridge_state_field selectedSettingsSection)"
  echo "navigate settings 'nonsense-section' -> '$got' (want unchanged '$pre')" >>"$REPORT_DIR/set-01.log"
  [ "$got" = "$pre" ] || fails=$((fails + 1))
  if [ "$fails" -eq 0 ]; then
    record set-01 PASS $(( $(now_s) - t0 )) "4 sections + unknown-input guard"
  else
    record set-01 FAIL $(( $(now_s) - t0 )) "$fails navigation assertion(s) failed (see set-01.log)"
  fi
}

probe_mic_06() {
  local t0 i ok=0 guard
  t0=$(now_s)
  if ! bridge state >/dev/null 2>&1; then
    record mic-06 BLOCKED $(( $(now_s) - t0 )) "bridge unreachable"
    return
  fi
  for i in $(seq 1 20); do
    bridge action ptt_start >/dev/null 2>&1 && ok=$((ok + 1))
    bridge action ptt_stop >/dev/null 2>&1 && ok=$((ok + 1))
  done
  sleep 2
  guard="$(grep -c 'startListening ignored' "$(app_log)" 2>/dev/null || true)"
  guard="${guard:-0}"
  {
    echo "ptt calls ok=$ok/40"
    echo "generation-guard lines in app log: $guard"
    grep -E 'PushToTalkManager' "$(app_log)" 2>/dev/null | tail -20 || true
  } >"$REPORT_DIR/mic-06.log"
  if [ "$ok" -eq 40 ] && bridge state >/dev/null 2>&1; then
    record mic-06 PASS $(( $(now_s) - t0 )) "40/40 toggles, app responsive, guard lines=$guard"
  else
    record mic-06 FAIL $(( $(now_s) - t0 )) "toggles ok=$ok/40 or app unresponsive after loop"
  fi
}

probe_chat_03() {
  local t0 reply1 reply2 nodepid
  t0=$(now_s)
  if ! bridge state >/dev/null 2>&1; then
    record chat-03 BLOCKED $(( $(now_s) - t0 )) "bridge unreachable"
    return
  fi
  reply1="$(bridge action ask query="reply with the single word ready" 2>/dev/null | head -c 2000 || true)"
  if [ -z "$reply1" ]; then
    record chat-03 BLOCKED $(( $(now_s) - t0 )) "warm ask returned nothing (agent unavailable)"
    return
  fi
  nodepid="$(pgrep -P "$APP_PID" 2>/dev/null | head -1 || true)"
  if [ -z "$nodepid" ]; then
    record chat-03 BLOCKED $(( $(now_s) - t0 )) "no agent subprocess found under app pid"
    return
  fi
  kill -9 "$nodepid" 2>/dev/null || true
  sleep 3
  reply2="$(bridge action ask query="reply with the single word recovered" 2>/dev/null | head -c 2000 || true)"
  {
    echo "warm reply bytes: $(printf '%s' "$reply1" | wc -c | tr -d ' ')"
    echo "killed agent subprocess pid=$nodepid (SIGKILL)"
    echo "post-kill reply bytes: $(printf '%s' "$reply2" | wc -c | tr -d ' ')"
    grep -E 'AgentRuntimeProcess.*(terminated|exit)' "$(app_log)" 2>/dev/null | tail -3 || true
  } >"$REPORT_DIR/chat-03.log"
  if [ -n "$reply2" ]; then
    record chat-03 PASS $(( $(now_s) - t0 )) "agent respawned; post-kill ask answered"
  else
    record chat-03 FAIL $(( $(now_s) - t0 )) "no reply after killing agent subprocess"
  fi
}

probe_auth_03() {
  # Destructive: relaunches the app. Requires launch mode.
  local t0 signed pre_expiry post_expiry latency
  t0=$(now_s)
  signed="$(defaults_read_raw "$BUNDLE_ID" auth_isSignedIn)"
  if [ "$signed" != "1" ]; then
    record auth-03 BLOCKED $(( $(now_s) - t0 )) "auth-stale: bundle not signed in — reseed via omi-auth-dump.sh + omi-auth-seed.sh $BUNDLE_ID"
    return
  fi
  latency="$(stop_app)" || true
  pre_expiry="$(defaults_read_raw "$BUNDLE_ID" auth_tokenExpiry)"
  if ! defaults write "$BUNDLE_ID" auth_tokenExpiry -float 1000; then
    record auth-03 BLOCKED $(( $(now_s) - t0 )) "defaults write failed (could not tamper expiry)"
    return
  fi
  if ! launch_app; then
    record auth-03 BLOCKED $(( $(now_s) - t0 )) "relaunch failed (bridge never came up)"
    return
  fi
  sleep 3
  post_expiry="$(defaults_read_raw "$BUNDLE_ID" auth_tokenExpiry)"
  signed="$(defaults_read_raw "$BUNDLE_ID" auth_isSignedIn)"
  {
    echo "pre-tamper expiry present: $(printf '%s' "$pre_expiry" | wc -c | tr -d ' ') chars (value redacted)"
    echo "tampered expiry to epoch 1000; relaunched"
    echo "post-launch signed_in=$signed"
    python3 -c "import time; e=float('${post_expiry:-0}'); print('post-launch expiry is', 'FUTURE (refreshed)' if e > time.time() else 'still past (no refresh)')"
  } >"$REPORT_DIR/auth-03.log"
  if [ "$signed" = "1" ] && python3 -c "import time,sys; sys.exit(0 if float('${post_expiry:-0}') > time.time() else 1)"; then
    record auth-03 PASS $(( $(now_s) - t0 )) "expired token refreshed on relaunch; session preserved"
  else
    record auth-03 FAIL $(( $(now_s) - t0 )) "signed_in=$signed, expiry not refreshed (see auth-03.log)"
  fi
}

probe_lnch_07() {
  # Terminal probe: SIGTERMs the app and leaves it stopped.
  local t0 uid db pre_a pre_b post_a post_b integ latency rc=0
  t0=$(now_s)
  uid="$(defaults_read_raw "$BUNDLE_ID" auth_tokenUserId)"
  db="$HOME/Library/Application Support/Omi/users/$uid/omi.db"
  if [ -z "$uid" ] || [ ! -f "$db" ]; then
    record lnch-07 BLOCKED $(( $(now_s) - t0 )) "no user DB for this bundle's signed-in user"
    return
  fi
  pre_a="$(sqlite3 -readonly "$db" 'SELECT count(*) FROM screenshots;' 2>/dev/null || echo -1)"
  pre_b="$(sqlite3 -readonly "$db" 'SELECT count(*) FROM transcription_segments;' 2>/dev/null || echo -1)"
  latency="$(stop_app)" || rc=1
  sleep 1
  post_a="$(sqlite3 -readonly "$db" 'SELECT count(*) FROM screenshots;' 2>/dev/null || echo -2)"
  post_b="$(sqlite3 -readonly "$db" 'SELECT count(*) FROM transcription_segments;' 2>/dev/null || echo -2)"
  integ="$(sqlite3 -readonly "$db" 'PRAGMA integrity_check;' 2>/dev/null | head -1 || echo check-failed)"
  {
    echo "exit latency: ${latency}0 ms (threshold 5000 ms)"
    echo "screenshots: $pre_a -> $post_a"
    echo "transcription_segments: $pre_b -> $post_b"
    echo "integrity_check: $integ"
  } >"$REPORT_DIR/lnch-07.log"
  if [ "$rc" -eq 0 ] && [ "$latency" -le 500 ] && [ "$post_a" -ge "$pre_a" ] && [ "$post_b" -ge "$pre_b" ] && [ "$integ" = "ok" ]; then
    record lnch-07 PASS $(( $(now_s) - t0 )) "flush ${latency}0ms, no row loss, integrity ok"
  else
    record lnch-07 FAIL $(( $(now_s) - t0 )) "latency=${latency}0ms rows:$pre_a/$pre_b->$post_a/$post_b integrity=$integ"
  fi
}

probe_self_hygiene() {
  local t0 rc=0
  t0=$(now_s)
  cmd_scan "$REPORT_DIR" 2>>"$REPORT_DIR/self-hygiene.log" || rc=$?
  case "$rc" in
    0) record self-hygiene PASS $(( $(now_s) - t0 )) "report dir clean" ;;
    1) record self-hygiene FAIL $(( $(now_s) - t0 )) "credential patterns in the report dir itself" ;;
    *) record self-hygiene BLOCKED $(( $(now_s) - t0 )) "scan could not read the report dir (see self-hygiene.log)" ;;
  esac
}

# ---------------------------------------------------------------------------
# run — orchestration
# ---------------------------------------------------------------------------
write_summary() {
  # Written AFTER the self-hygiene scan by design (it embeds the exit code), so
  # `record` reasons MUST stay value-free (counts/booleans/paths only) — a raw
  # credential in a reason string would bypass the report-dir scan.
  local exit_code="$1"
  GIT_SHA="$(git -C "$MACOS_DIR" rev-parse --short HEAD 2>/dev/null || echo unknown)" \
  STARTED_AT="$STARTED_AT" BUNDLE_ID="$BUNDLE_ID" PORT="$PORT" EXIT_CODE="$exit_code" \
  python3 - "$RESULTS_TSV" >"$REPORT_DIR/smoke-summary.json" <<'PY'
import json, os, sys, datetime
probes = []
with open(sys.argv[1]) as fh:
    for line in fh:
        parts = line.rstrip("\n").split("\t", 3)
        if len(parts) < 3:
            continue
        pid, status, secs = parts[0], parts[1], parts[2]
        reason = parts[3] if len(parts) > 3 else ""
        probes.append({"id": pid, "status": status, "duration_s": int(secs), "reason": reason})
print(json.dumps({
    "started": os.environ["STARTED_AT"],
    "finished": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "bundle": os.environ["BUNDLE_ID"],
    "port": int(os.environ["PORT"]),
    "git_sha": os.environ["GIT_SHA"],
    "exit_code": int(os.environ["EXIT_CODE"]),
    "probes": probes,
}, indent=2))
PY
}

compute_exit() {
  local fails blocked
  fails="$(cut -f2 "$RESULTS_TSV" | grep -c '^FAIL$' || true)"
  blocked="$(cut -f2 "$RESULTS_TSV" | grep -c '^BLOCKED$' || true)"
  if [ "${fails:-0}" -gt 0 ]; then echo 1
  elif [ "${blocked:-0}" -gt 0 ]; then echo 3
  else echo 0
  fi
}

cmd_run() {
  parse_run_args "$@"
  mkdir -p "$REPORT_DIR"
  RESULTS_TSV="$REPORT_DIR/results.tsv"
  : >"$RESULTS_TSV"
  STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  trap cleanup_trap EXIT

  if [ "$DRY_RUN" = 1 ]; then
    for p in $PROBES; do record "$p" SKIP 0 "dry-run"; done
    write_summary 0
    log "dry-run complete: $REPORT_DIR/smoke-summary.json"
    exit 0
  fi

  # Preflight: tooling, app presence, port.
  command -v sqlite3 >/dev/null || die "sqlite3 not found"
  command -v python3 >/dev/null || die "python3 not found"
  local needs_app=0
  for p in set-01 mic-06 chat-03 auth-03 lnch-07; do
    probe_selected "$p" && needs_app=1
  done

  if [ "$needs_app" = 1 ]; then
    if [ "$MODE" = "launch" ]; then
      [ -x "$(app_binary)" ] || die "app not installed: $(app_dir) — build once with OMI_APP_NAME=$(app_name) ./run.sh"
      if nc -z 127.0.0.1 "$PORT" >/dev/null 2>&1; then
        for p in set-01 mic-06 chat-03 auth-03 lnch-07; do
          probe_selected "$p" && record "$p" BLOCKED 0 "port-busy: 127.0.0.1:$PORT already listening"
        done
        needs_app=0
      elif ! launch_app; then
        for p in set-01 mic-06 chat-03 auth-03 lnch-07; do
          probe_selected "$p" && record "$p" BLOCKED 0 "launch failed: bridge never became ready (see app.log)"
        done
        needs_app=0
      fi
    else
      # attach: require a reachable bridge; lifecycle probes are skipped.
      if ! bridge state >/dev/null 2>&1; then
        for p in set-01 mic-06 chat-03; do
          probe_selected "$p" && record "$p" BLOCKED 0 "attach: no bridge on port $PORT"
        done
        needs_app=0
      fi
    fi
  fi

  # Identity guard: whatever bridge we ended up talking to must be OUR bundle —
  # never drive a foreign test bundle that happens to hold the port.
  if [ "$needs_app" = 1 ]; then
    actual_bundle="$(bridge_state_field bundleIdentifier)"
    if [ "$actual_bundle" != "$BUNDLE_ID" ]; then
      for p in set-01 mic-06 chat-03 auth-03 lnch-07; do
        probe_selected "$p" && record "$p" BLOCKED 0 "wrong-bundle: bridge on port $PORT is '${actual_bundle:-unreachable}', expected $BUNDLE_ID"
      done
      needs_app=0
    fi
  fi

  probe_selected auth-06 && probe_auth_06
  probe_selected set-04 && probe_set_04
  if [ "$needs_app" = 1 ]; then
    probe_selected set-01 && probe_set_01
    probe_selected mic-06 && probe_mic_06
    probe_selected chat-03 && probe_chat_03
    if [ "$MODE" = "launch" ]; then
      probe_selected auth-03 && probe_auth_03
      probe_selected lnch-07 && probe_lnch_07
    else
      probe_selected auth-03 && record auth-03 SKIP 0 "attach-mode (needs app lifecycle ownership)"
      probe_selected lnch-07 && record lnch-07 SKIP 0 "attach-mode (needs app lifecycle ownership)"
    fi
  fi
  # self-hygiene always runs, immune to --only/--skip.
  probe_self_hygiene

  local code
  code="$(compute_exit)"
  write_summary "$code"
  log "report: $REPORT_DIR (summary: smoke-summary.json)"
  exit "$code"
}

main() {
  local cmd="${1:-help}"
  shift || true
  case "$cmd" in
    run) cmd_run "$@" ;;
    list) cmd_list ;;
    scan) cmd_scan "$@" ;;
    help|-h|--help) cmd_help ;;
    *) die "unknown command: $cmd (run|list|scan|help)" ;;
  esac
}

main "$@"
