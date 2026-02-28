#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# Chaos Engineering Test: Audiobuffer Leak (PR #4826)
#
# Runs vulnerable and fixed pusher.py as local processes, drives header-101
# audio chunks for 30s, and compares audiobuffer growth.
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

TEST_DURATION="${TEST_DURATION:-30}"
PORT_VULN="${PORT_VULN:-18100}"
PORT_FIXED="${PORT_FIXED:-18101}"
CHUNK_SIZE="${CHUNK_SIZE:-16000}"
INTERVAL="${INTERVAL:-0.05}"

# Thresholds
MIN_GROWTH_BYTES="${MIN_GROWTH_BYTES:-3000000}"   # vuln must grow beyond this
MIN_SLOPE_BPS="${MIN_SLOPE_BPS:-50000}"           # vuln slope must exceed this
MAX_FIXED_BYTES="${MAX_FIXED_BYTES:-0}"           # fixed must stay at 0 bytes
MAX_FIXED_SLOPE_BPS="${MAX_FIXED_SLOPE_BPS:-1000}" # fixed slope must be near 0

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

log()  { echo -e "${CYAN}[chaos]${NC} $*"; }
ok()   { echo -e "${GREEN}[  OK ]${NC} $*"; }
fail() { echo -e "${RED}[FAIL]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }

VULN_PID=""
FIXED_PID=""

cleanup() {
    log "Cleaning up processes..."
    for pid in "$VULN_PID" "$FIXED_PID"; do
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            kill -9 "$pid" 2>/dev/null || true
            wait "$pid" 2>/dev/null || true
        fi
    done
}
trap cleanup EXIT

wait_for_server() {
    local port=$1
    local name=$2
    for i in $(seq 1 30); do
        if curl -s --max-time 1 "http://localhost:${port}/health" >/dev/null 2>&1; then
            return 0
        fi
        sleep 0.5
    done
    fail "Server ${name} on port ${port} not ready after 15s"
    return 1
}

run_phase() {
    local LABEL=$1
    local MODULE=$2
    local PORT=$3
    local DESC=$4

    echo ""
    echo -e "${BOLD}──────────────────────────────────────────────────────────${NC}"
    echo -e "${BOLD}  Phase ${LABEL}: ${DESC}${NC}"
    echo -e "${BOLD}──────────────────────────────────────────────────────────${NC}"
    echo ""

    cd "${SCRIPT_DIR}"
    PUSHER_MODULE="${MODULE}" python3 -m uvicorn harness_main:app \
        --host 0.0.0.0 --port "${PORT}" --log-level warning \
        > "/tmp/chaos-audiobuffer-${MODULE}.log" 2>&1 &
    local PID=$!

    if [[ "$LABEL" == "A" ]]; then
        VULN_PID=$PID
    else
        FIXED_PID=$PID
    fi

    log "Started ${MODULE} (PID ${PID}, port ${PORT})"
    wait_for_server "${PORT}" "${MODULE}"

    local OUT="/tmp/chaos-audiobuffer-${MODULE}.out"
    log "Running load generator for ${TEST_DURATION}s..."
    python3 "${SCRIPT_DIR}/load_generator.py" \
        --host localhost \
        --port "${PORT}" \
        --duration "${TEST_DURATION}" \
        --chunk-size "${CHUNK_SIZE}" \
        --interval "${INTERVAL}" \
        | tee "${OUT}"

    local RESULT_JSON
    RESULT_JSON="$(rg -m1 '^RESULT:' "${OUT}" | sed 's/^RESULT: //')"
    if [[ -z "${RESULT_JSON}" ]]; then
        fail "No RESULT line found for ${MODULE}"
        exit 1
    fi

    local RESULT_FILE="/tmp/chaos-audiobuffer-${MODULE}.json"
    echo "${RESULT_JSON}" > "${RESULT_FILE}"

    log "Stopping ${MODULE}..."
    kill -9 "${PID}" 2>/dev/null || true
    wait "${PID}" 2>/dev/null || true

}

run_phase "A" "pusher_vuln" "${PORT_VULN}" "Vulnerable (main branch)"
run_phase "B" "pusher_fixed" "${PORT_FIXED}" "Fixed (PR #4826)"

VULN_RESULT_FILE="/tmp/chaos-audiobuffer-pusher_vuln.json"
FIXED_RESULT_FILE="/tmp/chaos-audiobuffer-pusher_fixed.json"

V_MAX=$(python3 -c "import json; print(json.load(open('${VULN_RESULT_FILE}'))['max_audiobuffer_len'])")
V_SLOPE=$(python3 -c "import json; print(json.load(open('${VULN_RESULT_FILE}'))['slope_audiobuffer_bps'])")
F_MAX=$(python3 -c "import json; print(json.load(open('${FIXED_RESULT_FILE}'))['max_audiobuffer_len'])")
F_SLOPE=$(python3 -c "import json; print(json.load(open('${FIXED_RESULT_FILE}'))['slope_audiobuffer_bps'])")

echo ""
echo -e "${BOLD}──────────────────────────────────────────────────────────${NC}"
echo -e "${BOLD}  Summary${NC}"
echo -e "${BOLD}──────────────────────────────────────────────────────────${NC}"
echo ""
echo "Vulnerable max audiobuffer: ${V_MAX} bytes"
echo "Vulnerable slope:           ${V_SLOPE} bytes/sec"
echo "Fixed max audiobuffer:      ${F_MAX} bytes"
echo "Fixed slope:                ${F_SLOPE} bytes/sec"
echo ""

PASS=1
if (( V_MAX < MIN_GROWTH_BYTES )); then
    warn "Vulnerable growth below threshold (${V_MAX} < ${MIN_GROWTH_BYTES})"
    PASS=0
fi
if (( $(python3 -c "print(1 if float('${V_SLOPE}') < ${MIN_SLOPE_BPS} else 0)") )); then
    warn "Vulnerable slope below threshold (${V_SLOPE} < ${MIN_SLOPE_BPS})"
    PASS=0
fi
if (( F_MAX > MAX_FIXED_BYTES )); then
    warn "Fixed buffer grew (${F_MAX} > ${MAX_FIXED_BYTES})"
    PASS=0
fi
if (( $(python3 -c "print(1 if float('${F_SLOPE}') > ${MAX_FIXED_SLOPE_BPS} else 0)") )); then
    warn "Fixed slope above threshold (${F_SLOPE} > ${MAX_FIXED_SLOPE_BPS})"
    PASS=0
fi

if (( PASS == 1 )); then
    ok "PASS — Vulnerable grows, fixed stays flat"
else
    fail "FAIL — Thresholds not met"
    exit 1
fi
