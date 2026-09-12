#!/usr/bin/env bash
# Hermetic contract test for scripts/omi-e2e-pool: slot leasing for the
# pre-authorized E2E bundle pool. No app, no TCC, no /Applications — the pool
# directory, the "worktrees" and the applications directory all live in a
# tmpdir, so it runs on any host, including Linux CI.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
POOL="$MACOS_DIR/scripts/omi-e2e-pool"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}
assert_eq() { [ "$1" = "$2" ] || fail "${3:-} expected '$2', got '$1'"; }
# grep reads a temp file, not a pipe: with -q some grep builds exit on first
# match while the writer still has data, the writer then dies on SIGPIPE, and
# the pipeline status turns a successful match into a failure.
assert_grep() {
  local data="$1" pattern="$2" tmp
  tmp="$(mktemp "${TMPDIR:-/tmp}/omi-e2e-pool-assert.XXXXXX")"
  printf '%s' "$data" > "$tmp"
  grep -q$3 -- "$pattern" "$tmp"
  local rc=$?
  rm -f "$tmp"
  [ "$rc" = 0 ] || fail "${4:-} expected output to contain '$pattern':
$data"
}
assert_contains() { assert_grep "$1" "$2" "" "${3:-}"; }
# Fixed-string variant for patterns containing '$' — BRE '$' handling differs
# across grep implementations (BSD treats mid-pattern '$' literally, others
# anchor it), and these assertions are about exact source text.
assert_contains_fixed() { assert_grep "$1" "$2" "F" "${3:-}"; }
# Source-contract assertions grep the file itself: run.sh is ~70KB and piping
# it through shell variables on every assert dominates the suite's runtime.
assert_file_contains() {
  grep -q$3 -- "$2" "$1" || fail "${4:-} expected $1 to contain '$2'"
}

TMP="$(mktemp -d "${TMPDIR:-/tmp}/omi-e2e-pool-test.XXXXXX")"
# The contract asserts exact worktree spellings; pin the tmpdir to its physical
# path so a symlinked TMPDIR (/var/folders, /tmp) cannot leak logical spellings.
TMP="$(cd -P "$TMP" && pwd)"
trap 'rm -rf "$TMP"' EXIT

export OMI_E2E_POOL_DIR="$TMP/pool"
export OMI_E2E_POOL_APPLICATIONS_DIR="$TMP/apps"
export OMI_E2E_POOL_SIZE=2
export OMI_E2E_POOL_STALE=3600
unset OMI_E2E_POOL_WORKTREE OMI_E2E_POOL_TOKEN OMI_E2E_POOL_SIGN_IDENTITY 2>/dev/null || true
# The session manager decides the background→isolated auth default; pin it so
# every assertion below is hermetic regardless of where the suite runs (a CI
# shell is usually not Aqua). Dedicated sections override it per-assertion.
export OMI_E2E_POOL_MANAGER_NAME=Aqua
mkdir -p "$TMP/apps" "$TMP/wt-a" "$TMP/wt-b" "$TMP/wt-c"
WT_A="$TMP/wt-a" WT_B="$TMP/wt-b" WT_C="$TMP/wt-c"

