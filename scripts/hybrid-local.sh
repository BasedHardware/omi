#!/usr/bin/env bash
# Start or stop the hybrid local stack: omi-local-backend daemon + Omi Dev desktop.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMUX_SESSION="${OMI_HYBRID_LOCAL_TMUX_SESSION:-omi-hybrid-local}"
DEV_APP_NAME="${OMI_APP_NAME:-Omi Dev}"
DAEMON_HEALTH_WAIT_SECS="${OMI_DAEMON_HEALTH_WAIT_SECS:-180}"

export OMI_LOCAL_DAEMON_URL="${OMI_LOCAL_DAEMON_URL:-http://127.0.0.1:8765}"
export OMI_LOCAL_BACKEND_HOST="${OMI_LOCAL_BACKEND_HOST:-127.0.0.1}"
export OMI_LOCAL_BACKEND_PORT="${OMI_LOCAL_BACKEND_PORT:-8765}"
export OMI_LOCAL_BACKEND_DATA_DIR="${OMI_LOCAL_BACKEND_DATA_DIR:-/tmp/omi-local-mvp}"
export OMI_LOCAL_DAEMON_LOG="${OMI_LOCAL_DAEMON_LOG:-/tmp/omi-local-backend-dev.log}"
export OMI_LOCAL_ASR_FIXTURE_DIR="${OMI_LOCAL_ASR_FIXTURE_DIR:-/tmp/omi-local-asr-fixture}"

file_url_for_path() {
  python3 - "$1" <<'PY'
from pathlib import Path
import sys

print(Path(sys.argv[1]).resolve().as_uri())
PY
}

configure_local_asr_manifest() {
  if [ -n "${OMI_LOCAL_ASR_MANIFEST_URL:-}" ]; then
    return
  fi

  local fixture_manifest="${OMI_LOCAL_ASR_FIXTURE_DIR}/manifest.json"
  if [ -f "$fixture_manifest" ]; then
    OMI_LOCAL_ASR_MANIFEST_URL="$(file_url_for_path "$fixture_manifest")"
    export OMI_LOCAL_ASR_MANIFEST_URL
  fi
}

# Shared hybrid desktop env (matches local-mvp-runbook.md).
hybrid_desktop_env() {
  export OMI_DESKTOP_BACKEND_MODE=local
  export OMI_LOCAL_DAEMON_SUPERVISE=0
  export OMI_LOCAL_DAEMON_URL
  export OMI_LOCAL_BACKEND_PORT
  export OMI_PYTHON_API_URL="${OMI_PYTHON_API_URL:-http://omi-cloud-invalid:9001}"
  export OMI_DESKTOP_API_URL="${OMI_DESKTOP_API_URL:-http://omi-rust-invalid:9002}"
  configure_local_asr_manifest
}

local_daemon_health_ok() {
  curl -fsS "${OMI_LOCAL_DAEMON_URL}/health" >/dev/null 2>&1
}

daemon_port() {
  python3 - "$OMI_LOCAL_DAEMON_URL" <<'PY'
from urllib.parse import urlparse
import sys

parsed = urlparse(sys.argv[1])
print(parsed.port or 8765)
PY
}

kill_daemon_listeners() {
  local port
  port="$(daemon_port)"
  if command -v lsof >/dev/null 2>&1; then
    local pids
    pids="$(lsof -ti "tcp:${port}" -sTCP:LISTEN 2>/dev/null || true)"
    if [ -n "$pids" ]; then
      echo "Stopping local daemon listener(s) on port ${port}: ${pids}"
      # shellcheck disable=SC2086
      kill ${pids} 2>/dev/null || true
    fi
  fi
  if pgrep -x omi-local-backend >/dev/null 2>&1; then
    echo "Stopping omi-local-backend process(es)"
    pkill -x omi-local-backend 2>/dev/null || true
  fi
}

kill_dev_desktop() {
  if pgrep -f "${DEV_APP_NAME}.app" >/dev/null 2>&1; then
    echo "Stopping ${DEV_APP_NAME}.app"
    pkill -f "${DEV_APP_NAME}.app" 2>/dev/null || true
  fi
}

