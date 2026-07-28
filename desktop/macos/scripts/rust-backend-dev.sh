#!/usr/bin/env bash
# Sourceable lifecycle primitives for the worktree-owned local Rust backend.
# The launcher builds a candidate before it stops a healthy backend, so a Rust
# compile failure does not take down the Swift developer's current API server.

omi_rust_backend_profile() {
    case "${OMI_DESKTOP_BACKEND_RELEASE:-0}" in
        1|true|TRUE|yes|YES) printf '%s\n' "release" ;;
        *) printf '%s\n' "debug" ;;
    esac
}

omi_rust_backend_binary() {
    local backend_dir="$1"
    local profile="$2"
    printf '%s\n' "$backend_dir/target/$profile/omi-desktop-backend"
}

omi_rust_backend_sources_are_stale() {
    local backend_dir="$1"
    local binary="$2"
    local marker

    [ -f "$binary" ] || return 0
    # Keep this explicit rather than treating the whole crate tree as source:
    # target/log files should not rebuild the backend, while include_str! data
    # and Cargo configuration must. Add a new compile-time input here when one
    # is introduced outside these roots.
    for marker in src fixtures templates Cargo.toml Cargo.lock rust-toolchain.toml build.rs .cargo; do
        if [ -f "$backend_dir/$marker" ] && [ "$backend_dir/$marker" -nt "$binary" ]; then
            return 0
        fi
        if [ -d "$backend_dir/$marker" ] && find "$backend_dir/$marker" -type f -newer "$binary" -print -quit | grep -q .; then
            return 0
        fi
    done
    return 1
}

omi_rust_backend_config_is_newer() {
    local backend_dir="$1"
    local pidfile="$2"
    [ -f "$backend_dir/.env" ] && { [ ! -f "$pidfile" ] || [ "$backend_dir/.env" -nt "$pidfile" ]; }
}

omi_rust_backend_read_pid() {
    local pidfile="$1"
    [ -f "$pidfile" ] || return 1
    local pid
    pid="$(cat "$pidfile" 2>/dev/null)"
    [[ "$pid" =~ ^[1-9][0-9]*$ ]] || return 1
    printf '%s\n' "$pid"
}

omi_rust_backend_pid_is_alive() {
    local pidfile="$1"
    local pid
    pid="$(omi_rust_backend_read_pid "$pidfile")" || return 1
    kill -0 "$pid" 2>/dev/null
}

omi_rust_backend_pid_listens_on_port() {
    local pid="$1"
    local port="$2"
    lsof -a -p "$pid" -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
}

omi_rust_backend_health_check() {
    local port="$1"
    curl --connect-timeout 1 --max-time 1 --fail --silent \
        "http://127.0.0.1:$port/health" >/dev/null
}

omi_rust_backend_metadata_value() {
    local metadata="$1"
    local key="$2"
    sed -n "s/^${key}=//p" "$metadata" | head -1
}

omi_rust_backend_metadata_matches() {
    local metadata="$1"
    local profile="$2"
    local binary="$3"
    local port="$4"
    [ -f "$metadata" ] || return 1

    [ "$(omi_rust_backend_metadata_value "$metadata" profile)" = "$profile" ] \
        && [ "$(omi_rust_backend_metadata_value "$metadata" binary)" = "$binary" ] \
        && [ "$(omi_rust_backend_metadata_value "$metadata" port)" = "$port" ]
}

omi_rust_backend_process_start() {
    local pid="$1"
    ps -o lstart= -p "$pid" 2>/dev/null | sed 's/^[[:space:]]*//'
}

omi_rust_backend_pid_matches_metadata() {
    local metadata="$1"
    local pid="$2"
    local recorded_start actual_start

    [ -f "$metadata" ] || return 1
    [ "$(omi_rust_backend_metadata_value "$metadata" pid)" = "$pid" ] || return 1
    recorded_start="$(omi_rust_backend_metadata_value "$metadata" pid_start)"
    actual_start="$(omi_rust_backend_process_start "$pid")" || return 1
    [ -n "$recorded_start" ] && [ "$recorded_start" = "$actual_start" ]
}

omi_rust_backend_owned_process_matches() {
    local metadata="$1"
    local pid="$2"
    local profile="$3"
    local binary="$4"
    local port="$5"

    omi_rust_backend_metadata_matches "$metadata" "$profile" "$binary" "$port" || return 1
    omi_rust_backend_pid_matches_metadata "$metadata" "$pid"
}

omi_rust_backend_write_metadata() {
    local metadata="$1"
    local profile="$2"
    local binary="$3"
    local port="$4"
    local pid="$5"
    local process_start temporary

    process_start="$(omi_rust_backend_process_start "$pid")" || return 1
    [ -n "$process_start" ] || return 1

    mkdir -p "$(dirname "$metadata")"
    temporary="$(mktemp "${metadata}.tmp.XXXXXX")"
    {
        printf 'version=1\n'
        printf 'profile=%s\n' "$profile"
        printf 'binary=%s\n' "$binary"
        printf 'port=%s\n' "$port"
        printf 'pid=%s\n' "$pid"
        printf 'pid_start=%s\n' "$process_start"
    } > "$temporary"
    mv -f "$temporary" "$metadata"
}

omi_rust_backend_stop_owned() {
    local pidfile="$1"
    local metadata="$2"
    local pid attempt

    pid="$(omi_rust_backend_read_pid "$pidfile")" || {
        rm -f "$pidfile" "$metadata"
        return 0
    }
    if kill -0 "$pid" 2>/dev/null; then
        # PIDs are reused. Only signal the exact process that wrote this
        # worktree's metadata; on any mismatch discard stale bookkeeping and
        # leave the live process alone.
        if ! omi_rust_backend_pid_matches_metadata "$metadata" "$pid"; then
            rm -f "$pidfile" "$metadata"
            return 0
        fi
        kill "$pid" 2>/dev/null || true
        for attempt in {1..20}; do
            kill -0 "$pid" 2>/dev/null || break
            sleep 0.1
        done
        if kill -0 "$pid" 2>/dev/null; then
            kill -9 "$pid" 2>/dev/null || true
        fi
    fi
    rm -f "$pidfile" "$metadata"
}