# ── slot table is derived from the configuration, not hand-listed ─────────
slots="$("$POOL" slots)"
assert_eq "$(printf '%s\n' "$slots" | wc -l | tr -d ' ')" "2" "slots row count"
assert_contains "$slots" "omi-e2e-1	com.omi.omi-e2e-1	47701	10101	8301" "slot 1 row"
bigger="$(OMI_E2E_POOL_SIZE=7 "$POOL" slots | tail -1)"
assert_contains "$bigger" "omi-e2e-7	com.omi.omi-e2e-7	47707" "pool size is dynamic"
custom="$(OMI_E2E_POOL_PREFIX=omi-lab OMI_E2E_POOL_SIZE=1 "$POOL" slots)"
assert_contains "$custom" "omi-lab-1	com.omi.omi-lab-1" "prefix is configurable"
if OMI_E2E_POOL_PREFIX=lab "$POOL" slots >/dev/null 2>&1; then fail "a prefix without omi- must be rejected"; fi
if OMI_E2E_POOL_PREFIX=omi_lab "$POOL" slots >/dev/null 2>&1; then fail "a prefix run.sh would slugify differently must be rejected"; fi
if OMI_E2E_POOL_PREFIX=Omi-Lab "$POOL" slots >/dev/null 2>&1; then fail "a prefix run.sh would lowercase must be rejected"; fi
assert_contains "$(OMI_E2E_POOL_PREFIX=omi-lab-2 OMI_E2E_POOL_SIZE=1 "$POOL" slots)" "omi-lab-2-1" "an already-slug-form prefix is accepted"
if OMI_E2E_POOL_SIZE=0 "$POOL" slots >/dev/null 2>&1; then fail "pool size 0 must be rejected"; fi

# ── a non-pool slug passes verify untouched ────────────────────────────────
"$POOL" verify omi-fix-rewind || fail "non-pool slug must pass verify"
"$POOL" verify omi-e2e-x || fail "non-numeric suffix is not a pool slot"
assert_eq "$("$POOL" verify omi-fix-rewind)" "" "non-pool verify prints nothing"

# ── acquire: first free slot, env, verify from the holder ──────────────────
slot="$("$POOL" acquire --quiet --worktree "$WT_A" --holder lane-a)"
assert_eq "$slot" "1" "first acquire takes slot 1"
[ -f "$WT_A/.dev/e2e-pool.env" ] || fail "acquire must write the worktree env file"
env_out="$("$POOL" env --worktree "$WT_A")"
assert_contains "$env_out" "export OMI_APP_NAME='omi-e2e-1'" "env app name"
assert_contains "$env_out" "export OMI_AUTOMATION_PORT='47701'" "env bridge port"
assert_contains "$env_out" "export PORT='10101'" "env backend port"
assert_contains "$env_out" "export OMI_SIGN_IDENTITY='Omi Local Dev Signing'" "env pins the default identity"
assert_eq "$("$POOL" verify --worktree "$WT_A" omi-e2e-1)" "1" "verify prints the pool slot number"
if printf '%s' "$env_out" | grep -q OMI_SKIP_AUTH_SEED; then fail "shared auth must not skip the auth seed"; fi

"$POOL" verify --worktree "$WT_A" omi-e2e-1 || fail "holder worktree must pass verify"
token="$(sed -n "s/^export OMI_E2E_POOL_TOKEN='\(.*\)'$/\1/p" "$WT_A/.dev/e2e-pool.env")"
[ -n "$token" ] || fail "env file carries no token"
OMI_E2E_POOL_TOKEN="$token" "$POOL" verify --worktree "$WT_C" omi-e2e-1 || fail "the token must prove holdership from any cwd"

# ── the guard: another worktree is refused, and told who holds it ─────────
if out="$("$POOL" verify --worktree "$WT_B" omi-e2e-1 2>&1)"; then fail "another worktree must be refused"; fi
assert_contains "$out" "held by 'lane-a'" "refusal names the holder"
assert_contains "$out" "$WT_A" "refusal names the worktree"
if out="$("$POOL" verify --worktree "$WT_B" omi-e2e-2 2>&1)"; then fail "an unleased slot must be refused"; fi
assert_contains "$out" "nobody holds its lease" "unleased refusal explains itself"
if OMI_E2E_POOL_TOKEN=wrong "$POOL" verify --worktree "$WT_B" omi-e2e-1 >/dev/null 2>&1; then fail "a wrong token must not pass"; fi

