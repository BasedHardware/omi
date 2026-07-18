#!/bin/bash
# Trigger the focus analysis test runner in the running Omi Dev app.
# Finds context switches in the time range, analyzes departing frames through
# the focus pipeline, and logs focused/distracted decisions.
#
# Results are logged to the running named bundle's health-advertised log path.
#
# Usage:
#   ./scripts/test-focus.sh              # Last 1 hour, max 20 context switches
#   ./scripts/test-focus.sh --hours 4    # Last 4 hours
#   ./scripts/test-focus.sh --count 30   # Up to 30 context switches
#   ./scripts/test-focus.sh --hours 12 --count 30
#
# Then tail the log:
#   OMI_LOG_PATH="$(./scripts/omi-ctl log-path)"
#   grep "FocusTestCLI" "$OMI_LOG_PATH" | tail -f

HOURS="1"
COUNT="20"

while [[ $# -gt 0 ]]; do
    case $1 in
        --hours|-h) HOURS="$2"; shift 2 ;;
        --count|-c) COUNT="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

echo "Triggering focus test: last ${HOURS}h, max ${COUNT} context switches"
OMI_LOG_PATH="${OMI_LOG_PATH:-$(./scripts/omi-ctl log-path)}"
if [[ ! -f "$OMI_LOG_PATH" ]]; then
    echo "Named-bundle log path is not readable: $OMI_LOG_PATH" >&2
    exit 1
fi
echo "Watching ${OMI_LOG_PATH} for results..."
echo ""

# Send the distributed notification to the running app
xcrun swift -e "
import Foundation
DistributedNotificationCenter.default().postNotificationName(
    NSNotification.Name(\"com.omi.test.focus\"),
    object: nil,
    userInfo: [\"hours\": \"${HOURS}\", \"count\": \"${COUNT}\"],
    deliverImmediately: true
)
RunLoop.current.run(until: Date() + 0.5)
"

# Tail the log for results
exec grep --line-buffered "FocusTestCLI" "$OMI_LOG_PATH" | tail -f
