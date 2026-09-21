#!/bin/bash

echo "ESP32 S3 XIAO Flash Script"
echo "-------------------------"
echo "This script will help you flash the firmware to your ESP32 S3 XIAO board."
echo ""

# Function to find ESP32 device
find_esp32_device() {
    # Look for USB devices with ESP32 in the name
    ESP_DEVICE=$(ls /dev/tty.usb* 2>/dev/null | grep -i "usb\|wchusbserial\|SLAB\|CP210\|ACM" | head -n 1)
    
    if [ -z "$ESP_DEVICE" ]; then
        # Check for cu devices as well (common on macOS)
        ESP_DEVICE=$(ls /dev/cu.usb* 2>/dev/null | grep -i "usb\|wchusbserial\|SLAB\|CP210\|ACM" | head -n 1)
    fi
    
    echo "$ESP_DEVICE"
}

# Check if PlatformIO is installed
if ! command -v platformio &> /dev/null; then
    echo "PlatformIO is not installed or not in your PATH."
    echo "Please install PlatformIO using: brew install platformio"
    exit 1
fi

# Navigate to the project directory
cd "$(dirname "$0")" || exit

# Check if the device is connected
ESP_DEVICE=$(find_esp32_device)

if [ -z "$ESP_DEVICE" ]; then
    echo "No ESP32 S3 XIAO device found."
    echo "Please connect your ESP32 S3 XIAO board to your computer via USB."
    echo "Waiting for device to be connected..."
    
    # Wait for the device to be connected
    while [ -z "$ESP_DEVICE" ]; do
        sleep 2
        ESP_DEVICE=$(find_esp32_device)
        if [ -n "$ESP_DEVICE" ]; then
            echo "Device found: $ESP_DEVICE"
            break
        fi
        echo -n "."
    done
else
    echo "ESP32 S3 XIAO device found at: $ESP_DEVICE"
fi

echo ""
echo "========================================================================"
echo "IMPORTANT: Enter bootloader mode before flashing:"
echo "1. Press and hold the BOOT button on your ESP32 S3 XIAO"
echo "2. Press the RESET button while holding BOOT"
echo "3. Release the RESET button first, then release BOOT"
echo "========================================================================"
echo ""
read -p "Press Enter when your device is in bootloader mode..." -r

# Build and upload the firmware
echo "Building and uploading the firmware..."
echo ""

# Try different environments
ENV_LIST=("seeed_xiao_esp32s3" "seeed_xiao_esp32s3_slow")

for ENV in "${ENV_LIST[@]}"; do
    echo "Attempting to flash with environment: $ENV"
    platformio run -e "$ENV" --target upload --upload-port "$ESP_DEVICE"
    
    if [ $? -eq 0 ]; then
        echo ""
        echo "Firmware successfully uploaded to the ESP32 S3 XIAO board!"
        echo "You can now monitor the serial output using:"
        echo "platformio device monitor -p $ESP_DEVICE -b 115200"
        
        # Ask if the user wants to monitor the serial output
        read -p "Do you want to monitor the serial output? (y/n): " -n 1 -r
        echo ""
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo "Starting serial monitor..."
            platformio device monitor -p "$ESP_DEVICE" -b 115200
        fi
        
        exit 0
    else
        echo "Failed with environment $ENV, trying next environment..."
    fi
done

echo ""
echo "Failed to upload the firmware after multiple attempts."
echo ""
echo "Troubleshooting tips:"
echo "1. Try a different USB cable"
echo "2. Connect directly to the computer (not through a hub)"
echo "3. Make sure your board is properly in bootloader mode"
echo "4. Try manually running: platformio run -e seeed_xiao_esp32s3_slow --target upload --upload-port $ESP_DEVICE"
echo ""

exit 1 