# ── re-acquire is idempotent; a second worktree gets the next slot ────────
assert_eq "$("$POOL" acquire --quiet --worktree "$WT_A")" "1" "re-acquire keeps slot 1"
assert_eq "$("$POOL" acquire --quiet --worktree "$WT_B" --holder lane-b)" "2" "second worktree takes slot 2"
if out="$("$POOL" acquire --quiet --worktree "$WT_C" --holder lane-c 2>&1)"; then fail "a full pool must refuse"; fi
assert_contains "$out" "no free slot in a pool of 2" "full-pool refusal"
assert_contains "$out" "lane-a" "full-pool refusal lists live holders"
assert_contains "$out" "OMI_E2E_POOL_SIZE=3" "full-pool refusal says how to grow"
if "$POOL" acquire --quiet --worktree "$WT_A" --slot 2 >/dev/null 2>&1; then fail "a worktree may not take a second slot"; fi
if "$POOL" acquire --quiet --worktree "$WT_C" --slot 9 >/dev/null 2>&1; then fail "a slot outside the pool must be rejected"; fi

status="$("$POOL" status)"
assert_contains "$status" "held     lane-a ($WT_A" "status shows holder a"
assert_contains "$status" "held     lane-b ($WT_B" "status shows holder b"

# ── release: only the holder; then the slot is free again ─────────────────
if "$POOL" release --worktree "$WT_C" --slot 2 >/dev/null 2>&1; then fail "a non-holder must not release a live lease"; fi
# The default slot form resolves the caller worktree too; a foreign caller
# must not be able to free a live lease by naming only its slot.
if out="$(OMI_E2E_POOL_WORKTREE="$WT_C" "$POOL" release --slot 1 2>&1)"; then fail "a foreign default caller must not release a live lease"; fi
assert_contains "$out" "Refusing to release someone else's lease" "foreign default release explains ownership"
assert_contains "$out" "$WT_C" "foreign default release names the caller worktree"
OMI_E2E_POOL_WORKTREE="$WT_B" "$POOL" release --quiet --slot 2
[ ! -f "$WT_B/.dev/e2e-pool.env" ] || fail "release must remove the worktree env file"
assert_eq "$("$POOL" acquire --quiet --worktree "$WT_C" --holder lane-c)" "2" "released slot is reusable"
OMI_E2E_POOL_WORKTREE="$WT_C" "$POOL" release --quiet --slot 2
"$POOL" release --quiet --worktree "$WT_B" >/dev/null   # nothing held: not an error

# ── zero-padded --slot values address the canonical slot ───────────────────
assert_eq "$("$POOL" acquire --quiet --worktree "$WT_C" --slot 02)" "2" "--slot 02 canonicalizes to slot 2"
[ -f "$OMI_E2E_POOL_DIR/slots/2/lease" ] || fail "--slot 02 must lease the canonical slots/2 directory"
[ ! -e "$OMI_E2E_POOL_DIR/slots/02" ] || fail "no padded slot directory may be created"
OMI_E2E_POOL_WORKTREE="$WT_C" "$POOL" release --quiet --slot 02
[ ! -f "$OMI_E2E_POOL_DIR/slots/2/lease" ] || fail "--slot 02 must release canonical slot 2"

# ── ownership matches on the canonical path, not the acquire spelling ──────
mkdir -p "$WT_A"
ln -s "$WT_A" "$TMP/wt-a-link"
assert_eq "$("$POOL" acquire --quiet --worktree "$TMP/wt-a-link" --holder lane-a)" "1" "acquire through a symlink"
grep -q "^worktree=$WT_A$" "$OMI_E2E_POOL_DIR/slots/1/lease" || fail "a lease must be stored under the canonical worktree path"
( cd "$WT_A" && "$POOL" release --quiet --slot 1 ) || fail "owner's default release must accept a lease acquired via a symlink"
assert_eq "$("$POOL" acquire --quiet --worktree "$WT_A" --holder lane-a)" "1" "re-acquire after symlink release"
out="$(cd "$TMP" && "$POOL" acquire --quiet --worktree wt-b --holder lane-b)"
assert_eq "$out" "2" "acquire with a relative --worktree"
( cd "$WT_B" && "$POOL" release --quiet --slot 2 ) || fail "owner's default release must accept a relative acquire spelling"
assert_eq "$("$POOL" acquire --quiet --worktree "$WT_B" --holder lane-b)" "2" "re-acquire after relative release"
OMI_E2E_POOL_WORKTREE="$WT_B" "$POOL" release --quiet --slot 2

