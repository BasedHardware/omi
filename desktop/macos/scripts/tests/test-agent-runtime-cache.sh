#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source-path=SCRIPTDIR
# shellcheck source=../agent-runtime-cache.sh
source "$SCRIPT_DIR/../agent-runtime-cache.sh"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

assert_eq() {
  [ "$1" = "$2" ] || fail "expected '$2', got '$1'"
}

TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/agent-runtime-cache-test.XXXXXX")"
trap 'rm -rf "$TMP_ROOT"' EXIT
mkdir -p "$TMP_ROOT/inputs/src" "$TMP_ROOT/outputs/nested" "$TMP_ROOT/outputs/targets"
printf 'lock-v1\n' >"$TMP_ROOT/inputs/package-lock.json"
printf 'source-v1\n' >"$TMP_ROOT/inputs/src/index.ts"
printf 'runtime-v1\n' >"$TMP_ROOT/outputs/sentinel.js"
printf 'ordinary-v1\n' >"$TMP_ROOT/outputs/nested/ordinary-runtime.dat"
printf 'target-one\n' >"$TMP_ROOT/outputs/targets/one"
printf 'target-two\n' >"$TMP_ROOT/outputs/targets/two"
ln -s targets/one "$TMP_ROOT/outputs/runtime-link"

CHECKSUM_FILE="$TMP_ROOT/checksum-file"
printf 'checksum-v1\n' >"$CHECKSUM_FILE"
CHECKSUM="$(arc_sha256_file "$CHECKSUM_FILE")"
arc_file_matches_sha256 "$CHECKSUM_FILE" "$CHECKSUM" || fail "valid checksum file did not match"
printf 'checksum-corrupt\n' >"$CHECKSUM_FILE"
if arc_file_matches_sha256 "$CHECKSUM_FILE" "$CHECKSUM"; then
  fail "corrupt checksum file reported a match"
fi

CACHE_ARCHIVE="$TMP_ROOT/cache/archive.tar.gz"
RESTORED_ARCHIVE="$TMP_ROOT/restored/archive.tar.gz"
mkdir -p "$(dirname "$CACHE_ARCHIVE")" "$(dirname "$RESTORED_ARCHIVE")"
printf 'cached-archive-v1\n' >"$CACHE_ARCHIVE"
ARCHIVE_CHECKSUM="$(arc_sha256_file "$CACHE_ARCHIVE")"
arc_restore_verified_cache_file "$CACHE_ARCHIVE" "$ARCHIVE_CHECKSUM" "$RESTORED_ARCHIVE" || fail "valid cached archive did not restore"
assert_eq "$(cat "$RESTORED_ARCHIVE")" "cached-archive-v1"
printf 'cached-archive-corrupt\n' >"$CACHE_ARCHIVE"
printf 'destination-must-remain\n' >"$RESTORED_ARCHIVE"
if arc_restore_verified_cache_file "$CACHE_ARCHIVE" "$ARCHIVE_CHECKSUM" "$RESTORED_ARCHIVE"; then
  fail "corrupt cached archive restored"
fi
assert_eq "$(cat "$RESTORED_ARCHIVE")" "destination-must-remain"

key_for() {
  local mode="$1"
  local node_version="$2"
  {
    printf 'mode=%s\nnode=%s\n' "$mode" "$node_version"
    arc_hash_paths "$TMP_ROOT/inputs/package-lock.json" "$TMP_ROOT/inputs/src"
  } | arc_sha256_stream
}

output_digest() {
  arc_hash_paths "$TMP_ROOT/outputs"
}

STAMP="$TMP_ROOT/cache/cache.stamp"
KEY="$(key_for universal v22.14.0)"
DIGEST="$(output_digest)"

assert_eq "$(arc_cache_policy "" 0 0)" "eligible"
assert_eq "$(arc_cache_policy true 0 0)" "bypass:CI clean preparation"
assert_eq "$(arc_cache_policy 1 0 0)" "bypass:CI clean preparation"
assert_eq "$(arc_cache_policy false 1 0)" "bypass:--skip-npm"
assert_eq "$(arc_cache_policy false 0 1)" "bypass:OMI_AGENT_RUNTIME_FORCE_REBUILD=1"

