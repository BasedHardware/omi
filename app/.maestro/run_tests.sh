#!/bin/bash

# Omi App - Maestro Test Runner
# Usage: ./run_tests.sh [functional|performance|all] [--report]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPORT_DIR="${SCRIPT_DIR}/reports"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

usage() {
    echo "Usage: $0 [functional|performance|all] [--report]"
    echo ""
    echo "Options:"
    echo "  functional  - Run functional tests only"
    echo "  performance - Run performance tests only"
    echo "  all         - Run all tests (default)"
    echo "  --report    - Generate JUnit XML report"
    echo ""
    echo "Examples:"
    echo "  $0 functional"
    echo "  $0 performance --report"
    echo "  $0 all --report"
}

check_maestro() {
    if ! command -v maestro &> /dev/null; then
        echo -e "${RED}Error: Maestro is not installed${NC}"
        echo "Install with: curl -Ls 'https://get.maestro.mobile.dev' | bash"
        exit 1
    fi
    echo -e "${GREEN}Maestro found: $(maestro --version)${NC}"
}

run_tests() {
    local test_dir=$1
    local report_flag=$2

    echo -e "${YELLOW}Running tests in: ${test_dir}${NC}"

    if [ "$report_flag" == "--report" ]; then
        mkdir -p "${REPORT_DIR}"
        maestro test \
            --format junit \
            --output "${REPORT_DIR}/report_${TIMESTAMP}.xml" \
            "${SCRIPT_DIR}/${test_dir}/"
    else
        maestro test "${SCRIPT_DIR}/${test_dir}/"
    fi
}

# Parse arguments
TEST_SUITE="${1:-all}"
REPORT_FLAG="${2:-}"

# Check Maestro installation
check_maestro

echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}  Omi App - Maestro Test Suite${NC}"
echo -e "${GREEN}======================================${NC}"
echo ""

case $TEST_SUITE in
    functional)
        echo "Running functional tests..."
        run_tests "functional" "$REPORT_FLAG"
        ;;
    performance)
        echo "Running performance tests..."
        echo -e "${YELLOW}Note: Performance tests may take several hours${NC}"
        run_tests "performance" "$REPORT_FLAG"
        ;;
    all)
        echo "Running all tests..."
        run_tests "functional" "$REPORT_FLAG"
        run_tests "performance" "$REPORT_FLAG"
        ;;
    --help|-h)
        usage
        exit 0
        ;;
    *)
        echo -e "${RED}Unknown option: $TEST_SUITE${NC}"
        usage
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}Tests completed!${NC}"

if [ "$REPORT_FLAG" == "--report" ]; then
    echo -e "Report saved to: ${REPORT_DIR}/report_${TIMESTAMP}.xml"
fi
