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
before_mtime="$(stat -f %m "$TMP_ROOT/outputs/sentinel.js" 2>/dev/null || stat -c %Y "$TMP_ROOT/outputs/sentinel.js")"
sleep 1
arc_cache_status "$STAMP" "$KEY" "$(output_digest)" || fail "second unchanged check missed"
after_mtime="$(stat -f %m "$TMP_ROOT/outputs/sentinel.js" 2>/dev/null || stat -c %Y "$TMP_ROOT/outputs/sentinel.js")"
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

# Standalone invocations serialize their output/stamp critical section.
LOCK="$TMP_ROOT/concurrent.lock.d"
TRACE="$TMP_ROOT/concurrent.trace"
run_locked() {
  local name="$1"
  arc_acquire_lock "$LOCK" 5
  printf '%s-start\n' "$name" >>"$TRACE"
  sleep 0.2
  printf '%s-end\n' "$name" >>"$TRACE"
  arc_release_lock "$LOCK"
}
run_locked one &
pid_one=$!
run_locked two &
pid_two=$!
wait "$pid_one" "$pid_two"
trace="$(cat "$TRACE")"
case "$trace" in
  $'one-start\none-end\ntwo-start\ntwo-end'|$'two-start\ntwo-end\none-start\none-end') ;;
  *) fail "lock allowed interleaved critical sections: $trace" ;;
esac

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
