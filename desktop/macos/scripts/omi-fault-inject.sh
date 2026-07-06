#!/bin/bash
# omi-fault-inject.sh — stand up a local backend *fault* endpoint so the desktop app's
# failure paths can be exercised deterministically, without a live backend.
#
# The hermetic E2E harness is backend-only (Python); there is no desktop↔backend
# fault-injection recipe, so acceptance rows that assert graceful degradation —
# CHAT (backend 5xx → structured ChatErrorState), TASK (sortOrder sync failure
# surfaced/retried, not silent), transcription transport truthfulness — cannot be
# driven end-to-end. This script fills that gap: it runs a tiny local HTTP endpoint
# that fails on purpose, and you point a *named test bundle* at it via the documented
# backend-override env vars (DesktopBackendEnvironment.swift):
#
#   OMI_PYTHON_API_URL   → Python backend (chat, action-item sync, transcription relay)
#   OMI_DESKTOP_API_URL  → Rust backend
#   OMI_AUTH_API_URL     → auth backend
#
# Usage:
#   omi-fault-inject.sh start <mode> [--port N] [--latency-ms N]
#   omi-fault-inject.sh stop
#   omi-fault-inject.sh status
#   omi-fault-inject.sh url
#
# Modes:
#   error         every request → HTTP 500 (JSON body)            # generic backend 5xx
#   status:CODE   every request → HTTP CODE (e.g. status:503, status:429, status:401)
#   latency       every request → sleep --latency-ms (default 30000) then 200
#                                                                  # slow-backend / watchdog
#   reset         accept the socket then close it, no HTTP reply  # connection reset
#   refuse        bind nothing; print a URL to a closed port      # connection refused
#
# `start` prints a single `export OMI_FAULT_URL=…` line to stdout (human logs go to
# stderr), so it composes with eval:
#
#   eval "$(desktop/macos/scripts/omi-fault-inject.sh start error)"
#   OMI_SKIP_BACKEND=1 OMI_SKIP_TUNNEL=1 \
#     OMI_PYTHON_API_URL="$OMI_FAULT_URL" OMI_DESKTOP_API_URL="$OMI_FAULT_URL" \
#     OMI_APP_NAME=omi-fault ./run.sh
#   # …exercise the flow; assert the app surfaces a structured error, not a crash/silent no-op…
#   desktop/macos/scripts/omi-fault-inject.sh stop
#
# NEVER point a production bundle (com.omi.computer-macos / Omi Beta) at a fault URL.
set -euo pipefail

STATE_DIR="${OMI_FAULT_STATE_DIR:-${TMPDIR:-/tmp}/omi-fault-inject}"
PID_FILE="$STATE_DIR/pid"
META_FILE="$STATE_DIR/meta"
DEFAULT_PORT=47790
DEFAULT_LATENCY_MS=30000

log() { printf 'omi-fault-inject: %s\n' "$*" >&2; }
die() { log "$*"; exit 1; }

read_meta() { [ -f "$META_FILE" ] && cat "$META_FILE" || true; }

is_running() {
  [ -f "$PID_FILE" ] || return 1
  local pid; pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

cmd_stop() {
  if is_running; then
    local pid; pid="$(cat "$PID_FILE")"
    kill "$pid" 2>/dev/null || true
    log "stopped fault server (pid $pid)"
  else
    log "no fault server running"
  fi
  rm -f "$PID_FILE" "$META_FILE"
}

cmd_status() {
  if is_running; then
    log "running — $(read_meta) (pid $(cat "$PID_FILE"))"
  elif [ -f "$META_FILE" ]; then
    # refuse mode: active by design with no listener/pid.
    log "active — $(read_meta) (refuse: no listener by design)"
  else
    log "not running"
    return 1
  fi
}

cmd_url() {
  # META_FILE (not is_running) is the source of truth for the URL, so `url` works for
  # refuse mode too (which is intentionally pid-less).
  [ -f "$META_FILE" ] || die "not running (start one first)"
  # meta line: mode=<m> port=<p> url=<u>
  read_meta | sed -n 's/.* url=//p'
}

cmd_start() {
  local mode="${1:-}"; shift || true
  [ -n "$mode" ] || die "usage: omi-fault-inject.sh start <mode> [--port N] [--latency-ms N]"

  local port="$DEFAULT_PORT" latency_ms="$DEFAULT_LATENCY_MS"
  while [ $# -gt 0 ]; do
    case "$1" in
      --port) port="${2:?--port needs a value}"; shift 2 ;;
      --latency-ms) latency_ms="${2:?--latency-ms needs a value}"; shift 2 ;;
      *) die "unknown arg: $1" ;;
    esac
  done

  # Validate numerics up front — covers every mode (incl. refuse, which prints the port
  # into the eval'd export line) and turns a later false "port in use?" into a clear error.
  { [[ "$port" =~ ^[0-9]{1,5}$ ]] && [ "$port" -ge 1 ] && [ "$port" -le 65535 ]; } \
    || die "invalid --port: $port (1-65535)"
  [[ "$latency_ms" =~ ^[0-9]+$ ]] || die "invalid --latency-ms: $latency_ms"

  case "$mode" in
    error|latency|reset|refuse) ;;
    status:*) [[ "${mode#status:}" =~ ^[0-9]{3}$ ]] || die "status mode needs a 3-digit code, e.g. status:503" ;;
    *) die "unknown mode: $mode (error|status:CODE|latency|reset|refuse)" ;;
  esac

  if is_running; then die "already running — $(read_meta); stop it first"; fi
  mkdir -p "$STATE_DIR"

  local url="http://127.0.0.1:${port}"

  if [ "$mode" = "refuse" ]; then
    # Connection-refused is the absence of a listener — verify the port really is closed,
    # so we never hand the app a reachable (or worse, a real-backend) URL.
    if nc -z 127.0.0.1 "$port" 2>/dev/null; then
      die "port $port is already in use; refuse mode needs a closed port (try --port N)"
    fi
    # Nothing to run: record meta so status/url/stop behave, but there is no pid.
    : > "$PID_FILE"  # empty pid → is_running() false, but keeps stop() idempotent
    printf 'mode=%s port=%s url=%s\n' "$mode" "$port" "$url" > "$META_FILE"
    log "refuse mode: no listener on $port (connection refused). url below."
    printf 'export OMI_FAULT_URL=%s\n' "$url"
    return 0
  fi

  command -v python3 >/dev/null 2>&1 || die "python3 not found (needed for $mode mode)"

  # Embedded fault server. Reads program from stdin; argv = mode, port, latency_ms.
  python3 - "$mode" "$port" "$latency_ms" >/dev/null 2>&1 <<'PY' &
