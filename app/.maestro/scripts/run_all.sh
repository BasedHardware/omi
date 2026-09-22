#!/usr/bin/env bash
# =============================================================================
# Omi Functional Test Suite — Maestro Runner
# =============================================================================
# Usage:
#   bash app/.maestro/scripts/run_all.sh [OPTIONS]
#
# Options:
#   --device-id <id>    Target device/emulator ID (default: auto-detect)
#   --tags <tags>       Comma-separated tags to filter (default: core)
#                       Use "all" to run everything, "device_required" for HW tests
#   --output <dir>      Output directory for reports (default: .maestro/reports)
#   --help              Show this help
#
# Prerequisites:
#   - Maestro CLI installed: brew install maestro (macOS) or curl -Ls ... (Linux)
#   - App installed on target device/emulator
#   - For device_required tests: Omi device powered on and nearby
# =============================================================================

set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAESTRO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_DIR="$(cd "$MAESTRO_DIR/.." && pwd)"
FLOWS_DIR="$MAESTRO_DIR/flows"
DEFAULT_OUTPUT="$MAESTRO_DIR/reports"

DEVICE_ID=""
TAGS="core"
OUTPUT_DIR="$DEFAULT_OUTPUT"
START_TIME=""
RESULTS=()

# ── Argument Parsing ──────────────────────────────────────────────────────────

show_help() {
    head -18 "$0" | tail -16
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --device-id) DEVICE_ID="$2"; shift 2 ;;
        --tags)      TAGS="$2"; shift 2 ;;
        --output)    OUTPUT_DIR="$2"; shift 2 ;;
        --help)      show_help ;;
        *)           echo "Unknown option: $1"; show_help ;;
    esac
done

# ── Helpers ───────────────────────────────────────────────────────────────────

log()     { echo "[$(date '+%H:%M:%S')] $*"; }
log_ok()  { echo "[$(date '+%H:%M:%S')] ✅ $*"; }
log_err() { echo "[$(date '+%H:%M:%S')] ❌ $*"; }
log_skip(){ echo "[$(date '+%H:%M:%S')] ⏭️  $*"; }

elapsed_since() {
    local start="$1"
    local now
    now=$(date +%s)
    echo $(( now - start ))
}

# ── Preflight Checks ─────────────────────────────────────────────────────────

log "Omi Functional Test Suite"
log "========================="

# Check Maestro is installed
if ! command -v maestro &>/dev/null; then
    log_err "Maestro CLI not found. Install: brew install maestro (macOS) or see https://maestro.mobile.dev/"
    exit 1
fi

MAESTRO_VERSION=$(maestro --version 2>/dev/null || echo "unknown")
log "Maestro version: $MAESTRO_VERSION"

# Check device
if [[ -n "$DEVICE_ID" ]]; then
    log "Target device: $DEVICE_ID"
    DEVICE_FLAG="--device $DEVICE_ID"
else
    DEVICE_FLAG=""
    log "Target device: auto-detect"
fi

# Create output directory
mkdir -p "$OUTPUT_DIR"
log "Reports output: $OUTPUT_DIR"
log "Tags filter: $TAGS"
echo ""

# ── Collect Flows ─────────────────────────────────────────────────────────────