# ── liveness: a vanished worktree gives its slot up ───────────────────────
rm -rf "$WT_A"
if "$POOL" verify --worktree "$WT_B" omi-e2e-1 >/dev/null 2>&1; then fail "a defunct lease does not authorize a stranger"; fi
status="$("$POOL" status)"
assert_contains "$status" "DEFUNCT  lane-a" "vanished worktree shows as defunct"
assert_contains "$status" "is gone" "defunct reason names the worktree"
out="$("$POOL" acquire --worktree "$WT_B" --holder lane-b 2>&1)"
assert_contains "$out" "reclaiming slot 1 from 'lane-a'" "acquire reclaims a defunct slot loudly"
assert_eq "$(printf '%s\n' "$out" | tail -1)" "1" "reclaimed slot is slot 1"

# ── liveness: a lane that deleted .dev/ has given the slot up too ──────────
rm -rf "$WT_B/.dev"
status="$("$POOL" status)"
assert_contains "$status" "DEFUNCT  lane-b" "a deleted pool env file shows as defunct"
assert_contains "$status" "no longer holds the pool env file" "the missing-env reason names the worktree"
# A defunct lease remains reclaimable by another caller; only live ownership is
# protected by the release guard.
OMI_E2E_POOL_WORKTREE="$WT_A" "$POOL" release --quiet --slot 1
assert_eq "$("$POOL" acquire --quiet --worktree "$WT_A" --holder lane-a)" "1" "a deleted-env lease is reclaimable"

# ── liveness: a dead holder pid gives its slot up ─────────────────────────
OMI_E2E_POOL_WORKTREE="$WT_A" "$POOL" release --quiet --slot 1
sleep 0.2 &
dead_pid=$!
wait "$dead_pid"
mkdir -p "$WT_A"
assert_eq "$("$POOL" acquire --quiet --worktree "$WT_A" --holder lane-a --pid "$dead_pid")" "1" "acquire with a pid"
assert_contains "$("$POOL" status)" "holder pid $dead_pid is gone" "dead pid is defunct"
reap="$("$POOL" reap)"
assert_contains "$reap" "reaping slot 1" "reap frees the dead-pid slot"
assert_contains "$("$POOL" status)" "free" "slot is free after reap"
assert_contains "$("$POOL" reap)" "nothing to reap" "reap is idempotent"

# ── liveness: the heartbeat backstop, and that touching resets it ─────────
"$POOL" acquire --quiet --worktree "$WT_A" --holder lane-a >/dev/null
sed -i.bak 's/^touched=.*/touched=1/' "$OMI_E2E_POOL_DIR/slots/1/lease" && rm -f "$OMI_E2E_POOL_DIR/slots/1/lease.bak"
assert_contains "$("$POOL" status)" "past the 3600s backstop" "stale heartbeat is defunct"
"$POOL" env --worktree "$WT_A" >/dev/null || fail "the holder can still read env"
assert_contains "$("$POOL" status)" "held     lane-a" "env touches the heartbeat"

# ── isolated auth mode is persisted per slot and shapes the env ───────────
OMI_E2E_POOL_WORKTREE="$WT_A" "$POOL" release --quiet --slot 1
"$POOL" acquire --quiet --worktree "$WT_A" --auth isolated >/dev/null
env_out="$("$POOL" env --worktree "$WT_A")"
assert_contains "$env_out" "export OMI_SKIP_AUTH_SEED='1'" "isolated slot skips the Omi Dev auth clone"
assert_contains "$env_out" "export OMI_SKIP_REWIND_SEED='1'" "isolated slot skips the Rewind clone"
OMI_E2E_POOL_WORKTREE="$WT_A" "$POOL" release --quiet --slot 1
"$POOL" acquire --quiet --worktree "$WT_B" >/dev/null
assert_contains "$("$POOL" env --worktree "$WT_B")" "OMI_SKIP_AUTH_SEED" "auth mode sticks to the slot, not the holder"
assert_contains "$("$POOL" status)" "auth=isolated" "status shows the slot auth mode"
if "$POOL" acquire --quiet --worktree "$WT_B" --auth bogus >/dev/null 2>&1; then fail "auth mode must be validated"; fi
OMI_E2E_POOL_WORKTREE="$WT_B" "$POOL" release --quiet --slot 1

