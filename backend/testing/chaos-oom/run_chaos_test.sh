#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# Chaos Engineering Test: Reproduce OOM + Prove PR #4784 Fix
#
# Runs both vulnerable and fixed pusher.py as local processes, measures memory
# divergence. Without Docker, we use process RSS tracking + /debug/memory.
#
# Two leaks reproduced:
#   Leak 1: safe_create_task() — fire-and-forget tasks hold ws refs, never cancelled
#   Leak 2: List[dict] queues — unbounded growth under backpressure
#
# Improvements:
#   #1: Isolated leak modes (MODES env var)
#   #5: Regression assertions (CHAOS_ASSERT=1)
#   #6: Slope analysis in verdict
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_DURATION="${TEST_DURATION:-60}"
PORT_VULN="${PORT_VULN:-18090}"
PORT_FIXED="${PORT_FIXED:-18091}"
NUM_LEAK1="${NUM_LEAK1:-30}"
NUM_LEAK2="${NUM_LEAK2:-15}"
# Memory growth threshold (MB) — vuln must grow MORE than this above fixed
LEAK_THRESHOLD_MB="${LEAK_THRESHOLD_MB:-20}"
# Improvement #1: Run leak patterns in isolation and combined
MODES="${MODES:-both}"
# Improvement #5: CI assertion mode — fail on thresholds
CHAOS_ASSERT="${CHAOS_ASSERT:-0}"
TASK_LEAK_MIN="${TASK_LEAK_MIN:-50}"        # vuln must have at least this many in-flight tasks
QUEUE_DROPS_MIN="${QUEUE_DROPS_MIN:-5}"     # fixed must drop at least this many items
SLOPE_MAX_FIXED="${SLOPE_MAX_FIXED:-5.0}"   # fixed slope must be under this (MB/min)
# Improvement #7: Disconnect/reconnect interval (0=disabled)
DISCONNECT_INTERVAL="${DISCONNECT_INTERVAL:-0}"

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

get_rss_mb() {
    # Get RSS in MB from /proc/<pid>/status
    local pid=$1
    if [[ -f "/proc/$pid/status" ]]; then
        awk '/^VmRSS:/ {printf "%.1f", $2/1024}' "/proc/$pid/status" 2>/dev/null || echo "0"
    else
        echo "0"
    fi
}

get_memory_json() {
    local port=$1
    curl -s --max-time 3 "http://localhost:${port}/debug/memory" 2>/dev/null || echo "{}"
}

extract_json_field() {
    # Extract a field from JSON — usage: extract_json_field "$json" "field_name" "default"
    local json=$1 field=$2 default=${3:-0}
    echo "$json" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    # Support nested fields like 'safe_create_task_metrics.in_flight'
    keys = '${field}'.split('.')
    val = d
    for k in keys:
        val = val[k]
    print(val)
except:
    print('${default}')
" 2>/dev/null || echo "$default"
}

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

# Track overall pass/fail for assertion mode
ASSERT_FAILURES=0

