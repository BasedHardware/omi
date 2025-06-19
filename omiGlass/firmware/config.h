#ifndef CONFIG_H
#define CONFIG_H

// =============================================================================
// BOARD CONFIGURATION - Must be defined before camera includes
// =============================================================================
#define CAMERA_MODEL_XIAO_ESP32S3  // Define camera model for Seeed Xiao ESP32S3
#define BOARD_HAS_PSRAM            // Enable PSRAM support
#define CONFIG_ARDUHAL_ESP_LOG     // Enable Arduino HAL logging

// =============================================================================
// DEVICE CONFIGURATION
// =============================================================================
#define BLE_DEVICE_NAME "OMI Glass"
#define FIRMWARE_VERSION_STRING "2.1.0"
#define HARDWARE_REVISION "ESP32-S3-v1.0"
#define MANUFACTURER_NAME "Based Hardware"

// =============================================================================
// POWER MANAGEMENT - Optimized for MINIMUM 6-8 hours, targeting 10+ hours
// =============================================================================
// CPU Frequency Management - Aggressive power optimization
#define MAX_CPU_FREQ_MHZ 100          // Further reduced from 120MHz - still sufficient
#define MIN_CPU_FREQ_MHZ 40           // Ultra-low power for idle states
#define NORMAL_CPU_FREQ_MHZ 80        // Normal operation frequency (good balance)

// Sleep Management
#define LIGHT_SLEEP_DURATION_US 50000   // 50ms light sleep intervals
#define DEEP_SLEEP_THRESHOLD_MS 300000  // 5 minutes of inactivity triggers deep sleep
#define IDLE_THRESHOLD_MS 45000         // 45 seconds to enter power save mode (was 30s)

// Battery Configuration - Dual 250mAh @ 3.5V-4.1V under load (500mAh total)
#define BATTERY_MAX_VOLTAGE 4.1f       // 4.1V fully charged (under load)
#define BATTERY_MIN_VOLTAGE 3.5f       // 3.5V empty (under load)
#define BATTERY_CRITICAL_VOLTAGE 3.4f  // Emergency shutdown voltage
#define BATTERY_LOW_VOLTAGE 3.6f       // Low battery warning
#define VOLTAGE_DIVIDER_RATIO 2.104f   // Calibrated to match multimeter readings (load-compensated)

// Battery Monitoring - Extended intervals for power savings
#define BATTERY_REPORT_INTERVAL_MS 90000    // 1.5 minute reporting (was 60s)
#define BATTERY_TASK_INTERVAL_MS 20000      // 20 second internal checks (was 15s)
#define BATTERY_ADC_PIN 2                   // GPIO2 (A1) - voltage divider connection

// =============================================================================
// CAMERA CONFIGURATION - Power optimized for 6-8 hour battery life
// =============================================================================
#define CAMERA_FRAME_SIZE FRAMESIZE_VGA     // 640x480 - optimal balance
#define CAMERA_JPEG_QUALITY 25              // Slightly higher quality for better compression efficiency
#define CAMERA_XCLK_FREQ 6000000           // 6MHz - reduced from 8MHz for power savings
#define CAMERA_FB_IN_PSRAM CAMERA_FB_IN_PSRAM
#define CAMERA_GRAB_LATEST CAMERA_GRAB_LATEST

// Fixed Photo Capture Interval - Optimized for 6-8 hour operation
#define PHOTO_CAPTURE_INTERVAL_MS 30000    // Fixed 30 second interval
#define CAMERA_TASK_INTERVAL_MS 2000              // 2 second task check
#define CAMERA_TASK_STACK_SIZE 3072               // Reduced stack size
#define CAMERA_TASK_PRIORITY 2

// Camera Power Management - Reduce power cycling 
#define CAMERA_POWER_DOWN_DELAY_MS 60000    // Power down camera after 60s idle (was 8s)

// =============================================================================
// BLE CONFIGURATION - Power optimized for extended battery life
// =============================================================================
#define BLE_MTU_SIZE 517                    // Maximum MTU for efficiency
#define BLE_CHUNK_SIZE 500                  // Safe chunk size for photo transfer
#define BLE_PHOTO_TRANSFER_DELAY 3          // Fast transfer for connection stability
#define BLE_TX_POWER ESP_PWR_LVL_N0         // Low power for 6+ hour battery life

// Power-optimized BLE Advertising - Longer intervals for power savings
#define BLE_ADV_MIN_INTERVAL 0x0140         // 200ms minimum (was 160ms)
#define BLE_ADV_MAX_INTERVAL 0x0280         // 400ms maximum (was 320ms)
#define BLE_ADV_TIMEOUT_MS 0                // Never stop advertising (always discoverable)
#define BLE_SLEEP_ADV_INTERVAL 45000        // Re-advertise every 45 seconds when not connected (was 30s)

// Connection Management - Stable connections with power optimization
#define BLE_CONNECTION_TIMEOUT_MS 0         // Never timeout connections (disable auto-disconnect)
#define BLE_TASK_INTERVAL_MS 20000          // 20 second connection check (was 15s)
#define BLE_TASK_STACK_SIZE 2048
#define BLE_TASK_PRIORITY 1