# Pruned optional packages must not leave broken npm launchers that make an
# otherwise valid packaged runtime fail its post-build symlink validation.
mkdir -p "$TMP_ROOT/bin-targets" "$TMP_ROOT/node_modules/.bin"
printf 'ok\n' >"$TMP_ROOT/bin-targets/valid-cli"
ln -s ../../bin-targets/valid-cli "$TMP_ROOT/node_modules/.bin/valid-cli"
ln -s ../missing-package/cli.js "$TMP_ROOT/node_modules/.bin/missing-cli"
arc_remove_broken_symlinks "$TMP_ROOT/node_modules/.bin"
[ -L "$TMP_ROOT/node_modules/.bin/valid-cli" ] || fail "valid npm launcher was removed"
[ ! -L "$TMP_ROOT/node_modules/.bin/missing-cli" ] || fail "broken npm launcher survived pruning"

if arc_cache_status "$STAMP" "$KEY" "$DIGEST"; then
  fail "missing stamp reported HIT"
fi
arc_write_stamp "$STAMP" "$KEY" "$DIGEST"
arc_cache_status "$STAMP" "$KEY" "$DIGEST" || fail "unchanged stamp reported MISS"

# A hit is decision-only: it must not rewrite or touch prepared outputs.
# GNU stat -f prints filesystem metadata before failing on the BSD format;
# capturing that output makes free-block changes look like file mutations.
file_mtime() {
  python3 -c 'import os, sys; print(os.stat(sys.argv[1]).st_mtime_ns)' "$1"
}
before_mtime="$(file_mtime "$TMP_ROOT/outputs/sentinel.js")"
sleep 1
arc_cache_status "$STAMP" "$KEY" "$(output_digest)" || fail "second unchanged check missed"
after_mtime="$(file_mtime "$TMP_ROOT/outputs/sentinel.js")"
assert_eq "$after_mtime" "$before_mtime"

# Source/lock, mode, and actual build toolchain metadata all participate.
printf 'source-v2\n' >"$TMP_ROOT/inputs/src/index.ts"
[ "$(key_for universal v22.14.0)" != "$KEY" ] || fail "source mutation did not invalidate key"
printf 'source-v1\n' >"$TMP_ROOT/inputs/src/index.ts"
printf 'lock-v2\n' >"$TMP_ROOT/inputs/package-lock.json"
[ "$(key_for universal v22.14.0)" != "$KEY" ] || fail "lock mutation did not invalidate key"
printf 'lock-v1\n' >"$TMP_ROOT/inputs/package-lock.json"
[ "$(key_for local v22.14.0)" != "$KEY" ] || fail "mode mutation did not invalidate key"
[ "$(key_for universal v22.15.0)" != "$KEY" ] || fail "toolchain mutation did not invalidate key"

# Content corruption or deletion of any copied output invalidates, even when the
# critical sentinel remains untouched.
printf 'ordinary-corrupt\n' >"$TMP_ROOT/outputs/nested/ordinary-runtime.dat"
if arc_cache_status "$STAMP" "$KEY" "$(output_digest)"; then
  fail "corrupt non-sentinel output reported HIT"
fi
printf 'ordinary-v1\n' >"$TMP_ROOT/outputs/nested/ordinary-runtime.dat"
rm -f "$TMP_ROOT/outputs/nested/ordinary-runtime.dat"
if arc_cache_status "$STAMP" "$KEY" "$(output_digest)"; then
  fail "missing non-sentinel output reported HIT"
fi
printf 'ordinary-v1\n' >"$TMP_ROOT/outputs/nested/ordinary-runtime.dat"

# Symlink metadata and targets are part of the copied output integrity digest.
rm "$TMP_ROOT/outputs/runtime-link"
ln -s targets/two "$TMP_ROOT/outputs/runtime-link"
if arc_cache_status "$STAMP" "$KEY" "$(output_digest)"; then
  fail "retargeted output symlink reported HIT"
fi
rm "$TMP_ROOT/outputs/runtime-link"
ln -s targets/one "$TMP_ROOT/outputs/runtime-link"

# Critical runtime sentinel corruption/deletion remains covered as well.
printf 'corrupt\n' >"$TMP_ROOT/outputs/sentinel.js"
if arc_cache_status "$STAMP" "$KEY" "$(output_digest)"; then
  fail "corrupt sentinel reported HIT"
