#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# Chaos Engineering Test: App Integration Timeout Blocking (PR #4828)
#
# Runs a standalone reproduction of app integration timeouts against a local
# delayed HTTP server. Compares vulnerable (30s/15s/10s) vs fixed (10s/5s/5s)
# and reports wall-clock blocking time.
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CHAOS_ASSERT="${CHAOS_ASSERT:-0}"
MIN_VULN_EXTERNAL="${MIN_VULN_EXTERNAL:-25}"
MAX_FIXED_EXTERNAL="${MAX_FIXED_EXTERNAL:-12}"
MIN_VULN_TOTAL="${MIN_VULN_TOTAL:-45}"
MAX_FIXED_TOTAL="${MAX_FIXED_TOTAL:-25}"

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
    local OUT="/tmp/chaos-timeout-${MODE}.out"

    echo ""
    echo -e "${BOLD}──────────────────────────────────────────────────────────${NC}"
    echo -e "${BOLD}  Phase ${LABEL}: ${DESC}${NC}"
    echo -e "${BOLD}──────────────────────────────────────────────────────────${NC}"
    echo ""

    log "Running ${MODE} variant..."
    python3 "${SCRIPT_DIR}/chaos_timeout_test.py" --mode "${MODE}" | tee "${OUT}"
}

run_phase "A" "vulnerable" "Vulnerable (30s/15s/10s)"
run_phase "B" "fixed" "Fixed (10s/5s/5s)"

V_OUT="/tmp/chaos-timeout-vulnerable.out"
F_OUT="/tmp/chaos-timeout-fixed.out"

V_JSON="$(rg -m1 '^RESULT:' "${V_OUT}" | sed 's/^RESULT: //')"
F_JSON="$(rg -m1 '^RESULT:' "${F_OUT}" | sed 's/^RESULT: //')"

if [[ -z "${V_JSON}" || -z "${F_JSON}" ]]; then
    fail "Missing RESULT output."
    exit 1
fi

V_EXTERNAL=$(python3 - <<PY
import json; print(json.loads('''${V_JSON}''')['timings']['trigger_external_integrations'])
PY
)
V_AUDIO=$(python3 - <<PY
import json; print(json.loads('''${V_JSON}''')['timings']['trigger_realtime_audio_bytes'])
PY
)
V_REAL=$(python3 - <<PY
import json; print(json.loads('''${V_JSON}''')['timings']['trigger_realtime_integrations'])
PY
)
V_TOTAL=$(python3 - <<PY
import json; print(json.loads('''${V_JSON}''')['total_blocking_time'])
PY
)

F_EXTERNAL=$(python3 - <<PY
import json; print(json.loads('''${F_JSON}''')['timings']['trigger_external_integrations'])
PY
)
F_AUDIO=$(python3 - <<PY
import json; print(json.loads('''${F_JSON}''')['timings']['trigger_realtime_audio_bytes'])
PY
)
F_REAL=$(python3 - <<PY
import json; print(json.loads('''${F_JSON}''')['timings']['trigger_realtime_integrations'])
PY
)
F_TOTAL=$(python3 - <<PY
import json; print(json.loads('''${F_JSON}''')['total_blocking_time'])
PY
)

echo ""
echo -e "${BOLD}──────────────────────────────────────────────────────────${NC}"
echo -e "${BOLD}  Summary${NC}"
echo -e "${BOLD}──────────────────────────────────────────────────────────${NC}"
echo ""
echo "Vulnerable external integrations: ${V_EXTERNAL}s"
echo "Vulnerable realtime audio bytes:   ${V_AUDIO}s"
echo "Vulnerable realtime integrations:  ${V_REAL}s"
echo "Vulnerable total blocking time:    ${V_TOTAL}s"
echo ""
echo "Fixed external integrations:       ${F_EXTERNAL}s"
echo "Fixed realtime audio bytes:        ${F_AUDIO}s"
echo "Fixed realtime integrations:       ${F_REAL}s"
echo "Fixed total blocking time:         ${F_TOTAL}s"
echo ""

PASS=1
if (( $(python3 - <<PY
print(1 if float('${V_EXTERNAL}') < ${MIN_VULN_EXTERNAL} else 0)
PY
) )); then
    warn "Vulnerable external integration blocking below threshold (${V_EXTERNAL} < ${MIN_VULN_EXTERNAL})"
    PASS=0
fi
if (( $(python3 - <<PY
print(1 if float('${F_EXTERNAL}') > ${MAX_FIXED_EXTERNAL} else 0)
PY
) )); then
    warn "Fixed external integration blocking above threshold (${F_EXTERNAL} > ${MAX_FIXED_EXTERNAL})"
    PASS=0
fi
if (( $(python3 - <<PY
print(1 if float('${V_TOTAL}') < ${MIN_VULN_TOTAL} else 0)
PY
) )); then
    warn "Vulnerable total blocking below threshold (${V_TOTAL} < ${MIN_VULN_TOTAL})"
    PASS=0
fi
if (( $(python3 - <<PY
print(1 if float('${F_TOTAL}') > ${MAX_FIXED_TOTAL} else 0)
PY
) )); then
    warn "Fixed total blocking above threshold (${F_TOTAL} > ${MAX_FIXED_TOTAL})"
    PASS=0
fi

if (( PASS == 1 )); then
    ok "PASS — Vulnerable blocks longer than fixed"
else
    fail "FAIL — Thresholds not met"
    if (( CHAOS_ASSERT == 1 )); then
        exit 1
    fi
fi