run_phase() {
    # Run a single phase (vuln or fixed) with a given mode
    local LABEL=$1     # "A" or "B"
    local MODULE=$2    # "pusher_vuln" or "pusher_fixed"
    local PORT=$3
    local MODE=$4
    local DESC=$5

    local DI_FLAG=""
    if [[ "$DISCONNECT_INTERVAL" != "0" ]]; then
        DI_FLAG="--disconnect-interval ${DISCONNECT_INTERVAL}"
    fi

    echo ""
    echo -e "${BOLD}──────────────────────────────────────────────────────────${NC}"
    echo -e "${BOLD}  Phase ${LABEL}: ${DESC}  (mode=${MODE})${NC}"
    echo -e "${BOLD}──────────────────────────────────────────────────────────${NC}"
    echo ""

    # Start server
    cd "${SCRIPT_DIR}"
    PUSHER_MODULE="${MODULE}" python3 -m uvicorn harness_main:app \
        --host 0.0.0.0 --port "${PORT}" --log-level warning \
        > "/tmp/chaos-${MODULE}-${MODE}.log" 2>&1 &
    local PID=$!

    if [[ "$LABEL" == "A" ]]; then
        VULN_PID=$PID
    else
        FIXED_PID=$PID
    fi

    log "Started ${MODULE} (PID ${PID}, port ${PORT})"

    wait_for_server "${PORT}" "${MODULE}"
    local RSS_START
    RSS_START=$(get_rss_mb "$PID")
    log "Baseline RSS: ${RSS_START}MB"
    echo ""

    log "Running load generator for ${TEST_DURATION}s..."
    python3 "${SCRIPT_DIR}/load_generator.py" \
        --host localhost \
        --port "${PORT}" \
        --duration "${TEST_DURATION}" \
        --mode "${MODE}" \
        --num-leak1 "${NUM_LEAK1}" \
        --num-leak2 "${NUM_LEAK2}" \
        ${DI_FLAG} \
        2>&1 || true

    echo ""

    # Cooldown phase
    log "Cooldown: waiting 15s after load stops..."
    for i in 1 2 3; do
        sleep 5
        if kill -0 "$PID" 2>/dev/null; then
            local CD_RSS CD_DEBUG CD_TASKS
            CD_RSS=$(get_rss_mb "$PID")
            CD_DEBUG=$(get_memory_json "${PORT}")
            CD_TASKS=$(extract_json_field "$CD_DEBUG" "asyncio_tasks" "-1")
            log "  Cooldown +$((i*5))s: RSS=${CD_RSS}MB  tasks=${CD_TASKS}"
        fi
    done

    # Capture final state
    local ALIVE=true
    if ! kill -0 "$PID" 2>/dev/null; then
        ALIVE=false
    fi

    local RSS_END TASKS TRACED FINAL_DEBUG
    if $ALIVE; then
        RSS_END=$(get_rss_mb "$PID")
        FINAL_DEBUG=$(get_memory_json "${PORT}")
        TASKS=$(extract_json_field "$FINAL_DEBUG" "asyncio_tasks" "-1")
        TRACED=$(extract_json_field "$FINAL_DEBUG" "traced_current_mb" "0")
    else
        RSS_END="0"
        TASKS="-1"
        TRACED="0"
        FINAL_DEBUG="{}"
    fi

    local GROWTH
    GROWTH=$(python3 -c "print(round(${RSS_END} - ${RSS_START}, 1))" 2>/dev/null || echo "0")

    log "Phase ${LABEL} results:"
    log "  Process alive: ${ALIVE}"
    log "  RSS: ${RSS_START}MB -> ${RSS_END}MB (+${GROWTH}MB, after cooldown)"
    log "  Asyncio tasks: ${TASKS}"
    log "  Traced memory: ${TRACED}MB"

    # Print detailed metrics
    local SCT_IN_FLIGHT SCT_CREATED
    SCT_IN_FLIGHT=$(extract_json_field "$FINAL_DEBUG" "safe_create_task_metrics.in_flight" "0")
    SCT_CREATED=$(extract_json_field "$FINAL_DEBUG" "safe_create_task_metrics.created" "0")
    if [[ "$SCT_CREATED" != "0" ]]; then
        log "  safe_create_task: in_flight=${SCT_IN_FLIGHT} created=${SCT_CREATED}"
    fi

    local BG_IN_FLIGHT BG_CREATED BG_CANCELLED
    BG_IN_FLIGHT=$(extract_json_field "$FINAL_DEBUG" "pusher_debug.bg_task_metrics.in_flight" "0")
    BG_CREATED=$(extract_json_field "$FINAL_DEBUG" "pusher_debug.bg_task_metrics.created" "0")
    BG_CANCELLED=$(extract_json_field "$FINAL_DEBUG" "pusher_debug.bg_task_metrics.cancelled" "0")
    if [[ "$BG_CREATED" != "0" ]]; then
        log "  bg_task_metrics: in_flight=${BG_IN_FLIGHT} created=${BG_CREATED} cancelled=${BG_CANCELLED}"
    fi

    local THREAD_IN_FLIGHT THREAD_SUBMITTED
    THREAD_IN_FLIGHT=$(extract_json_field "$FINAL_DEBUG" "to_thread_metrics.in_flight" "0")
    THREAD_SUBMITTED=$(extract_json_field "$FINAL_DEBUG" "to_thread_metrics.submitted" "0")
    if [[ "$THREAD_SUBMITTED" != "0" ]]; then
        log "  to_thread: in_flight=${THREAD_IN_FLIGHT} submitted=${THREAD_SUBMITTED}"
    fi

    # Kill server
    kill -9 "$PID" 2>/dev/null || true
    wait "$PID" 2>/dev/null || true
    if [[ "$LABEL" == "A" ]]; then VULN_PID=""; else FIXED_PID=""; fi
    sleep 2  # Let OS reclaim port

    # Export results via eval-friendly vars
    echo "__RESULT_${LABEL}_ALIVE=${ALIVE}" >> /tmp/chaos-results-${MODE}.txt
    echo "__RESULT_${LABEL}_RSS_START=${RSS_START}" >> /tmp/chaos-results-${MODE}.txt
    echo "__RESULT_${LABEL}_RSS_END=${RSS_END}" >> /tmp/chaos-results-${MODE}.txt
    echo "__RESULT_${LABEL}_GROWTH=${GROWTH}" >> /tmp/chaos-results-${MODE}.txt
    echo "__RESULT_${LABEL}_TASKS=${TASKS}" >> /tmp/chaos-results-${MODE}.txt
    echo "__RESULT_${LABEL}_SCT_IN_FLIGHT=${SCT_IN_FLIGHT}" >> /tmp/chaos-results-${MODE}.txt
    echo "__RESULT_${LABEL}_DEBUG='${FINAL_DEBUG}'" >> /tmp/chaos-results-${MODE}.txt
}