fi
rm -f "$TMP_ROOT/outputs/sentinel.js"
if arc_cache_status "$STAMP" "$KEY" "$(output_digest)"; then
  fail "missing sentinel reported HIT"
fi

# Production removes an old stamp before preparation. A failed preparation can
# therefore never publish or retain a stamp for the failed attempt.
arc_write_stamp "$STAMP" "$KEY" "$DIGEST"
rm -f "$STAMP"
false || true
[ ! -e "$STAMP" ] || fail "failed preparation retained a stamp"

# Standalone invocations serialize their output/stamp critical section. Two
# real contender processes (each with its own pid and start stamp), a file
# barrier instead of a timing sleep, and overlap detected by the section itself
# rather than by the trace, which is kept as a diagnostic only.
LOCK="$TMP_ROOT/concurrent.lock.d"
TRACE="$TMP_ROOT/concurrent.trace"
CS_MARKER="$TMP_ROOT/concurrent.section"
BARRIER="$TMP_ROOT/concurrent.barrier"
mkdir -p "$BARRIER"

# shellcheck disable=SC2016 # expanded by the contender shell, not here
contender_script='
set -euo pipefail
source "$1"
name="$2"
lock="$3"
trace="$4"
cs_marker="$5"
barrier="$6"
touch "$barrier/ready-$name"
deadline=$((SECONDS + 20))
while [ ! -e "$barrier/release" ]; do
  [ "$SECONDS" -lt "$deadline" ] || exit 1
  sleep 0.01
done
arc_acquire_lock "$lock" 30 || exit 1
printf "%s-start\n" "$name" >>"$trace"
if ! (set -C; : >"$cs_marker") 2>/dev/null; then
  echo "FAIL: overlapping lock holders: $name" >&2
  exit 1
fi
printf "%s-end\n" "$name" >>"$trace"
rm "$cs_marker"
arc_release_lock "$lock"
'
bash -c "$contender_script" _ "$SCRIPT_DIR/../agent-runtime-cache.sh" one "$LOCK" "$TRACE" "$CS_MARKER" "$BARRIER" 2>"$TMP_ROOT/lock-one.log" &
contender_one=$!
bash -c "$contender_script" _ "$SCRIPT_DIR/../agent-runtime-cache.sh" two "$LOCK" "$TRACE" "$CS_MARKER" "$BARRIER" 2>"$TMP_ROOT/lock-two.log" &
contender_two=$!
# Wait for both contenders to be staged, then open the barrier together.
barrier_deadline=$((SECONDS + 20))
while [ ! -e "$BARRIER/ready-one" ] || [ ! -e "$BARRIER/ready-two" ]; do
  if [ "$SECONDS" -ge "$barrier_deadline" ]; then
    cat "$TMP_ROOT/lock-one.log" "$TMP_ROOT/lock-two.log" >&2
    fail "contenders did not reach the barrier"
  fi
  sleep 0.05
done
: >"$BARRIER/release"
contender_failed=0
wait "$contender_one" || contender_failed=1
wait "$contender_two" || contender_failed=1
if [ "$contender_failed" -ne 0 ]; then
  cat "$TMP_ROOT/lock-one.log" "$TMP_ROOT/lock-two.log" "$TRACE" >&2
  fail "lock contender failed"
fi
[ ! -d "$LOCK" ] || fail "contenders left the lock directory behind"

# A held lock must survive a record that cannot confirm the holder. The pid
# protocol read exactly that as staleness and deleted the live lock; the owner
# record must make the contender wait instead. The bare `pid` record stays in
# play because an in-flight older process may still write one.
held_lock="$TMP_ROOT/held.lock.d"
arc_acquire_lock "$held_lock" 5
dead_pid=999999
while kill -0 "$dead_pid" 2>/dev/null; do
  dead_pid=$((dead_pid - 1))
done
printf '%s\n' "$dead_pid" >"$held_lock/pid"
if bash -c 'source "$1"; arc_acquire_lock "$2" 1' _ "$SCRIPT_DIR/../agent-runtime-cache.sh" "$held_lock" 2>/dev/null; then
  fail "a contender evicted the live owner's lock"
fi
[ -f "$held_lock/owner" ] || fail "a waiting contender deleted the live owner record"
arc_release_lock "$held_lock"
[ ! -d "$held_lock" ] || fail "releasing the held lock left the directory behind"

