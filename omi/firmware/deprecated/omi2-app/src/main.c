/**
 * @file main.c
 * @brief Main entry point for Omi firmware
 * 
 * This file contains the main application code for an embedded audio device
 * running on Zephyr RTOS with nRF hardware. The device handles audio capture,
 * processing, and transmission over Bluetooth, along with various peripherals.
 */

#include <zephyr/logging/log.h>
#include <zephyr/kernel.h>
#include <zephyr/drivers/gpio.h>  /* Replace nrf_power.h with gpio.h */
#include <string.h>               /* For strlen and related functions */
#include <stdio.h>                /* For snprintf */
#include "transport.h"     /* Bluetooth communication module */
#include "mic.h"           /* Microphone interface */
#include "utils.h"         /* Utility functions */
#include "led.h"           /* LED control functions */
#include "config.h"        /* Configuration settings */
#include "codec.h"         /* Audio codec (Opus) */
#include "button.h"        /* Button input handling */
#include "sdcard.h"        /* SD card interface */
#include "storage.h"       /* Storage management */
#include "usb.h"           /* USB interface */
#include "haptic.h"        /* Haptic feedback */
#include "battery.h"       /* Battery management */
#include <zephyr/drivers/sensor.h>  /* Sensor drivers for IMU */
#include <zephyr/sys/printk.h>

// // Fatal error handler
// #include <zephyr/fatal.h>
// void k_sys_fatal_error_handler(unsigned int reason, const struct arch_esf *esf)
// {
//     printk("Fatal error: reason %u\n", reason);
//     k_fatal_halt(reason);
// }

/* Timing constants for boot sequence LED pattern */
#define BOOT_BLINK_DURATION_MS 600
#define BOOT_PAUSE_DURATION_MS 200

/* Hardware pin definitions for detection mechanisms */
#define VBUS_DETECT (1U << 20)    /* USB power detection bit */
#define WAKEUP_DETECT (1U << 16)   /* Wakeup detection bit */

/* Register this module with Zephyr's logging system */
LOG_MODULE_REGISTER(main, CONFIG_LOG_DEFAULT_LEVEL);

/**
 * @brief Callback function for processing encoded audio data
 * 
 * Called by the codec when new encoded audio data is available.
 * Broadcasts the encoded audio packets over Bluetooth.
 * 
 * @param data Pointer to encoded audio data
 * @param len Length of the encoded data in bytes
 */
static void codec_handler(uint8_t *data, size_t len)
{
    // LOG_INF("Codec handler called"); // Reduce log noise
    
    int err = broadcast_audio_packets(data, len);
    if (err)
    {
        if (err == -ENOBUFS) {
             LOG_WRN("TX queue full, encoded packet dropped (size %zu)", len);
        } else {
             LOG_ERR("Failed to broadcast audio packets: %d", err);
        }
    }
}

/**
 * @brief Callback function for handling microphone PCM data
 * 
 * Called when new audio samples are captured from the microphone.
 * Passes the raw PCM data to the codec for encoding.
 * 
 * @param buffer Pointer to buffer containing PCM audio samples
 */
static void mic_handler(int16_t *buffer)
{
    // LOG_INF("Mic handler called"); // Keep this maybe? Or remove if too noisy

    // Comment out the old codec processing call if still present
    int err = codec_receive_pcm(buffer, MIC_BUFFER_SAMPLES);
    if (err)
    {
        LOG_ERR("Failed to process PCM data: %d", err);
    }

    // // Print all samples to the console
    // printk("--- Mic Buffer Start ---\n");
    // for (int i = 0; i < MIC_BUFFER_SAMPLES; i++)
    // {
    //     // printk("Sample %d: %d\\n", i, buffer[i]); // Option 1: Index + Value
    //     printk("%d\n", buffer[i]); // Option 2: Just the value, simpler for copy-paste
    // }
    // printk("--- Mic Buffer End ---\n");
}