attach_tmux_session() {
  if [ "${OMI_HYBRID_LOCAL_ATTACH:-1}" = "0" ]; then
    echo "tmux session '${TMUX_SESSION}' is running (attach skipped)."
    echo "  tmux attach -t ${TMUX_SESSION}"
    return 0
  fi

  if [ -n "${TMUX:-}" ]; then
    echo "Switching tmux client to session '${TMUX_SESSION}'..."
    tmux switch-client -t "$TMUX_SESSION"
    return 0
  fi

  exec tmux attach -t "$TMUX_SESSION"
}

daemon_pane_command() {
  if local_daemon_health_ok; then
    cat <<EOF
cd "${ROOT_DIR}/desktop/local-backend"
echo '=== omi-local-backend already running ==='
echo "health: ${OMI_LOCAL_DAEMON_URL}/health"
echo 'Leave this pane open or run: make down-local'
exec bash -l
EOF
    return
  fi

  cat <<EOF
cd "${ROOT_DIR}/desktop/local-backend"
export OMI_LOCAL_BACKEND_HOST="${OMI_LOCAL_BACKEND_HOST}" \\
  OMI_LOCAL_BACKEND_PORT="${OMI_LOCAL_BACKEND_PORT}" \\
  OMI_LOCAL_BACKEND_DATA_DIR="${OMI_LOCAL_BACKEND_DATA_DIR}"
echo '=== omi-local-backend (hybrid daemon) ==='
echo "data_dir=\${OMI_LOCAL_BACKEND_DATA_DIR} port=\${OMI_LOCAL_BACKEND_PORT}"
exec cargo run
EOF
}

desktop_pane_command() {
  hybrid_desktop_env
  cat <<EOF
cd "${ROOT_DIR}/desktop"
export OMI_DESKTOP_BACKEND_MODE=local \\
  OMI_LOCAL_DAEMON_SUPERVISE=0 \\
  OMI_LOCAL_DAEMON_URL="${OMI_LOCAL_DAEMON_URL}" \\
  OMI_LOCAL_BACKEND_PORT="${OMI_LOCAL_BACKEND_PORT}" \\
  OMI_LOCAL_ASR_MANIFEST_URL="${OMI_LOCAL_ASR_MANIFEST_URL:-}" \\
  OMI_PYTHON_API_URL="${OMI_PYTHON_API_URL:-http://omi-cloud-invalid:9001}" \\
  OMI_DESKTOP_API_URL="${OMI_DESKTOP_API_URL:-http://omi-rust-invalid:9002}"
echo '=== Omi Dev desktop (hybrid local mode) ==='
echo "daemon=\${OMI_LOCAL_DAEMON_URL}"
if [ -n "\${OMI_LOCAL_ASR_MANIFEST_URL:-}" ]; then
  echo "local ASR manifest=\${OMI_LOCAL_ASR_MANIFEST_URL}"
else
  echo "local ASR manifest not configured; run: make local-asr-fixture"
fi
echo 'Waiting for local daemon /health...'
elapsed=0
until curl -fsS "\${OMI_LOCAL_DAEMON_URL}/health" >/dev/null 2>&1; do
  if [ "\$elapsed" -ge "${DAEMON_HEALTH_WAIT_SECS}" ]; then
    echo "ERROR: Timed out after ${DAEMON_HEALTH_WAIT_SECS}s waiting for \${OMI_LOCAL_DAEMON_URL}/health"
    echo 'Fix the daemon pane above, then re-run: make serve-local'
    exec bash -l
  fi
  sleep 1
  elapsed=\$((elapsed + 1))
done
SEED_SCRIPT="${ROOT_DIR}/desktop/local-backend/tools/seed_hybrid_defaults.sh"
if [ -x "\$SEED_SCRIPT" ]; then
  echo 'Seeding hybrid provider defaults (if unset)...'
  bash "\$SEED_SCRIPT" || echo 'Warning: hybrid provider seed failed (non-fatal)'
fi
echo 'Daemon healthy — starting ./run.sh (first Swift build can take several minutes)...'
RUN_LOG="\${OMI_HYBRID_DESKTOP_RUN_LOG:-/tmp/omi-hybrid-desktop-run.log}"
echo "run.sh output: \$RUN_LOG"
exec ./run.sh 2>&1 | tee "\$RUN_LOG"
EOF
}