# ── identity is pinned at slot creation; a later override does not move it ─
out="$(OMI_E2E_POOL_SIGN_IDENTITY="Apple Development: Someone" "$POOL" acquire --worktree "$WT_A" 2>&1)"
assert_contains "$out" "WARNING slot 1 is pinned" "identity change is refused loudly"
assert_contains "$("$POOL" env --worktree "$WT_A")" "OMI_SIGN_IDENTITY='Omi Local Dev Signing'" "pinned identity survives"
OMI_E2E_POOL_WORKTREE="$WT_A" "$POOL" release --quiet --slot 1
# Slot 3 has never been created: growing the pool is how a never-used slot appears.
fresh="$(OMI_E2E_POOL_SIZE=3 OMI_E2E_POOL_SIGN_IDENTITY="Apple Development: Someone" "$POOL" acquire --quiet --worktree "$WT_A" --slot 3)"
assert_eq "$fresh" "3"
assert_contains "$(OMI_E2E_POOL_SIZE=3 "$POOL" env --worktree "$WT_A")" "OMI_SIGN_IDENTITY='Apple Development: Someone'" "a fresh slot pins the requested identity"
OMI_E2E_POOL_SIZE=3 OMI_E2E_POOL_WORKTREE="$WT_A" "$POOL" release --quiet --slot 3

# ── run: acquires, exports, and execs the command in one step ─────────────
# shellcheck disable=SC2016
out="$("$POOL" run --worktree "$WT_A" -- sh -c 'printf "%s %s %s" "$OMI_APP_NAME" "$OMI_AUTOMATION_PORT" "$OMI_E2E_POOL_SLOT"')"
assert_eq "$out" "omi-e2e-1 47701 1" "run exports the slot environment"
"$POOL" release --quiet --worktree "$WT_A"

# ── concurrent acquires are serialized; each lane wins a distinct slot ─────
for lane in a b c; do
  "$POOL" acquire --quiet --worktree "$TMP/wt-race-$lane" --holder "race-$lane" >"$TMP/race-$lane.out" 2>&1 &
done
wait || true
race_winners="$(cat "$TMP/race-a.out" "$TMP/race-b.out" "$TMP/race-c.out" | grep -cE '^[12]$' || true)"
assert_eq "$race_winners" "2" "exactly two of three racing acquires win a slot"
race_distinct="$(cat "$TMP/race-a.out" "$TMP/race-b.out" "$TMP/race-c.out" | grep -E '^[12]$' | sort -u | wc -l | tr -d ' ')"
assert_eq "$race_distinct" "2" "racing acquires win distinct slots"

# ── setup prints a per-slot human checklist ───────────────────────────────
setup="$("$POOL" setup --slot 2)"
assert_contains "$setup" "Slot 2 — omi-e2e-2" "setup names the slot"
assert_contains "$setup" "omi-ctl navigate settings permissions --show" "setup points at the permissions page"
assert_contains "$setup" "Screen Recording" "setup lists the system grants"


# ── launch policy: a background session defaults acquires to isolated ──────
# Race winners still hold live leases. Slot-only release from this checkout
# must refuse those (the ownership contract); free them via their worktrees.
for lane in a b c; do
  "$POOL" release --quiet --worktree "$TMP/wt-race-$lane" >/dev/null 2>&1 || true