# A stale reclaimer paused immediately before unlink must not erase a new
# owner's record at the reused pathname. The rm shim is a scheduling barrier;
# the other reclaimer and replacement holder use the real lock operations.
reused_lock="$TMP_ROOT/reused.lock.d"
mkdir "$reused_lock"
printf '%s\t%s\n' "$dead_pid" stale >"$reused_lock/owner"
# shellcheck disable=SC2016 # expanded by the reclaimer shell
bash -c '
  source "$1"
  ready="$3"
  release="$4"
  rm() {
    : >"$ready"
    deadline=$((SECONDS + 20))
    while [ ! -e "$release" ]; do
      [ "$SECONDS" -lt "$deadline" ] || return 1
      sleep 0.01
    done
    command rm "$@"
  }
  arc_recover_stale_lock "$2"
' _ "$SCRIPT_DIR/../agent-runtime-cache.sh" "$reused_lock" "$BARRIER/reclaim-ready" "$BARRIER/reclaim-release" &
reclaimer=$!
barrier_deadline=$((SECONDS + 20))
while [ ! -e "$BARRIER/reclaim-ready" ]; do
  [ "$SECONDS" -lt "$barrier_deadline" ] || fail "reclaimer did not reach unlink barrier"
  sleep 0.01
done
arc_recover_stale_lock "$reused_lock"
arc_acquire_lock "$reused_lock" 5
replacement_owner="$(cat "$reused_lock/owner")"
: >"$BARRIER/reclaim-release"
wait "$reclaimer" || true # rmdir must refuse the replacement's nonempty directory
[ -f "$reused_lock/owner" ] || fail "stale reclaimer deleted the replacement owner's record"
assert_eq "$(cat "$reused_lock/owner")" "$replacement_owner"
arc_release_lock "$reused_lock"
[ ! -d "$reused_lock" ] || fail "replacement holder left the lock directory behind"

# A live pid whose start stamp cannot currently be read is not a stale owner.
arc_acquire_lock "$held_lock" 5
if bash -c 'source "$1"; arc_process_start_stamp() { return 1; }; arc_lock_is_stale "$2"' _ "$SCRIPT_DIR/../agent-runtime-cache.sh" "$held_lock" 2>/dev/null; then
  fail "an unavailable start stamp evicted a live owner"
fi
arc_release_lock "$held_lock"
if bash -c 'source "$1"; arc_process_start_stamp() { return 1; }; arc_acquire_lock "$2" 1' _ "$SCRIPT_DIR/../agent-runtime-cache.sh" "$held_lock" 2>/dev/null; then
  fail "lock acquisition published an unverifiable owner"
fi
[ ! -d "$held_lock" ] || fail "failed owner identification left a lock directory"

# Release must match the complete identity, while a genuinely different start
# stamp on a live (reused) pid is recoverable.
arc_acquire_lock "$held_lock" 5
printf '%s\t%s\n' "$$" different-start >"$held_lock/owner"
arc_release_lock "$held_lock"
[ -f "$held_lock/owner" ] || fail "release deleted a different owner identity"
arc_acquire_lock "$held_lock" 5
assert_eq "$(cat "$held_lock/owner")" "$(printf '%s\t%s' "$$" "$(arc_process_start_stamp "$$")")"
arc_release_lock "$held_lock"

# A fresh ownerless directory protects mkdir -> owner publication. Age it
# explicitly instead of sleeping through the five-second floor.
ownerless_lock="$TMP_ROOT/ownerless.lock.d"
mkdir "$ownerless_lock"
if arc_lock_is_stale "$ownerless_lock"; then
  fail "fresh ownerless directory reported stale"
fi
python3 - "$ownerless_lock" <<'PY'
import os
import sys
import time
old = time.time() - 10
os.utime(sys.argv[1], (old, old))
PY
arc_acquire_lock "$ownerless_lock" 5
arc_release_lock "$ownerless_lock"

# A recorded owner whose pid is gone is still reclaimed, so an interrupted
# preparation cannot wedge every later run.
stale_pid=999999
while kill -0 "$stale_pid" 2>/dev/null; do
  stale_pid=$((stale_pid - 1))