collect_flows() {
    local tag_filter="$1"
    local flows=()

    for flow_file in "$FLOWS_DIR"/*.yaml; do
        [[ -f "$flow_file" ]] || continue

        local flow_tags
        flow_tags=$(awk '/^tags:/{p=1; next} p && /^ *- /{gsub(/^ *- /,""); print} p && !/^ *- /{p=0}' "$flow_file" || true)

        if [[ "$tag_filter" == "all" ]]; then
            flows+=("$flow_file")
        else
            local match=false
            IFS=',' read -ra FILTER_TAGS <<< "$tag_filter"
            for ft in "${FILTER_TAGS[@]}"; do
                ft=$(echo "$ft" | xargs)  # trim whitespace
                if echo "$flow_tags" | grep -q "^${ft}$"; then
                    match=true
                    break
                fi
            done
            if $match; then
                flows+=("$flow_file")
            fi
        fi
    done

    printf '%s\n' "${flows[@]}"
}

FLOW_FILES=()
while IFS= read -r f; do
    [[ -n "$f" ]] && FLOW_FILES+=("$f")
done < <(collect_flows "$TAGS")

if [[ ${#FLOW_FILES[@]} -eq 0 ]]; then
    log_err "No flows found matching tags: $TAGS"
    exit 1
fi

log "Found ${#FLOW_FILES[@]} flow(s) to run"
echo ""

# ── Run Flows ─────────────────────────────────────────────────────────────────

TOTAL=0
PASSED=0
FAILED=0
SKIPPED=0
SUITE_START=$(date +%s)

for flow_file in "${FLOW_FILES[@]}"; do
    flow_name=$(basename "$flow_file" .yaml)
    TOTAL=$((TOTAL + 1))

    log "Running: $flow_name"
    flow_start=$(date +%s)
    flow_output="$OUTPUT_DIR/$flow_name"
    mkdir -p "$flow_output"

    # Run Maestro test
    set +e
    maestro test "$flow_file" \
        $DEVICE_FLAG \
        --config "$MAESTRO_DIR/config/global.yaml" \
        --format junit \
        --output "$flow_output/report.xml" \
        > "$flow_output/stdout.log" 2>&1
    exit_code=$?
    set -e

    flow_duration=$(elapsed_since "$flow_start")

    if [[ $exit_code -eq 0 ]]; then
        PASSED=$((PASSED + 1))
        RESULTS+=("PASS|$flow_name|${flow_duration}s")
        log_ok "$flow_name — PASSED (${flow_duration}s)"
    else
        FAILED=$((FAILED + 1))
        RESULTS+=("FAIL|$flow_name|${flow_duration}s")
        log_err "$flow_name — FAILED (${flow_duration}s) — see $flow_output/stdout.log"
    fi

    # Copy only screenshots generated during this flow (not from earlier runs)
    if [[ -d "$HOME/.maestro/tests" ]]; then
        find "$HOME/.maestro/tests" -name "*.png" \
            -newer "$flow_output/report.xml" \
            -exec cp {} "$flow_output/" \; 2>/dev/null || true
    fi
done

SUITE_DURATION=$(elapsed_since "$SUITE_START")

# ── Generate Report ───────────────────────────────────────────────────────────

REPORT_FILE="$OUTPUT_DIR/report.md"

{
    echo "# Omi Functional Test Report"
    echo ""
    echo "**Date:** $(date '+%Y-%m-%d %H:%M:%S %Z')"
    echo "**Duration:** ${SUITE_DURATION}s"
    echo "**Maestro Version:** $MAESTRO_VERSION"
    echo "**Device:** ${DEVICE_ID:-auto}"
    echo "**Tags:** $TAGS"
    echo ""
    echo "## Summary"
    echo ""
    echo "| Metric  | Count |"
    echo "|---------|-------|"
    echo "| Total   | $TOTAL |"
    echo "| ✅ Passed | $PASSED |"
    echo "| ❌ Failed | $FAILED |"
    echo "| ⏭️ Skipped | $SKIPPED |"
    echo ""
    echo "## Results"
    echo ""
    echo "| Status | Flow | Duration |"
    echo "|--------|------|----------|"
    for result in "${RESULTS[@]}"; do
        IFS='|' read -r status name duration <<< "$result"
        if [[ "$status" == "PASS" ]]; then
            echo "| ✅ | $name | $duration |"
        else
            echo "| ❌ | $name | $duration |"
        fi
    done
    echo ""
    echo "## Flow Details"
    echo ""
    for flow_file in "${FLOW_FILES[@]}"; do
        flow_name=$(basename "$flow_file" .yaml)
        flow_output="$OUTPUT_DIR/$flow_name"
        echo "### $flow_name"
        echo ""
        if [[ -f "$flow_output/stdout.log" ]]; then
            echo "<details><summary>Console Output</summary>"
            echo ""
            echo '```'
            tail -50 "$flow_output/stdout.log"
            echo '```'
            echo "</details>"
        fi
        echo ""
    done
    echo "---"
    echo "*Generated by Omi Functional Test Suite*"
} > "$REPORT_FILE"

# ── Final Summary ─────────────────────────────────────────────────────────────

echo ""
echo "═══════════════════════════════════════════════════"
echo "  Omi Functional Test Suite — Results"
echo "═══════════════════════════════════════════════════"
echo "  Total:   $TOTAL"
echo "  Passed:  $PASSED ✅"
echo "  Failed:  $FAILED ❌"
echo "  Skipped: $SKIPPED ⏭️"
echo "  Duration: ${SUITE_DURATION}s"
echo ""
echo "  Report: $REPORT_FILE"
echo "═══════════════════════════════════════════════════"

# Exit with failure if any tests failed
[[ $FAILED -eq 0 ]] && exit 0 || exit 1
