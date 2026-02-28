#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# Chaos Engineering Test: Thread Explosion vs ThreadPoolExecutor (PR #4827)
#
# Runs a minimal, standalone reproduction of the process_conversation
# background tasks. Compares vulnerable raw Thread().start() vs
# ThreadPoolExecutor(max_workers=32).
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CONVERSATIONS="${CONVERSATIONS:-50}"
SLEEP_MIN="${SLEEP_MIN:-2}"
SLEEP_MAX="${SLEEP_MAX:-5}"
MAX_WORKERS="${MAX_WORKERS:-32}"
SAMPLE_INTERVAL="${SAMPLE_INTERVAL:-0.05}"
LAUNCH_INTERVAL="${LAUNCH_INTERVAL:-0.005}"
SEED="${SEED:-4827}"

# Thresholds (used if CHAOS_ASSERT=1)
MIN_VULN_THREADS="${MIN_VULN_THREADS:-300}"
MAX_FIXED_THREADS="${MAX_FIXED_THREADS:-36}"
CHAOS_ASSERT="${CHAOS_ASSERT:-0}"

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

run_phase() {
    local LABEL=$1
    local MODE=$2
    local DESC=$3
    local OUT="/tmp/chaos-threadpool-${MODE}.out"

    echo ""
    echo -e "${BOLD}──────────────────────────────────────────────────────────${NC}"
    echo -e "${BOLD}  Phase ${LABEL}: ${DESC}${NC}"
    echo -e "${BOLD}──────────────────────────────────────────────────────────${NC}"
    echo ""

    log "Running ${MODE} variant..."
    python3 "${SCRIPT_DIR}/chaos_threadpool_test.py" \
        --mode "${MODE}" \
        --conversations "${CONVERSATIONS}" \
        --sleep-min "${SLEEP_MIN}" \
        --sleep-max "${SLEEP_MAX}" \
        --max-workers "${MAX_WORKERS}" \
        --sample-interval "${SAMPLE_INTERVAL}" \
        --launch-interval "${LAUNCH_INTERVAL}" \
        --seed "${SEED}" \
        | tee "${OUT}"
}

run_phase "A" "vulnerable" "Vulnerable (raw Thread().start())"
run_phase "B" "fixed" "Fixed (ThreadPoolExecutor)"

VULN_OUT="/tmp/chaos-threadpool-vulnerable.out"
FIXED_OUT="/tmp/chaos-threadpool-fixed.out"

V_JSON="$(rg -m1 '^RESULT:' "${VULN_OUT}" | sed 's/^RESULT: //')"
F_JSON="$(rg -m1 '^RESULT:' "${FIXED_OUT}" | sed 's/^RESULT: //')"

if [[ -z "${V_JSON}" || -z "${F_JSON}" ]]; then
    fail "Missing RESULT output."
    exit 1
fi

V_PEAK_TOTAL=$(python3 - <<PY
import json; print(json.loads('''${V_JSON}''')['peak_total_threads'])
PY
)
V_PEAK_BG=$(python3 - <<PY
import json; print(json.loads('''${V_JSON}''')['peak_bg_threads'])
PY
)
F_PEAK_TOTAL=$(python3 - <<PY
import json; print(json.loads('''${F_JSON}''')['peak_total_threads'])
PY
)
F_PEAK_POOL=$(python3 - <<PY
import json; print(json.loads('''${F_JSON}''')['peak_pool_threads'])
PY
)

echo ""
echo -e "${BOLD}──────────────────────────────────────────────────────────${NC}"
echo -e "${BOLD}  Summary${NC}"
echo -e "${BOLD}──────────────────────────────────────────────────────────${NC}"
echo ""
echo "Vulnerable peak total threads: ${V_PEAK_TOTAL}"
echo "Vulnerable peak bg threads:    ${V_PEAK_BG}"
echo "Fixed peak total threads:      ${F_PEAK_TOTAL}"
echo "Fixed peak pool threads:       ${F_PEAK_POOL}"
echo ""

PASS=1
if (( V_PEAK_BG < MIN_VULN_THREADS )); then
    warn "Vulnerable peak bg threads below threshold (${V_PEAK_BG} < ${MIN_VULN_THREADS})"
    PASS=0
fi
if (( F_PEAK_POOL > MAX_FIXED_THREADS )); then
    warn "Fixed peak pool threads above threshold (${F_PEAK_POOL} > ${MAX_FIXED_THREADS})"
    PASS=0
fi

if (( PASS == 1 )); then
    ok "PASS — Vulnerable thread explosion vs fixed thread cap"
else
    fail "FAIL — Thresholds not met"
    if (( CHAOS_ASSERT == 1 )); then
        exit 1
    fi
fi
