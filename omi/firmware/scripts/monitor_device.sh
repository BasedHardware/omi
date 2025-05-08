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
LOG_FILE="$LOG_DIR/device.log"
SESSION_NAME="device_monitor_$(basename "$DEVICE")"

mkdir -p "$LOG_DIR"

cleanup() {
    echo "Exiting monitor script..."

    # Kill screen session by name
    screen -ls | grep "$SESSION_NAME" | awk '{print $1}' | xargs -r -n1 screen -S {} -X quit

    # Ensure all related screens are gone
    pkill -f "screen $DEVICE $BAUD_RATE"

    stty sane
    exit 0
}

trap cleanup SIGINT SIGTERM

echo "Starting device monitor for $DEVICE"
echo "Logs will be appended to $LOG_FILE"
echo "Press Ctrl+C to exit"

> "$LOG_FILE"
echo "================ Script started at $(date) ================" >> "$LOG_FILE"

while true; do
    echo "Waiting for device $DEVICE..."

    while [ ! -e "$DEVICE" ]; do
        sleep 1
    done

    echo "Device connected! Starting logging to $LOG_FILE"
    echo "================ Session started at $(date) ================" >> "$LOG_FILE"

    screen -dmS "$SESSION_NAME" bash -c "script -q -a '$LOG_FILE' screen $DEVICE $BAUD_RATE"

    while [ -e "$DEVICE" ]; do
        sleep 1
    done

    echo "Device disconnected."
    echo "================ Session ended at $(date) ================" >> "$LOG_FILE"

    cleanup
    echo "Waiting for device to reconnect..."
    sleep 2
done