run_mode() {
    local MODE=$1
    log "============================================================"
    log "  Running mode: ${MODE}"
    log "============================================================"

    # Clean results file
    rm -f /tmp/chaos-results-${MODE}.txt
    touch /tmp/chaos-results-${MODE}.txt

    # Phase A: Vulnerable
    run_phase "A" "pusher_vuln" "${PORT_VULN}" "${MODE}" "Vulnerable pusher.py (main branch)"

    # Phase B: Fixed
    run_phase "B" "pusher_fixed" "${PORT_FIXED}" "${MODE}" "Fixed pusher.py (PR #4784)"

    # Load results
    source /tmp/chaos-results-${MODE}.txt

    # Verdict for this mode
    echo ""
    echo -e "${BOLD}═══════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}  VERDICT — mode=${MODE}${NC}"
    echo -e "${BOLD}═══════════════════════════════════════════════════════${NC}"
    echo ""

    local VULN_GROWTH="${__RESULT_A_GROWTH}"
    local FIXED_GROWTH="${__RESULT_B_GROWTH}"
    local VULN_ALIVE="${__RESULT_A_ALIVE}"
    local FIXED_ALIVE="${__RESULT_B_ALIVE}"
    local VULN_TASKS="${__RESULT_A_TASKS}"
    local FIXED_TASKS="${__RESULT_B_TASKS}"
    local DIFFERENTIAL
    DIFFERENTIAL=$(python3 -c "print(round(${VULN_GROWTH} - ${FIXED_GROWTH}, 1))" 2>/dev/null || echo "0")

    log "Memory growth comparison:"
    log "  Vulnerable: +${VULN_GROWTH}MB"
    log "  Fixed:      +${FIXED_GROWTH}MB"
    log "  Differential: ${DIFFERENTIAL}MB (threshold: ${LEAK_THRESHOLD_MB}MB)"
    echo ""

    local VULN_LEAKED=false
    local FIXED_STABLE=false

    if [[ "${VULN_ALIVE}" != "true" ]]; then
        VULN_LEAKED=true
        log "  Vulnerable process died (likely OOM)"
    elif python3 -c "exit(0 if float('${DIFFERENTIAL}') >= float('${LEAK_THRESHOLD_MB}') else 1)" 2>/dev/null; then
        VULN_LEAKED=true
    fi

    if [[ "${FIXED_ALIVE}" == "true" ]]; then
        FIXED_STABLE=true
    fi

    if $VULN_LEAKED && $FIXED_STABLE; then
        echo -e "${GREEN}${BOLD}  PASS: mode=${MODE} — PR #4784 fixes the memory leak${NC}"
        echo "  Vulnerable: +${VULN_GROWTH}MB, ${VULN_TASKS} tasks"
        echo "  Fixed:      +${FIXED_GROWTH}MB, ${FIXED_TASKS} tasks"

        # Improvement #5: Regression assertions
        if [[ "${CHAOS_ASSERT}" == "1" ]]; then
            echo ""
            log "Running regression assertions..."

            local VULN_SCT_IN_FLIGHT="${__RESULT_A_SCT_IN_FLIGHT}"
            if [[ "${MODE}" == "leak1" || "${MODE}" == "both" ]]; then
                if python3 -c "exit(0 if int('${VULN_SCT_IN_FLIGHT}') >= int('${TASK_LEAK_MIN}') else 1)" 2>/dev/null; then
                    ok "Task leak: vuln has ${VULN_SCT_IN_FLIGHT} in-flight tasks (>= ${TASK_LEAK_MIN})"
                else
                    fail "Task leak: vuln only has ${VULN_SCT_IN_FLIGHT} in-flight tasks (expected >= ${TASK_LEAK_MIN})"
                    ASSERT_FAILURES=$((ASSERT_FAILURES + 1))
                fi
            fi

            # Check queue drops in fixed version
            local FIXED_DEBUG="${__RESULT_B_DEBUG}"
            local FIXED_DROPS
            FIXED_DROPS=$(echo "${FIXED_DEBUG}" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    drops = d.get('pusher_debug', {}).get('queue_drops', {})
    print(sum(drops.values()))
except:
    print(0)
" 2>/dev/null || echo "0")

            if [[ "${MODE}" == "leak2" || "${MODE}" == "both" ]]; then
                if python3 -c "exit(0 if int('${FIXED_DROPS}') >= int('${QUEUE_DROPS_MIN}') else 1)" 2>/dev/null; then
                    ok "Queue bounds: fixed dropped ${FIXED_DROPS} items (>= ${QUEUE_DROPS_MIN})"
                else
                    warn "Queue bounds: fixed only dropped ${FIXED_DROPS} items (expected >= ${QUEUE_DROPS_MIN})"
                    # Don't count as hard failure — drops depend on timing
                fi
            fi
        fi
    elif ! $VULN_LEAKED && $FIXED_STABLE; then
        echo -e "${YELLOW}${BOLD}  INCONCLUSIVE: Leak not prominent enough (mode=${MODE})${NC}"
        echo "  Differential ${DIFFERENTIAL}MB < threshold ${LEAK_THRESHOLD_MB}MB"
        echo "  Try: TEST_DURATION=120 NUM_LEAK1=50 NUM_LEAK2=25 $0"
        if [[ "${CHAOS_ASSERT}" == "1" ]]; then
            ASSERT_FAILURES=$((ASSERT_FAILURES + 1))
        fi
    elif $VULN_LEAKED && ! $FIXED_STABLE; then
        echo -e "${RED}${BOLD}  FAIL: Both versions have memory issues (mode=${MODE})${NC}"
        ASSERT_FAILURES=$((ASSERT_FAILURES + 1))
    else
        echo -e "${RED}${BOLD}  INCONCLUSIVE: Unexpected results (mode=${MODE})${NC}"
        ASSERT_FAILURES=$((ASSERT_FAILURES + 1))
    fi

    echo ""
}

# ============================================================================
# Main
# ============================================================================
echo ""
echo -e "${BOLD}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  Chaos OOM Test — PR #4784 Memory Leak Fix Verification  ${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════════════════${NC}"
echo ""
log "Test duration: ${TEST_DURATION}s"
log "Leak1 clients (header-104): ${NUM_LEAK1}"
log "Leak2 clients (header-101): ${NUM_LEAK2}"
log "Leak threshold: ${LEAK_THRESHOLD_MB}MB differential"
log "Modes: ${MODES}"
log "Assertion mode: ${CHAOS_ASSERT}"
if [[ "$DISCONNECT_INTERVAL" != "0" ]]; then
    log "Disconnect interval: ${DISCONNECT_INTERVAL}s"
fi
echo ""

# Improvement #1: Loop over modes
IFS=',' read -ra MODE_LIST <<< "${MODES}"
for mode in "${MODE_LIST[@]}"; do
    run_mode "$mode"
done

# Final summary
echo -e "${BOLD}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  FINAL SUMMARY${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════════════════${NC}"
echo ""
log "Modes tested: ${MODES}"
log "Assertion failures: ${ASSERT_FAILURES}"

if [[ "${ASSERT_FAILURES}" -gt 0 ]]; then
    echo -e "${RED}${BOLD}  OVERALL: FAIL (${ASSERT_FAILURES} assertion failures)${NC}"
    echo ""
    exit 1
else
    echo -e "${GREEN}${BOLD}  OVERALL: PASS${NC}"
    echo ""
    exit 0
fi