done
"$POOL" release --quiet --worktree "$WT_A" >/dev/null 2>&1 || true
"$POOL" release --quiet --worktree "$WT_B" >/dev/null 2>&1 || true
"$POOL" release --quiet --worktree "$WT_C" >/dev/null 2>&1 || true
out="$(OMI_E2E_POOL_MANAGER_NAME=Background "$POOL" acquire --worktree "$WT_A" --holder lane-a 2>&1)"
assert_eq "$(printf '%s\n' "$out" | tail -1)" "1" "background acquire still prints the slot number last"
assert_contains "$out" "defaulting the slot to isolated auth" "background acquire announces the isolated default"
assert_contains "$("$POOL" env --worktree "$WT_A")" "export OMI_SKIP_AUTH_SEED='1'" "background default is isolated"
# an explicit --auth always wins over the session-derived default
"$POOL" release --quiet --worktree "$WT_A"
OMI_E2E_POOL_MANAGER_NAME=Background "$POOL" acquire --quiet --worktree "$WT_A" --auth shared >/dev/null
if printf '%s' "$("$POOL" env --worktree "$WT_A")" | grep -q OMI_SKIP_AUTH_SEED; then
  fail "explicit --auth shared must win over the background default"
fi
# a background refresh of a shared slot flips it to isolated: seeding cannot
# succeed there, and the slot keeps whatever session it already has
OMI_E2E_POOL_MANAGER_NAME=Background "$POOL" acquire --quiet --worktree "$WT_A" >/dev/null 2>&1
assert_contains "$("$POOL" env --worktree "$WT_A")" "OMI_SKIP_AUTH_SEED" "background refresh flips a shared slot to isolated"
# an Aqua session keeps the documented shared default
"$POOL" release --quiet --worktree "$WT_A"
"$POOL" acquire --quiet --worktree "$WT_A" --auth shared >/dev/null
if printf '%s' "$("$POOL" env --worktree "$WT_A")" | grep -q OMI_SKIP_AUTH_SEED; then
  fail "an Aqua acquire must keep explicit shared auth"
fi
"$POOL" release --quiet --worktree "$WT_A"

# ── launch policy: run wraps ./run.sh with --fast-only by default ──────────
mkdir -p "$TMP/bin"
cat >"$TMP/bin/run.sh" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "$@"
SH
chmod +x "$TMP/bin/run.sh"
out="$("$POOL" run --worktree "$WT_A" -- "$TMP/bin/run.sh" --yolo)"
assert_eq "$(printf '%s\n' "$out" | tail -1)" "--fast-only" "run injects --fast-only into a bare run.sh"
assert_contains "$out" "--yolo" "run keeps the caller own arguments"
out="$("$POOL" run --worktree "$WT_A" -- "$TMP/bin/run.sh" --yolo --fast-only)"
assert_eq "$(printf '%s\n' "$out" | grep -c -- --fast-only)" "1" "run does not duplicate an explicit --fast-only"
out="$("$POOL" run --worktree "$WT_A" -- "$TMP/bin/run.sh" --yolo --full)"
if printf '%s' "$out" | grep -q -- --fast-only; then
  fail "run must not inject --fast-only beside an explicit --full"
fi
assert_contains "$out" "--full" "run keeps an explicit --full for run.sh to validate"
out="$(OMI_FORCE_FULL_BUNDLE=1 "$POOL" run --worktree "$WT_A" -- "$TMP/bin/run.sh" --yolo)"
if printf '%s' "$out" | grep -q -- --fast-only; then
  fail "run must not inject --fast-only when OMI_FORCE_FULL_BUNDLE=1"
fi
"$POOL" release --quiet --worktree "$WT_A"

