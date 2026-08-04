#!/usr/bin/env bash

omi_python_desktop_backend_binary() {
    local backend_dir="$1"
    printf '%s\n' "$backend_dir/.venv/bin/uvicorn"
}

omi_python_desktop_backend_sources_are_stale() {
    local backend_dir="$1"
    local pidfile="$2"

    [ -f "$pidfile" ] || return 0
    find "$backend_dir" \
        -path "$backend_dir/.venv" -prune -o \
        \( -name '*.py' -o -name 'requirements*.txt' -o -name 'pylock*.toml' \) \
        -type f -newer "$pidfile" -print -quit | grep -q .
}

omi_python_desktop_backend_config_is_newer() {
    local backend_dir="$1"
    local pidfile="$2"
    [ -f "$backend_dir/.env" ] && { [ ! -f "$pidfile" ] || [ "$backend_dir/.env" -nt "$pidfile" ]; }
}

omi_python_desktop_backend_read_pid() {
    local pidfile="$1"
    [ -f "$pidfile" ] || return 1
    local pid
    pid="$(cat "$pidfile" 2>/dev/null)"
    [[ "$pid" =~ ^[1-9][0-9]*$ ]] || return 1
    printf '%s\n' "$pid"
}

omi_python_desktop_backend_pid_is_alive() {
    local pidfile="$1"
    local pid
    pid="$(omi_python_desktop_backend_read_pid "$pidfile")" || return 1
    kill -0 "$pid" 2>/dev/null
}

omi_python_desktop_backend_pid_listens_on_port() {
    local pid="$1"
    local port="$2"
    lsof -a -p "$pid" -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
}

omi_python_desktop_backend_health_check() {
    local port="$1"
    curl --connect-timeout 1 --max-time 1 --fail --silent \
        "http://127.0.0.1:$port/health" >/dev/null
}

omi_python_desktop_backend_process_start() {
    local pid="$1"
    ps -o lstart= -p "$pid" 2>/dev/null | sed 's/^[[:space:]]*//'
}

omi_python_desktop_backend_metadata_value() {
    local metadata="$1"
    local key="$2"
    sed -n "s/^${key}=//p" "$metadata" | head -1
}

omi_python_desktop_backend_pid_matches_metadata() {
    local metadata="$1"
    local pid="$2"
    local recorded_start actual_start

    [ -f "$metadata" ] || return 1
    [ "$(omi_python_desktop_backend_metadata_value "$metadata" pid)" = "$pid" ] || return 1
    recorded_start="$(omi_python_desktop_backend_metadata_value "$metadata" pid_start)"
    actual_start="$(omi_python_desktop_backend_process_start "$pid")" || return 1
    [ -n "$recorded_start" ] && [ "$recorded_start" = "$actual_start" ]
}

omi_python_desktop_backend_metadata_matches() {
    local metadata="$1"
    local port="$2"
    [ -f "$metadata" ] && [ "$(omi_python_desktop_backend_metadata_value "$metadata" port)" = "$port" ]
}

omi_python_desktop_backend_write_metadata() {
    local metadata="$1"
    local port="$2"
    local pid="$3"
    local process_start temporary

    process_start="$(omi_python_desktop_backend_process_start "$pid")" || return 1
    [ -n "$process_start" ] || return 1
    mkdir -p "$(dirname "$metadata")"
    temporary="$(mktemp "${metadata}.tmp.XXXXXX")"
    {
        printf 'version=1\n'
        printf 'port=%s\n' "$port"
        printf 'pid=%s\n' "$pid"
        printf 'pid_start=%s\n' "$process_start"
    } > "$temporary"
    mv -f "$temporary" "$metadata"
}

omi_python_desktop_backend_stop_owned() {
    local pidfile="$1"
    local metadata="$2"
    local pid attempt

    pid="$(omi_python_desktop_backend_read_pid "$pidfile")" || {
        rm -f "$pidfile" "$metadata"
        return 0
    }
    if kill -0 "$pid" 2>/dev/null; then
        if ! omi_python_desktop_backend_pid_matches_metadata "$metadata" "$pid"; then
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