done
stale_lock="$TMP_ROOT/stale-owner.lock.d"
mkdir -p "$stale_lock"
printf '%s\t%s\n' "$stale_pid" "Thu Jan  1 00:00:00 1970" >"$stale_lock/owner"
arc_acquire_lock "$stale_lock" 5
assert_eq "$(cut -f1 "$stale_lock/owner")" "$$"
arc_release_lock "$stale_lock"
[ ! -d "$stale_lock" ] || fail "released lock left the directory behind"

assert_eq "$(arc_node_runtime_cache_policy "" 0)" "reuse"
assert_eq "$(arc_node_runtime_cache_policy false 0)" "reuse"
assert_eq "$(arc_node_runtime_cache_policy true 0)" "direct"
assert_eq "$(arc_node_runtime_cache_policy 1 1)" "direct"
assert_eq "$(arc_node_runtime_cache_policy "" 1)" "refresh"
assert_eq "$(arc_node_runtime_cache_policy false 1)" "refresh"

runtime_material="$(printf 'schema=1\nmode=universal\nversion=%s\narm64=%s\nx64=%s\n' v22.19.0 aaa bbb)"
runtime_name="$(arc_node_runtime_cache_name v22.19.0 universal "$runtime_material")"
assert_eq "$runtime_name" "$(arc_node_runtime_cache_name v22.19.0 universal "$runtime_material")"
case "$runtime_name" in
  v22.19.0-universal-*) ;;
  *) fail "unexpected node runtime cache name: $runtime_name" ;;
esac
[ "$runtime_name" != "$(arc_node_runtime_cache_name v22.19.0 universal "${runtime_material}changed")" ] || fail "node runtime material did not change the cache name"
[ "$runtime_name" != "$(arc_node_runtime_cache_name v22.19.0 local "$runtime_material")" ] || fail "node runtime mode did not change the cache name"
runtime_file="$(arc_node_runtime_cache_file "$TMP_ROOT/node-runtime" v22.19.0 universal "$runtime_material")"
assert_eq "$runtime_file" "$TMP_ROOT/node-runtime/$runtime_name/node"

payload="$TMP_ROOT/clone-src.bin"
python3 - "$payload" <<'PY'
import sys
with open(sys.argv[1], "wb") as handle:
    handle.write(b"\0" * (4096 * 1024))
PY
arc_clone_or_copy_file "$payload" "$TMP_ROOT/clone-dst.bin"
cmp -s "$payload" "$TMP_ROOT/clone-dst.bin" || fail "clone-or-copy changed file bytes"
if [ "$(uname -s)" = "Darwin" ]; then
  arc_same_clone "$payload" "$TMP_ROOT/clone-dst.bin" || fail "same-directory stage did not share an APFS clone"
  cross_src="$TMP_ROOT/cross-src.bin"
  cross_dst="/tmp/omi-node-runtime-cross-$$.bin"
  src_vol="$(df -P "$payload" | awk 'NR==2 {print $1}')"
  dst_vol="$(df -P /tmp | awk 'NR==2 {print $1}')"
  if [ "$src_vol" != "$dst_vol" ]; then
    cp -f "$payload" "$cross_src"
    arc_clone_or_copy_file "$cross_src" "$cross_dst"
    if arc_same_clone "$cross_src" "$cross_dst"; then
      fail "cross-volume stage reported a shared clone"
    fi
    cmp -s "$cross_src" "$cross_dst" || fail "cross-volume fallback changed file bytes"
    rm -f "$cross_dst"
  fi
fi

# A missing parent must not spin: the lock helper creates it.
missing_parent_lock="$TMP_ROOT/missing-parent/node.lock.d"
arc_acquire_lock "$missing_parent_lock" 5
[ -d "$missing_parent_lock" ] || fail "lock helper did not create a missing parent"
arc_release_lock "$missing_parent_lock"
[ ! -d "$missing_parent_lock" ] || fail "lock helper left the lock directory behind"

