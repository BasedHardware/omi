#!/bin/bash

# Device path to monitor
devices=(/dev/tty.usb*)
if [ ${#devices[@]} -eq 0 ]; then
    echo "No devices matching /dev/tty.usb* found. Exiting."
    exit 1
elif [ ${#devices[@]} -eq 1 ]; then
    DEVICE=${devices[0]}
    echo "Using device: $DEVICE"
else
    echo "Multiple devices found:"
    select d in "${devices[@]}"; do
        if [ -n "$d" ]; then
            DEVICE="$d"
            echo "Selected device: $DEVICE"
            break
        else
            echo "Invalid selection. Please try again."
        fi
    done
fi
BAUD_RATE=115200
LOG_DIR="logs"
LOG_FILE="$LOG_DIR/device.log" # Single log file

# Create logs directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Function to handle cleanup on exit
cleanup() {
    echo "Exiting monitor script..."
    # Kill the script process running screen
    if [[ -n "$SCRIPT_PID" ]]; then
        pkill -P $SCRIPT_PID # Kill children of script (like screen)
        kill $SCRIPT_PID 2>/dev/null
    fi
    # Ensure screen session is terminated (belt and suspenders)
    pkill -f "screen $DEVICE $BAUD_RATE"
    # Restore terminal settings if needed
    stty sane
    exit 0
}

# Set trap for clean exit
trap cleanup SIGINT SIGTERM

echo "Starting device monitor for $DEVICE"
echo "Logs will be appended to $LOG_FILE"
echo "Press Ctrl+C to exit"

# Clear the log file at the start, or comment this out to keep history across script runs
> "$LOG_FILE"
echo "================ Script started at $(date) ================" >> "$LOG_FILE"

SCRIPT_PID=""

while true; do
    echo "Waiting for device $DEVICE..."

    # Wait for device to be available
    while [ ! -e "$DEVICE" ]; do
        sleep 1
    done

    echo "Device connected! Starting logging to $LOG_FILE"
    echo "================ Session started at $(date) ================" >> "$LOG_FILE"

    # Use script command to capture screen's output, appending (-a) to the log file
    # Run in background
    script -q -a "$LOG_FILE" screen $DEVICE $BAUD_RATE &
    SCRIPT_PID=$!

    echo "Monitoring device... PID: $SCRIPT_PID"

    # Wait for device to disconnect
    while [ -e "$DEVICE" ]; do
        # Check if the script/screen process died prematurely
        if ! ps -p $SCRIPT_PID > /dev/null; then
            echo "Error: Logging process (PID $SCRIPT_PID) ended unexpectedly."
            SCRIPT_PID=""
            break
        fi
        sleep 1
    done

    # Device disconnected or process died
    if [ -e "$DEVICE" ]; then
        # Process died, device still connected
        echo "Logging process stopped. Restarting..."
    else
        # Device disconnected
        echo "Device disconnected. Stopping logging session."
    fi

    # Kill the script process and its children (screen)
    if [[ -n "$SCRIPT_PID" ]]; then
        pkill -P $SCRIPT_PID # Kill children first
        kill $SCRIPT_PID 2>/dev/null
    fi
    # Extra cleanup for screen
    pkill -f "screen $DEVICE $BAUD_RATE"

    SCRIPT_PID=""

    echo "================ Session ended at $(date) ================" >> "$LOG_FILE"
    echo "Waiting for device to reconnect..."
    sleep 2
done