serve_with_tmux() {
  local daemon_cmd desktop_cmd
  daemon_cmd="$(daemon_pane_command)"
  desktop_cmd="$(desktop_pane_command)"

  tmux new-session -d -s "$TMUX_SESSION" -n hybrid -c "${ROOT_DIR}/desktop/local-backend" bash -lc "$daemon_cmd"
  tmux split-window -v -t "${TMUX_SESSION}:0" -c "${ROOT_DIR}/desktop" bash -lc "$desktop_cmd"
  tmux select-pane -t "${TMUX_SESSION}:0.0"
  tmux set-option -t "$TMUX_SESSION" remain-on-exit on
}

serve_single_process() {
  echo "tmux not found; starting desktop/run.sh with daemon supervision."
  echo "Daemon log: ${OMI_LOCAL_DAEMON_LOG}"
  cd "${ROOT_DIR}/desktop"
  hybrid_desktop_env
  export OMI_LOCAL_DAEMON_SUPERVISE=1
  exec ./run.sh
}

cmd_up() {
  if command -v tmux >/dev/null 2>&1 && tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
    echo "tmux session '${TMUX_SESSION}' is already running."
    attach_tmux_session
    return 0
  fi

  if command -v tmux >/dev/null 2>&1; then
    if local_daemon_health_ok; then
      echo "Local daemon already healthy at ${OMI_LOCAL_DAEMON_URL} — starting desktop pane only in tmux."
    else
      echo "Starting hybrid local stack in tmux session '${TMUX_SESSION}'"
    fi
    echo "  top pane:    desktop/local-backend (or status if already running)"
    echo "  bottom pane: desktop/run.sh (Omi Dev, hybrid env)"
    echo "Teardown: make down-local"
    if [ -n "${TMUX:-}" ]; then
      echo ""
      echo "Note: you are already inside tmux; this will switch you to '${TMUX_SESSION}'."
      echo "      To start detached instead: OMI_HYBRID_LOCAL_ATTACH=0 make serve-local"
    fi
    serve_with_tmux
    attach_tmux_session
    return 0
  fi

  serve_single_process
}

cmd_down() {
  if command -v tmux >/dev/null 2>&1 && tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
    echo "Killing tmux session '${TMUX_SESSION}'"
    tmux kill-session -t "$TMUX_SESSION"
  fi
  kill_daemon_listeners
  kill_dev_desktop
  echo "Hybrid local stack stopped."
}

usage() {
  cat <<EOF
Usage: $(basename "$0") <up|down>

  up    Start hybrid local backend + desktop (tmux when available)
  down  Stop tmux session, local daemon, and Omi Dev.app

Environment (optional):
  OMI_HYBRID_LOCAL_TMUX_SESSION   tmux session name (default: omi-hybrid-local)
  OMI_HYBRID_LOCAL_ATTACH=0       start tmux detached (do not attach/switch)
  OMI_LOCAL_DAEMON_URL            daemon base URL (default: http://127.0.0.1:8765)
  OMI_LOCAL_BACKEND_DATA_DIR      SQLite data dir (default: /tmp/omi-local-mvp)
  OMI_DAEMON_HEALTH_WAIT_SECS       wait for /health (default: 180)
  OMI_APP_NAME                      desktop bundle name (default: Omi Dev)
  OMI_LOCAL_ASR_MANIFEST_URL        production-shaped local ASR add-on manifest URL
  OMI_LOCAL_ASR_FIXTURE_DIR         auto-detected fixture dir (default: /tmp/omi-local-asr-fixture)

See desktop/local-backend/docs/local-mvp-runbook.md
EOF
}

main() {
  case "${1:-}" in
    up) cmd_up ;;
    down) cmd_down ;;
    *)
      usage >&2
      exit 1
      ;;
  esac
}

main "$@"