import sys, time, json, socket, struct, http.server, socketserver
mode, port, latency_ms = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])

if mode == "reset":
    # Abrupt backend drop: RST every connection on accept (SO_LINGER timeout 0 makes
    # close() send RST, not FIN), before reading the request. The client sees
    # "connection reset by peer" immediately rather than hanging. A raw TCP handler is
    # used (not BaseHTTPRequestHandler, whose keep-alive loop defers the close).
    class ResetHandler(socketserver.BaseRequestHandler):
        def handle(self):
            try:
                self.request.setsockopt(
                    socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
            except OSError:
                pass
            try:
                self.request.close()
            except OSError:
                pass

    class ResetServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        allow_reuse_address = True
        daemon_threads = True

    ResetServer(("127.0.0.1", port), ResetHandler).serve_forever()
    sys.exit(0)

class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _serve(self):
        if mode == "latency":
            time.sleep(latency_ms / 1000.0)
            code = 200
        elif mode.startswith("status:"):
            code = int(mode.split(":", 1)[1])
        else:  # error
            code = 500
        body = json.dumps({"error": "omi-fault-inject", "mode": mode, "code": code}).encode()
        # HEAD and bodiless status codes must not carry a body under HTTP/1.1 keep-alive,
        # or a strict client desyncs on the reused socket.
        if self.command == "HEAD" or code in (204, 304):
            body = b""
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = _serve
    def log_message(self, *args):  # silence per-request stderr noise
        pass

class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

Server(("127.0.0.1", port), Handler).serve_forever()
PY
  local pid=$!
  echo "$pid" > "$PID_FILE"
  printf 'mode=%s port=%s url=%s\n' "$mode" "$port" "$url" > "$META_FILE"

  # Confirm it actually bound (fail loud instead of leaving a dead pidfile).
  local ok=""
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    if ! kill -0 "$pid" 2>/dev/null; then break; fi
    case "$mode" in
      reset|latency)
        # reset never replies and latency delays the response past a short probe — for
        # both, a TCP accept is the correct readiness signal (an HTTP round-trip would
        # time out and falsely report "port in use").
        if nc -z 127.0.0.1 "$port" 2>/dev/null; then ok=1; break; fi ;;
      *)
        if curl -s -o /dev/null --max-time 1 "$url" 2>/dev/null; then ok=1; break; fi ;;
    esac
    sleep 0.2
  done
  if [ -z "$ok" ]; then
    cmd_stop >/dev/null 2>&1 || true
    die "fault server failed to bind on $port (port in use?)"
  fi

  log "started $mode on $url (pid $pid)"
  printf 'export OMI_FAULT_URL=%s\n' "$url"
}

main() {
  local cmd="${1:-help}"; shift || true
  case "$cmd" in
    start)  cmd_start "$@" ;;
    stop)   cmd_stop ;;
    status) cmd_status ;;
    url)    cmd_url ;;
    help|-h|--help)
      # Print the contiguous header comment block (skip the shebang; stop at the first
      # non-comment line) so help never spills into the script body.
      awk 'NR==1 {next} /^#/ {sub(/^# ?/, ""); print; next} {exit}' "$0"
      ;;
    *) die "unknown command: $cmd (start|stop|status|url|help)" ;;
  esac
}

main "$@"