# ── launch policy: run.sh refuses an explicit --full on a reusable slot ────
# The fingerprint-aware decision lives in run.sh as a pure function so this
# hermetic suite can drive it directly, the way test-prepare-local-dev-
# entitlements.sh drives the classifier bodies of run.sh itself.
RUN_SH="$MACOS_DIR/run.sh"
guard_body="$(sed -n "/^omi_pool_refuses_explicit_full()/,/^}/p" "$RUN_SH")"
[ -n "$guard_body" ] || fail "run.sh must define omi_pool_refuses_explicit_full()"
eval "$guard_body"
if ! omi_pool_refuses_explicit_full 1 reusable 1; then fail "explicit --full must be refused on a reusable pool slot"; fi
if omi_pool_refuses_explicit_full 1 fast_fingerprint_mismatch 1; then fail "a fingerprint-required full rebuild must be allowed"; fi
if omi_pool_refuses_explicit_full 1 no_installed_bundle 1; then fail "a first build must be allowed"; fi
if omi_pool_refuses_explicit_full 1 incomplete_runtime_payload 1; then fail "an incomplete runtime payload must be allowed to rebuild"; fi
if omi_pool_refuses_explicit_full 1 reusable 0; then fail "an internally forced full rebuild (rewind reseed) must be allowed"; fi
if omi_pool_refuses_explicit_full "" reusable 1; then fail "a non-pool named bundle may be rebuilt on request"; fi

assert_file_contains "$RUN_SH" 'E2E_POOL_SLOT="$("$SCRIPT_DIR/scripts/omi-e2e-pool" verify "$APP_SLUG")"' F \
  "run.sh must capture the pool slot from verify"
assert_file_contains "$RUN_SH" 'omi_pool_refuses_explicit_full "${E2E_POOL_SLOT:-}"' F \
  "the full-bundle decision must consult the pool guard"
assert_file_contains "$RUN_SH" "keeping the existing session of E2E pool slot" "" \
  "an empty auth dump on a pool slot keeps its session instead of launching cold"
assert_file_contains "$RUN_SH" "Launching cold" "" "non-pool bundles keep the cold-launch warning"

# ── check: the permissions preflight fails closed on a signed-out slot ─────
# omi-ctl reaches the bridge with curl, so a fixture-fed curl stub keeps this
# hermetic: no app, no bridge, no /Applications.
mkdir -p "$TMP/checkbin"
cat >"$TMP/checkbin/curl" <<'SH'
#!/usr/bin/env bash
cat "${OMI_E2E_POOL_CHECK_FIXTURE:?}"
SH
chmod +x "$TMP/checkbin/curl"
write_check_fixture() {
  python3 - "$1" "$2" "$3" <<'PY'
import json, sys

path, signed_in, microphone = sys.argv[1:]
json.dump({"ok": True, "result": {"action": "permissions_snapshot",
           "detail": {"microphone": microphone, "screen_recording": "granted",
                      "accessibility": "granted"},
           "state": {"isSignedIn": signed_in == "true"}}},
          open(path, "w", encoding="utf-8"))
PY
}
write_check_fixture "$TMP/check-ok.json" true granted
write_check_fixture "$TMP/check-out.json" false granted
write_check_fixture "$TMP/check-mic.json" true not_granted
printf 'gateway timeout\n' >"$TMP/check-dead.json"

run_check() {
  OMI_AUTOMATION_TOKEN=test-token \
  OMI_E2E_POOL_CHECK_FIXTURE="$1" \
  PATH="$TMP/checkbin:$PATH" \
    "$POOL" check --slot 1
}
run_check "$TMP/check-ok.json" >/dev/null
set +e
run_check "$TMP/check-out.json" >"$TMP/check.out" 2>"$TMP/check.err"
check_rc=$?
run_check "$TMP/check-mic.json" >/dev/null 2>&1
mic_rc=$?
run_check "$TMP/check-dead.json" >/dev/null 2>&1
dead_rc=$?
set -e
assert_eq "$check_rc" "2" "a signed-out slot fails check (exit 2, the TCC class)"
assert_contains "$(cat "$TMP/check.err")" "signed out" "the signed-out failure says so"
assert_contains "$(cat "$TMP/check.err")" "Keychain" "the signed-out failure warns against keychain reset"
assert_eq "$mic_rc" "2" "a missing grant still fails check (exit 2)"
assert_eq "$dead_rc" "1" "an unanswering slot still dies (exit 1)"

echo "PASS: omi-e2e-pool lease contract"