/**
 * @brief Handler for Bluetooth controller assertions
 * 
 * Called by the Bluetooth stack when an assertion occurs in the controller.
 * 
 * @param name Name of the assertion
 * @param type Type of the assertion
 */
void bt_ctlr_assert_handle(char *name, int type)
{
    LOG_INF("Bluetooth assert: %s (type %d)", name ? name : "NULL", type);
}

/* Global state variables */
bool is_connected = false;   /* Bluetooth connection state */
// bool is_charging = false;    /* Battery charging state */
extern bool is_charging;     /* Battery charging state, defined elsewhere */
extern bool is_off;          /* Device power state, defined elsewhere */
extern bool usb_charge;      /* USB charging state, defined elsewhere */

/**
 * @brief Execute boot sequence LED pattern
 * 
 * Runs a predefined LED sequence at boot time to indicate the device is starting
 * and to test that all LEDs are functioning correctly.
 */
static void boot_led_sequence(void)
{
    // Red blink
    set_led_red(true);
    k_msleep(BOOT_BLINK_DURATION_MS);
    set_led_red(false);
    k_msleep(BOOT_PAUSE_DURATION_MS);
    // Green blink
    set_led_green(true);
    k_msleep(BOOT_BLINK_DURATION_MS);
    set_led_green(false);
    k_msleep(BOOT_PAUSE_DURATION_MS);
    // Blue blink
    set_led_blue(true);
    k_msleep(BOOT_BLINK_DURATION_MS);
    set_led_blue(false);
    k_msleep(BOOT_PAUSE_DURATION_MS);
    // All LEDs on
    set_led_red(true);
    set_led_green(true);
    set_led_blue(true);
    k_msleep(BOOT_BLINK_DURATION_MS);
    // All LEDs off
    set_led_red(false);
    set_led_green(false);
    set_led_blue(false);
}

/**
 * @brief Update LED states based on device status
 * 
 * Controls the RGB LEDs to indicate various device states:
 * - Green blinking: Charging via USB
 * - Blue solid: Connected to Bluetooth
 * - Red solid: Not connected to Bluetooth
 * - All off: Device powered off
 */
void set_led_state()
{
    // Handle charging indicator (green LED)
    if(usb_charge)
    {
        // Toggle green LED to indicate charging
        is_charging = !is_charging;
        if(is_charging)
        {
            set_led_green(true);
        }
        else
        {
            set_led_green(false);
        }
    }
    else
    {
        set_led_green(false);
    }
    
    // If device is off, ensure all status LEDs are off
    if(is_off)
    {
        set_led_red(false);
        set_led_blue(false);
        return;
    }
    
    // Connected state - Blue LED on
    if (is_connected)
    {
        set_led_blue(true);
        set_led_red(false);
        return;
    }

    // Disconnected state - Red LED on
    if (!is_connected)
    {
        set_led_red(true);
        set_led_blue(false);
        return;
    }
}

// Define a test message to send over Bluetooth
#define TEST_MESSAGE "Hello from Omi!"
#define TEST_MESSAGE_INTERVAL_MS 1000

// Flag to indicate if we should send test messages or use real audio
bool use_test_messages = false;

//Main loop thread
void main_loop_thread(void)
{
    uint8_t count = 0;
    uint8_t test_buffer[32];
    bool transport_error_shown = false;
    
    // Wait a bit to make sure everything is initialized
    k_msleep(2000);
    
    while (1)
    {
        // Update LED state
        set_led_state();
        
        // Only send test data if connected to Bluetooth AND test mode is active
        if (is_connected && use_test_messages) {
            // Format a test message with a counter
            snprintf(test_buffer, sizeof(test_buffer), "%s %u", TEST_MESSAGE, count++);
            LOG_INF("Sending test data: %s", test_buffer);
            
            // Use only one method to avoid duplicate messages
            // Method: Using the direct test message function which uses broadcast_audio_packets internally
            int err = send_test_message(test_buffer, strlen(test_buffer) + 1);
            if (err) {
                LOG_ERR("Failed to send test message: %d", err);
            }
        } else if (!is_connected) {
            // Only show waiting message if transport is actually working
            if (!transport_error_shown) {
                LOG_INF("Waiting for Bluetooth connection...");
            }
        }
        
        // Sleep for the defined interval
        k_msleep(TEST_MESSAGE_INTERVAL_MS);
    }
}

