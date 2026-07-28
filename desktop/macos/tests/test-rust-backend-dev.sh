#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$MACOS_DIR/scripts/rust-backend-dev.sh"

TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/omi-rust-backend-dev.XXXXXX")"
cleanup() {
  for pid in "${SLEEP_PID:-}" "${RECORDED_PID:-}" "${FOREIGN_PID:-}"; do
    if [[ -n "$pid" ]]; then
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
  done
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

start_blocking_process() {
  local fifo="$TMP_ROOT/$1.fifo"
  mkfifo "$fifo"
  cat "$fifo" >/dev/null &
  STARTED_PID=$!
}

BACKEND_DIR="$TMP_ROOT/Backend-Rust"
mkdir -p "$BACKEND_DIR/src" "$BACKEND_DIR/fixtures" "$BACKEND_DIR/templates" \
  "$BACKEND_DIR/target/debug" "$BACKEND_DIR/target/release"
printf '%s\n' 'fn main() {}' > "$BACKEND_DIR/src/main.rs"
printf '%s\n' 'fixture' > "$BACKEND_DIR/fixtures/default.sse"
printf '%s\n' 'template' > "$BACKEND_DIR/templates/callback.html"
printf '%s\n' '[package]' > "$BACKEND_DIR/Cargo.toml"
printf '%s\n' 'lock' > "$BACKEND_DIR/Cargo.lock"
printf '%s\n' '[toolchain]' > "$BACKEND_DIR/rust-toolchain.toml"

unset OMI_DESKTOP_BACKEND_RELEASE
test "$(omi_rust_backend_profile)" = "debug"
export OMI_DESKTOP_BACKEND_RELEASE=1
test "$(omi_rust_backend_profile)" = "release"
unset OMI_DESKTOP_BACKEND_RELEASE

DEBUG_BINARY="$(omi_rust_backend_binary "$BACKEND_DIR" debug)"
RELEASE_BINARY="$(omi_rust_backend_binary "$BACKEND_DIR" release)"
test "$DEBUG_BINARY" = "$BACKEND_DIR/target/debug/omi-desktop-backend"
test "$RELEASE_BINARY" = "$BACKEND_DIR/target/release/omi-desktop-backend"

omi_rust_backend_sources_are_stale "$BACKEND_DIR" "$DEBUG_BINARY"
printf '%s\n' 'binary' > "$DEBUG_BINARY"
touch -r "$BACKEND_DIR/src/main.rs" "$DEBUG_BINARY"
! omi_rust_backend_sources_are_stale "$BACKEND_DIR" "$DEBUG_BINARY"
# Avoid a wall-clock sleep: macOS timestamp resolution can otherwise make this
# indistinguishable from the binary's timestamp.
touch -t 209901010000 "$BACKEND_DIR/src/main.rs"
omi_rust_backend_sources_are_stale "$BACKEND_DIR" "$DEBUG_BINARY"
touch -t 210001010000 "$DEBUG_BINARY"
! omi_rust_backend_sources_are_stale "$BACKEND_DIR" "$DEBUG_BINARY"
touch -t 210101010000 "$BACKEND_DIR/fixtures/default.sse"
omi_rust_backend_sources_are_stale "$BACKEND_DIR" "$DEBUG_BINARY"
touch -t 210201010000 "$DEBUG_BINARY"
! omi_rust_backend_sources_are_stale "$BACKEND_DIR" "$DEBUG_BINARY"
touch -t 210301010000 "$BACKEND_DIR/templates/callback.html"
omi_rust_backend_sources_are_stale "$BACKEND_DIR" "$DEBUG_BINARY"

PIDFILE="$TMP_ROOT/rust-backend.pid"
METADATA="$TMP_ROOT/rust-backend.meta"
printf '%s\n' 'stale' > "$BACKEND_DIR/.env"
printf '%s\n' '1234' > "$PIDFILE"
touch -r "$BACKEND_DIR/.env" "$PIDFILE"
! omi_rust_backend_config_is_newer "$BACKEND_DIR" "$PIDFILE"
touch -t 209901010000 "$BACKEND_DIR/.env"
omi_rust_backend_config_is_newer "$BACKEND_DIR" "$PIDFILE"

start_blocking_process owned
SLEEP_PID="$STARTED_PID"
omi_rust_backend_write_metadata "$METADATA" debug "$DEBUG_BINARY" 10201 "$SLEEP_PID"
omi_rust_backend_metadata_matches "$METADATA" debug "$DEBUG_BINARY" 10201
! omi_rust_backend_metadata_matches "$METADATA" release "$DEBUG_BINARY" 10201
! omi_rust_backend_metadata_matches "$METADATA" debug "$DEBUG_BINARY" 10202
omi_rust_backend_owned_process_matches "$METADATA" "$SLEEP_PID" debug "$DEBUG_BINARY" 10201
! omi_rust_backend_owned_process_matches "$METADATA" "999999" debug "$DEBUG_BINARY" 10201
grep -qx 'profile=debug' "$METADATA"
! grep -q 'OMI_LOCAL_AUTH_PASSWORD\|OPENAI_API_KEY' "$METADATA"

printf '%s\n' "$SLEEP_PID" > "$PIDFILE"
omi_rust_backend_pid_is_alive "$PIDFILE"
# The helper intentionally terminates this fixture process; suppress Bash's
# expected job-termination diagnostic so successful test output stays useful.
omi_rust_backend_stop_owned "$PIDFILE" "$METADATA" 2>/dev/null
! omi_rust_backend_pid_is_alive "$PIDFILE"
test ! -e "$PIDFILE"
test ! -e "$METADATA"
unset SLEEP_PID

# A stale pidfile must never authorize killing an unrelated live process.
start_blocking_process recorded
RECORDED_PID="$STARTED_PID"
omi_rust_backend_write_metadata "$METADATA" debug "$DEBUG_BINARY" 10201 "$RECORDED_PID"
start_blocking_process foreign
FOREIGN_PID="$STARTED_PID"
printf '%s\n' "$FOREIGN_PID" > "$PIDFILE"
omi_rust_backend_stop_owned "$PIDFILE" "$METADATA" 2>/dev/null
kill -0 "$FOREIGN_PID" 2>/dev/null
test ! -e "$PIDFILE"
test ! -e "$METADATA"
kill "$RECORDED_PID" 2>/dev/null || true
wait "$RECORDED_PID" 2>/dev/null || true
unset RECORDED_PID
kill "$FOREIGN_PID" 2>/dev/null || true
wait "$FOREIGN_PID" 2>/dev/null || true
unset FOREIGN_PID

HEALTH_CURL_ARGS=()
curl() {
  HEALTH_CURL_ARGS=("$@")
  return 0
}
omi_rust_backend_health_check 10201
test "${HEALTH_CURL_ARGS[*]}" = "--connect-timeout 1 --max-time 1 --fail --silent http://127.0.0.1:10201/health"
curl() {
  return 22
}
! omi_rust_backend_health_check 10201

echo "rust backend dev lifecycle tests passed"
