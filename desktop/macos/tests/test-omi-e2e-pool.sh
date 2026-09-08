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
assert_contains() { printf '%s' "$1" | grep -q -- "$2" || fail "${3:-} expected output to contain '$2':
$1"; }

TMP="$(mktemp -d "${TMPDIR:-/tmp}/omi-e2e-pool-test.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

export OMI_E2E_POOL_DIR="$TMP/pool"
export OMI_E2E_POOL_APPLICATIONS_DIR="$TMP/apps"
export OMI_E2E_POOL_SIZE=2
export OMI_E2E_POOL_STALE=3600
unset OMI_E2E_POOL_WORKTREE OMI_E2E_POOL_TOKEN OMI_E2E_POOL_SIGN_IDENTITY 2>/dev/null || true
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

# ── acquire: first free slot, env, verify from the holder ──────────────────
slot="$("$POOL" acquire --quiet --worktree "$WT_A" --holder lane-a)"
assert_eq "$slot" "1" "first acquire takes slot 1"
[ -f "$WT_A/.dev/e2e-pool.env" ] || fail "acquire must write the worktree env file"
env_out="$("$POOL" env --worktree "$WT_A")"
assert_contains "$env_out" "export OMI_APP_NAME='omi-e2e-1'" "env app name"
assert_contains "$env_out" "export OMI_AUTOMATION_PORT='47701'" "env bridge port"
assert_contains "$env_out" "export PORT='10101'" "env backend port"
assert_contains "$env_out" "export OMI_SIGN_IDENTITY='Omi Local Dev Signing'" "env pins the default identity"
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
"$POOL" release --quiet --worktree "$WT_B"
[ ! -f "$WT_B/.dev/e2e-pool.env" ] || fail "release must remove the worktree env file"
assert_eq "$("$POOL" acquire --quiet --worktree "$WT_C" --holder lane-c)" "2" "released slot is reusable"
"$POOL" release --quiet --slot 2
"$POOL" release --quiet --worktree "$WT_B" >/dev/null   # nothing held: not an error

# ── zero-padded --slot values address the canonical slot ───────────────────
assert_eq "$("$POOL" acquire --quiet --worktree "$WT_C" --slot 02)" "2" "--slot 02 canonicalizes to slot 2"
[ -f "$OMI_E2E_POOL_DIR/slots/2/lease" ] || fail "--slot 02 must lease the canonical slots/2 directory"
[ ! -e "$OMI_E2E_POOL_DIR/slots/02" ] || fail "no padded slot directory may be created"
"$POOL" release --quiet --slot 02
[ ! -f "$OMI_E2E_POOL_DIR/slots/2/lease" ] || fail "--slot 02 must release canonical slot 2"

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
assert_eq "$("$POOL" acquire --quiet --worktree "$WT_A" --holder lane-a)" "1" "a deleted-env lease is reclaimable"

# ── liveness: a dead holder pid gives its slot up ─────────────────────────
"$POOL" release --quiet --slot 1
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
"$POOL" release --quiet --slot 1
"$POOL" acquire --quiet --worktree "$WT_A" --auth isolated >/dev/null
env_out="$("$POOL" env --worktree "$WT_A")"
assert_contains "$env_out" "export OMI_SKIP_AUTH_SEED='1'" "isolated slot skips the Omi Dev auth clone"
assert_contains "$env_out" "export OMI_SKIP_REWIND_SEED='1'" "isolated slot skips the Rewind clone"
"$POOL" release --quiet --slot 1
"$POOL" acquire --quiet --worktree "$WT_B" >/dev/null
assert_contains "$("$POOL" env --worktree "$WT_B")" "OMI_SKIP_AUTH_SEED" "auth mode sticks to the slot, not the holder"
assert_contains "$("$POOL" status)" "auth=isolated" "status shows the slot auth mode"
if "$POOL" acquire --quiet --worktree "$WT_B" --auth bogus >/dev/null 2>&1; then fail "auth mode must be validated"; fi
"$POOL" release --quiet --slot 1

# ── identity is pinned at slot creation; a later override does not move it ─
out="$(OMI_E2E_POOL_SIGN_IDENTITY="Apple Development: Someone" "$POOL" acquire --worktree "$WT_A" 2>&1)"
assert_contains "$out" "WARNING slot 1 is pinned" "identity change is refused loudly"
assert_contains "$("$POOL" env --worktree "$WT_A")" "OMI_SIGN_IDENTITY='Omi Local Dev Signing'" "pinned identity survives"
"$POOL" release --quiet --slot 1
# Slot 3 has never been created: growing the pool is how a never-used slot appears.
fresh="$(OMI_E2E_POOL_SIZE=3 OMI_E2E_POOL_SIGN_IDENTITY="Apple Development: Someone" "$POOL" acquire --quiet --worktree "$WT_A" --slot 3)"
assert_eq "$fresh" "3"
assert_contains "$(OMI_E2E_POOL_SIZE=3 "$POOL" env --worktree "$WT_A")" "OMI_SIGN_IDENTITY='Apple Development: Someone'" "a fresh slot pins the requested identity"
OMI_E2E_POOL_SIZE=3 "$POOL" release --quiet --slot 3

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

echo "PASS: omi-e2e-pool lease contract"