/* Start the main loop thread with 1KB stack, priority 7 */
K_THREAD_DEFINE(main_loop_tid, 1024, main_loop_thread, NULL, NULL, NULL, 7, 0, 0);

/**
 * @brief Main application entry point
 * 
 * Initializes all hardware peripherals, sets up callbacks, 
 * and enters the main application loop.
 * 
 * @return 0 on success, negative error code on failure
 */
int main(void)
{
    int err;

    // Remove the nrf_power functions that are causing build errors
    uint32_t reset_reason = 0; // Placeholder, removed nrf_power_resetreas_get

    // Configure power management using Zephyr's standard interfaces instead of directly
    // accessing nRF registers
    LOG_INF("Booting...\n");

    // Log device information
    LOG_INF("Model: %s", CONFIG_BT_DIS_MODEL);
    LOG_INF("Firmware revision: %s", CONFIG_BT_DIS_FW_REV_STR);
    LOG_INF("Hardware revision: %s", CONFIG_BT_DIS_HW_REV_STR);

    LOG_INF("Reset reason: %d\n", reset_reason);

    LOG_PRINTK("\n");
    LOG_INF("Initializing LEDs...\n");
	LOG_INF("Initializing LEDs...\n");

    // Initialize LED subsystem
    err = led_start();
    if (err)
    {
        LOG_ERR("Failed to initialize LEDs (err %d)", err);
        return err;
    }

    // Run the boot LED sequence to indicate startup
    boot_led_sequence();

    /* CONDITIONAL PERIPHERAL INITIALIZATION BASED ON CONFIG */
    
    // Initialize battery if enabled in config
#ifdef CONFIG_OMI_ENABLE_BATTERY
	LOG_INF("Initializing battery...");
	err = battery_init();
	if (err)
	{
		LOG_ERR("Battery init failed (err %d)", err);
		return err;
	}

	err = battery_charge_start();
	if (err)
	{
		LOG_ERR("Battery failed to start (err %d)", err);
		return err;
	}
	// LOG_INF("Battery initialization skipped");
#endif

	// Initialize IMU if enabled in config
#ifdef CONFIG_OMI_ENABLE_IMU
    // Note: The IMU is now initialized via SYS_INIT in imu.c with imu_poweron()
    // This relies on the IMU driver being properly set up in device tree
    LOG_PRINTK("IMU initialization configured via system init");
#endif

    // Initialize button if enabled in config
#ifdef CONFIG_OMI_ENABLE_BUTTON
    err = button_init();
    if (err)
    {
        LOG_ERR("Failed to initialize Button (err %d)", err);
        return err;
    }
    LOG_INF("Button initialized");
    activate_button_work(); // Start the button event handling thread
#endif

    // Initialize SD card and storage if offline storage is enabled
// #ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
//     LOG_PRINTK("\n");
//     LOG_INF("Mount SD card...\n");

//     err = mount_sd_card();
//     if (err)
//     {
//         LOG_ERR("Failed to mount SD card (err %d)", err);
//         return err;
//     }

//     k_msleep(500); // Allow time for SD card to stabilize

//     LOG_PRINTK("\n");
//     LOG_INF("Initializing storage...\n");

//     err = storage_init();
//     if (err)
//     {
//         LOG_ERR("Failed to initialize storage (err %d)", err);
//     }
// #endif

    // Initialize haptic feedback if enabled in config
#ifdef CONFIG_OMI_ENABLE_HAPTIC
    LOG_PRINTK("\n");
    LOG_INF("Initializing haptic...\n");

    err = init_haptic_pin();
    if (err)
    {
        LOG_ERR("Failed to initialize haptic pin (err %d)", err);
        return err;
    }
    LOG_INF("Haptic pin initialized");
#endif

    // Provide haptic feedback for successful codec initialization if enabled
#ifdef CONFIG_OMI_ENABLE_HAPTIC
	LOG_INF("Providing haptic feedback for successful codec initialization");
    play_haptic_milli(500);
#endif

//     // Initialize USB if enabled in config
// #ifdef CONFIG_ENABLE_USB
//     LOG_PRINTK("\n");
//     LOG_INF("Initializing power supply check...\n");

//     err = init_usb();
//     if (err)
//     {
//         LOG_ERR("Failed to initialize power supply (err %d)", err);
//         return err;
//     }
// #endif

    /* CRITICAL CORE FUNCTIONALITY INITIALIZATION */

    // Initialize Bluetooth transport layer
    LOG_PRINTK("\n");
    LOG_INF("Initializing transport...\n");

    // Visual indicator for transport initialization
    set_led_green(true);
    set_led_green(false);

    // Start the Bluetooth transport
    int transportErr;
    transportErr = transport_start();
    if (transportErr)
    {
        LOG_ERR("Failed to start transport (err %d)", transportErr);
        // Note: we continue execution even in case of transport failure
        // to allow the main loop to run for debugging
    }
    else
    {
        LOG_INF("Transport started successfully");
    }

    // Initialize audio codec (Opus)
    LOG_PRINTK("\n");
    LOG_INF("Initializing codec...\n");

    set_led_blue(true); // Visual indicator for codec initialization

    // Register the callback for encoded audio data
    set_codec_callback(codec_handler);
    err = codec_start();
    if (err)
    {
        LOG_ERR("Failed to start codec: %d", err);
        // Blink blue LED to indicate codec error
        for (int i = 0; i < 5; i++)
        {
            set_led_blue(!gpio_pin_get_dt(&led_blue));
            k_msleep(200);
        }
        set_led_blue(false);
        return err;
    }

    set_led_blue(false);

    // Initialize microphone
    LOG_PRINTK("\n");
    LOG_INF("Initializing microphone...\n");

    // Visual indicator for microphone initialization
    set_led_red(true);
    set_led_green(true);

    k_msleep(1000);

    // Register the callback for microphone data
    set_mic_callback(mic_handler);
    err = mic_start();
    if (err)
    {
        LOG_ERR("Failed to start microphone: %d", err);
        // Blink red and green LEDs to indicate microphone error
        for (int i = 0; i < 5; i++)
        {
            set_led_red(!gpio_pin_get_dt(&led_red));
            set_led_green(!gpio_pin_get_dt(&led_green));
            k_msleep(200);
        }
        set_led_red(false);
        set_led_green(false);
        return err;
    }

    // Explicitly set to audio mode (not test mode)
    set_test_mode(false);
    LOG_INF("Starting in audio mode - mic and codec active");

    // Turn off initialization indicator LEDs
    set_led_red(false);
    set_led_green(false);

    // Indicate successful initialization
    LOG_INF("Device initialized successfully");

    // Brief blue LED flash to indicate successful initialization
    set_led_blue(true);
    k_msleep(1000);
    set_led_blue(false);

    LOG_INF("Entering main loop...");

    return 0;
}

/**
 * @brief Toggle between test mode and audio mode
 * 
 * This function can be called to switch between sending test messages
 * and processing real audio data from the microphone.
 * 
 * @param enable_test_mode true to enable test messages, false to use real audio
 */
void set_test_mode(bool enable_test_mode)
{
    use_test_messages = enable_test_mode;
    
    if (enable_test_mode) {
        LOG_INF("Test mode enabled - sending test messages");
        // Optionally pause microphone to save power
        mic_off();
    } else {
        LOG_INF("Test mode disabled - using real audio");
        // Resume microphone
        mic_on();
    }
}
