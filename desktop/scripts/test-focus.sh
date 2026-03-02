#!/bin/bash
# Trigger the focus analysis test runner in the running Omi Dev app.
# Finds context switches in the time range, analyzes departing frames through
# the focus pipeline, and logs focused/distracted decisions.
#
# Results are logged to /private/tmp/omi-dev.log
#
# Usage:
#   ./scripts/test-focus.sh              # Last 1 hour, max 20 context switches
#   ./scripts/test-focus.sh --hours 4    # Last 4 hours
#   ./scripts/test-focus.sh --count 30   # Up to 30 context switches
#   ./scripts/test-focus.sh --hours 12 --count 30
#
# Then tail the log:
#   grep "FocusTestCLI" /private/tmp/omi-dev.log | tail -f

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
echo "Watching /private/tmp/omi-dev.log for results..."
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
exec grep --line-buffered "FocusTestCLI" /private/tmp/omi-dev.log | tail -f