// Connection Parameters for Stable Connections with Power Optimization
#define BLE_CONN_MIN_INTERVAL 20            // 25ms minimum connection interval (was 20ms)
#define BLE_CONN_MAX_INTERVAL 40            // 50ms maximum connection interval (was 40ms)
#define BLE_CONN_LATENCY 0                  // No latency for immediate response
#define BLE_CONN_TIMEOUT 800                // 8 second supervision timeout

// =============================================================================
// POWER STATES
// =============================================================================
typedef enum {
    POWER_STATE_ACTIVE,      // Normal operation - camera + BLE active
    POWER_STATE_POWER_SAVE,  // Reduced frequency, longer intervals
    POWER_STATE_LOW_BATTERY, // Minimal operation
    POWER_STATE_SLEEP        // Deep sleep mode
} power_state_t;

// =============================================================================
// TASK CONFIGURATION - Optimized stack sizes
// =============================================================================
#define BATTERY_TASK_STACK_SIZE 2048
#define BATTERY_TASK_PRIORITY 1
#define POWER_MANAGEMENT_TASK_STACK_SIZE 2048
#define POWER_MANAGEMENT_TASK_PRIORITY 0

// Status Reporting - Power optimized
#define STATUS_REPORT_INTERVAL_MS 120000    // 2 minutes (was 30 seconds)

// =============================================================================
// BLE UUID DEFINITIONS - OMI Protocol
// =============================================================================
#define OMI_SERVICE_UUID "19B10000-E8F2-537E-4F6C-D104768A1214"
#define AUDIO_DATA_UUID "19B10001-E8F2-537E-4F6C-D104768A1214"
#define AUDIO_CONTROL_UUID "19B10002-E8F2-537E-4F6C-D104768A1214"
#define PHOTO_DATA_UUID "19B10005-E8F2-537E-4F6C-D104768A1214"
#define PHOTO_CONTROL_UUID "19B10006-E8F2-537E-4F6C-D104768A1214"

// Battery Service UUID - Cast to uint16_t for BLE compatibility
#define BATTERY_SERVICE_UUID (uint16_t)0x180F
#define BATTERY_LEVEL_UUID (uint16_t)0x2A19

// =============================================================================
// PIN DEFINITIONS (from camera_pins.h integration)
// =============================================================================
#ifdef CAMERA_MODEL_XIAO_ESP32S3
  #define PWDN_GPIO_NUM     -1
  #define RESET_GPIO_NUM    -1
  #define XCLK_GPIO_NUM     10
  #define SIOD_GPIO_NUM     40
  #define SIOC_GPIO_NUM     39
  #define Y9_GPIO_NUM       48
  #define Y8_GPIO_NUM       11
  #define Y7_GPIO_NUM       12
  #define Y6_GPIO_NUM       14
  #define Y5_GPIO_NUM       16
  #define Y4_GPIO_NUM       18
  #define Y3_GPIO_NUM       17
  #define Y2_GPIO_NUM       15
  #define VSYNC_GPIO_NUM    38
  #define HREF_GPIO_NUM     47
  #define PCLK_GPIO_NUM     13
  
  // Power Button and LED Control
  #define POWER_BUTTON_PIN  1           // Custom button (GPIO1/A0) - power on/off
  #define STATUS_LED_PIN    21          // User LED (GPIO21) - status indicator
#endif

// =============================================================================
// POWER BUTTON & LED CONFIGURATION
// =============================================================================
// Button Configuration
#define BUTTON_DEBOUNCE_MS 50             // Button debounce time
#define POWER_OFF_PRESS_MS 2000           // Long press duration for power off (2 seconds)
#define BOOT_COMPLETE_DELAY_MS 3000       // LED indication during boot

// LED Status Patterns (in milliseconds)
#define LED_BOOT_BLINK_FAST 200           // Fast blink during boot
#define LED_BATTERY_LOW_BLINK 1000        // Slow blink for low battery
#define LED_SLEEP_BLINK 5000              // Very slow blink in deep sleep mode
#define LED_PHOTO_CAPTURE_FLASH 100       // Quick flash during photo capture

// Deep Sleep Configuration  
#define DEEP_SLEEP_BUTTON_WAKEUP 1        // Enable button wake-up from deep sleep
#define POWER_OFF_SLEEP_DELAY_MS 1000     // Delay before entering deep sleep after power off

// Power Button States
typedef enum {
    BUTTON_IDLE,
    BUTTON_PRESSED,
    BUTTON_LONG_PRESS,
    BUTTON_RELEASED
} button_state_t;

// LED Status Modes
typedef enum {
    LED_OFF,
    LED_ON,
    LED_BOOT_SEQUENCE,
    LED_NORMAL_OPERATION, 
    LED_LOW_BATTERY,
    LED_PHOTO_CAPTURE,
    LED_POWER_OFF_SEQUENCE,
    LED_SLEEP_MODE
} led_status_t;

// Device Power States
typedef enum {
    DEVICE_BOOTING,
    DEVICE_ACTIVE,
    DEVICE_POWER_SAVE,
    DEVICE_LOW_BATTERY,
    DEVICE_POWERING_OFF,
    DEVICE_SLEEP
} device_state_t;

#endif // CONFIG_H 