# Same-volume APFS clones are allowed. A cross-volume destination, and a
# symlink whose target is on another volume, are refused. cp -c would still
# exit 0 in both refused cases.
if [ "$(uname -s)" = "Darwin" ]; then
  same_reason="$(arc_clone_block_reason "$payload" "$TMP_ROOT" || true)"
  [ -z "$same_reason" ] || fail "same-directory clone was refused: $same_reason"
  arc_can_clone "$payload" "$TMP_ROOT" || fail "arc_can_clone rejected a same-directory APFS path"

  data_dir="$(mktemp -d /private/tmp/omi-clone-data.XXXXXX)"
  data_file="$data_dir/payload.bin"
  cp -f "$payload" "$data_file"
  scratch_dev="$(stat -L -f '%d' "$payload")"
  data_dev="$(stat -L -f '%d' "$data_file")"
  if [ "$scratch_dev" != "$data_dev" ]; then
    cross_reason="$(arc_clone_block_reason "$payload" "$data_dir" || true)"
    [ -n "$cross_reason" ] || fail "cross-volume clone was allowed"
    arc_can_clone "$payload" "$data_dir" && fail "arc_can_clone allowed a cross-volume destination"
    case "$cross_reason" in
      different\ devices*) ;;
      *) fail "unexpected cross-volume reason: $cross_reason" ;;
    esac
    link_src="$TMP_ROOT/build-link"
    ln -s "$data_dir" "$link_src"
    link_reason="$(arc_clone_block_reason "$link_src" "$TMP_ROOT" || true)"
    [ -n "$link_reason" ] || fail "symlink onto another volume was treated as cloneable"
    same_data_reason="$(arc_clone_block_reason "$data_file" "$data_dir" || true)"
    [ -z "$same_data_reason" ] || fail "Data-volume paths were not cloneable: $same_data_reason"

    saved_cache_dir="${OMI_AGENT_RUNTIME_NODE_CACHE_DIR-}"
    saved_xdg="${XDG_CACHE_HOME-}"
    unset OMI_AGENT_RUNTIME_NODE_CACHE_DIR XDG_CACHE_HOME
    data_cache="$(arc_node_runtime_cache_dir "$data_dir")"
    assert_eq "$data_cache" "$HOME/Library/Caches/OmiDesktop/node-runtime"
    scratch_cache="$(arc_node_runtime_cache_dir "$TMP_ROOT")"
    case "$scratch_cache" in
      */.omi-cache/OmiDesktop/node-runtime) ;;
      *) fail "split layout did not select a volume-local cache: $scratch_cache" ;;
    esac
    scratch_cache_dev="$(stat -L -f '%d' "$(arc_existing_ancestor "$scratch_cache")")"
    [ "$scratch_cache_dev" = "$scratch_dev" ] || fail "volume-local cache is not on the source device"
    export OMI_AGENT_RUNTIME_NODE_CACHE_DIR="/explicit/node-runtime"
    assert_eq "$(arc_node_runtime_cache_dir "$TMP_ROOT")" "/explicit/node-runtime"
    if [ -n "$saved_cache_dir" ]; then
      export OMI_AGENT_RUNTIME_NODE_CACHE_DIR="$saved_cache_dir"
    else
      unset OMI_AGENT_RUNTIME_NODE_CACHE_DIR
    fi
    if [ -n "$saved_xdg" ]; then
      export XDG_CACHE_HOME="$saved_xdg"
    else
      unset XDG_CACHE_HOME
    fi
  fi
  rm -rf "$data_dir"
fi

reap_root="$TMP_ROOT/reap"
mkdir -p "$reap_root/run.dead" "$reap_root/run.live" "$reap_root/run.unowned" "$reap_root/run.notadir"
printf 'marker\n' >"$reap_root/run.dead/keep.txt"
printf 'marker\n' >"$reap_root/run.live/keep.txt"
printf 'marker\n' >"$reap_root/run.unowned/keep.txt"
dead_pid=999999
while kill -0 "$dead_pid" 2>/dev/null; do
  dead_pid=$((dead_pid - 1))
done
printf '%s\n' "$dead_pid" >"$reap_root/run.dead/owner.pid"
printf '%s\n' "$$" >"$reap_root/run.live/owner.pid"
arc_reap_dead_owner_dirs "$reap_root"
[ ! -d "$reap_root/run.dead" ] || fail "dead owner run was not reaped"
[ -d "$reap_root/run.live" ] || fail "live owner run was reaped"
[ -f "$reap_root/run.unowned/keep.txt" ] || fail "run without owner.pid was reaped"
[ -e "$reap_root/run.notadir" ] || fail "non-directory run entry was removed"

echo "agent runtime cache hermetic tests passed"
