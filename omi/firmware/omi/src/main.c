#include <zephyr/kernel.h>
#include <zephyr/shell/shell.h>
#include <zephyr/logging/log.h>
#include <zephyr/drivers/hwinfo.h>
#include <zephyr/pm/device_runtime.h>
#include "lib/dk2/mic.h"
#include "lib/dk2/codec.h"
#include "lib/dk2/config.h"
#include "lib/dk2/transport.h"
#include "lib/dk2/lib/battery/battery.h"
#include "lib/dk2/led.h"
#include "lib/dk2/button.h"
#ifdef CONFIG_OMI_ENABLE_HAPTIC
#include "haptic.h"
#endif
#include "spi_flash.h"
#include "sd_card.h"
#ifdef CONFIG_OMI_ENABLE_ACCELEROMETER
#include "lib/dk2/accel.h"
#endif

LOG_MODULE_REGISTER(main, CONFIG_LOG_DEFAULT_LEVEL);

bool is_connected = false;
bool is_charging = false;
bool is_off = false;

// TODO: remove these metrics
uint32_t gatt_notify_count = 0;
uint32_t total_mic_buffer_bytes = 0;
uint32_t broadcast_audio_count = 0;
uint32_t write_to_tx_queue_count = 0;

static void codec_handler(uint8_t *data, size_t len)
{
    broadcast_audio_count++;
    int err = broadcast_audio_packets(data, len);
    if (err)
    {
        LOG_ERR("Failed to broadcast audio packets: %d", err);
    }
}

static void mic_handler(int16_t *buffer)
{
    // Track total bytes processed (each sample is 2 bytes)
    total_mic_buffer_bytes += 1;

    int err = codec_receive_pcm(buffer, MIC_BUFFER_SAMPLES);
    if (err)
    {
        LOG_ERR("Failed to process PCM data: %d", err);
    }
}

static void boot_led_sequence(void)
{
    // Red blink
    set_led_red(true);
    k_msleep(600);
    set_led_red(false);
    k_msleep(200);
    // Green blink
    set_led_green(true);
    k_msleep(600);
    set_led_green(false);
    k_msleep(200);
    // Blue blink
    set_led_blue(true);
    k_msleep(600);
    set_led_blue(false);
    k_msleep(200);
    // All LEDs on
    set_led_red(true);
    set_led_green(true);
    set_led_blue(true);
    k_msleep(600);
    // All LEDs off
    set_led_red(false);
    set_led_green(false);
    set_led_blue(false);
}

void set_led_state()
{
    // Set LED state based on connection and charging status
    if (is_charging)
    {
        set_led_green(true);
    }
    else
    {
        set_led_green(false);
    }

    // If device is off, turn off all status LEDs except charging indicator
    if (is_off)
    {
        set_led_red(false);
        set_led_blue(false);
        return;
    }

    if (is_connected)
    {
        set_led_blue(true);
        set_led_red(false);
        return;
    }

    // Not connected - RED
    if (!is_connected)
    {
        set_led_red(true);
        set_led_blue(false);
        return;
    }
}

static int suspend_unused_modules(void)
{
    int err = flash_off();
    if (err)
    {
        LOG_ERR("Can not suspend the spi flash module: %d", err);
    }

    err = app_sd_off();
    if (err)
    {
        LOG_ERR("Can not suspend the sd card module: %d", err);
    }

    return 0;
}


int main(void)
{
    int ret;

    // Store reset reason code
    uint32_t reset_reason;
    ret = hwinfo_get_reset_cause( &reset_reason );

	printk("Starting omi ...\n");

	// Suspend unused modules
    LOG_PRINTK("\n");
    LOG_INF("Suspending unused modules...\n");
    ret = suspend_unused_modules();
    if (ret)
    {
        LOG_ERR("Failed to suspend unused modules (err %d)", ret);
        ret = 0;
    }
	
    // Log model, HW, and FW version
    LOG_INF("Model: %s", CONFIG_BT_DIS_MODEL);
    LOG_INF("Firmware revision: %s", CONFIG_BT_DIS_FW_REV_STR);
    LOG_INF("Hardware revision: %s", CONFIG_BT_DIS_HW_REV_STR);

    if( ret >= 0 )
    {
        LOG_DBG("Reset reason: %d\n", reset_reason);
    } else {
        LOG_DBG("Err reading reset reason: %d\n", ret);
    }
    hwinfo_clear_reset_cause();

	// Initialize LEDs
	LOG_PRINTK("\n");
	LOG_INF("Initializing LEDs...\n");

	ret = led_start();
	if (ret)
	{
		LOG_ERR("Failed to initialize LEDs (err %d)", ret);
		return ret;
	}

	// Run the boot LED sequence
	boot_led_sequence();

	// Initialize battery
#ifdef CONFIG_OMI_ENABLE_BATTERY
	ret = battery_init();
	if (ret)
	{
		LOG_ERR("Battery init failed (err %d)", ret);
		return ret;
	}

	ret = battery_charge_start();
	if (ret)
	{
		LOG_ERR("Battery failed to start (err %d)", ret);
		return ret;
	}
	LOG_INF("Battery initialized");
#endif

    // Initialize button
#ifdef CONFIG_OMI_ENABLE_BUTTON
    ret = button_init();
    if (ret)
    {
        LOG_ERR("Failed to initialize Button (err %d)", ret);
        return ret;
    }
    LOG_INF("Button initialized");
    activate_button_work();
#endif

    // Enable haptic
#ifdef CONFIG_OMI_ENABLE_HAPTIC
    LOG_INF("Initializing haptic...\n");

    ret = init_haptic_pin();
    if (ret)
    {
        LOG_ERR("Failed to initialize Haptic driver (err %d)", ret);
        return ret;
    }
    LOG_INF("Haptic driver initialized");
    play_haptic_milli(100);
#endif

    // Enable accelerometer
#ifdef CONFIG_OMI_ENABLE_ACCELEROMETER
    LOG_INF("Initializing IMU...\n");
    ret = accel_start();
    if (ret)
    {
        LOG_ERR("Accelerometer failed to activate (err %d)", ret);
        return ret;
    }
    LOG_INF("Accelerometer initialized");
#endif

    // Enable sdcard
#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
    LOG_PRINTK("\n");
    LOG_INF("Mount SD card...\n");

    err = mount_sd_card();
    if (err)
    {
        LOG_ERR("Failed to mount SD card (err %d)", err);
        return err;
    }

    k_msleep(500);

    LOG_PRINTK("\n");
    LOG_INF("Initializing storage...\n");

    err = storage_init();
    if (err)
    {
        LOG_ERR("Failed to initialize storage (err %d)", err);
    }
#endif

    // Enable usb
#ifdef CONFIG_OMI_ENABLE_USB
    LOG_PRINTK("\n");
    LOG_INF("Initializing power supply check...\n");

    err = init_usb();
    if (err)
    {
        LOG_ERR("Failed to initialize power supply (err %d)", err);
        return err;
    }
#endif

	// Indicate transport initialization
	LOG_PRINTK("\n");
	LOG_INF("Initializing transport...\n");

    set_led_green(true);
    set_led_green(false);

	// Start transport
	int transportErr;
	transportErr = transport_start();
	if (transportErr)
	{
		LOG_ERR("Failed to start transport (err %d)", transportErr);
		return transportErr;
	}

    /** No speaker on Omi2 - TODO should there still be empty stubs? */

	// Initialize codec
	LOG_INF("Initializing codec...\n");

	// Set codec callback
	set_codec_callback(codec_handler);
	ret = codec_start();
	if (ret)
	{
		LOG_ERR("Failed to start codec: %d", ret);
        // Blink blue LED to indicate error
        for (int i = 0; i < 5; i++)
        {
            set_led_blue(!gpio_pin_get_dt(&led_blue));
            k_msleep(200);
        }
        set_led_blue(false);
		return ret;
	}

#ifdef CONFIG_OMI_ENABLE_HAPTIC
    play_haptic_milli(500);
#endif
    set_led_blue(false);

	// Initialize microphone
    LOG_PRINTK("\n");
	LOG_INF("Initializing microphone...\n");

    set_led_red(true);
    set_led_green(true);

	set_mic_callback(mic_handler);
	ret = mic_start();
	if (ret)
	{
		LOG_ERR("Failed to start microphone: %d", ret);
		// Blink red and green LEDs to indicate error
        for (int i = 0; i < 5; i++)
        {
            set_led_red(!gpio_pin_get_dt(&led_red));
            set_led_green(!gpio_pin_get_dt(&led_green));
            k_msleep(200);
        }
        set_led_red(false);
        set_led_green(false);
        return ret;
	}

    set_led_red(false);
    set_led_green(false);

    // Indicate successful initialization
    LOG_PRINTK("\n");
	LOG_INF("Device initialized successfully\n");

    set_led_blue(true);
    k_msleep(1000);
    set_led_blue(false);

	while (1) {
        // Log total mic buffer bytes processed, GATT notify count, broadcast count, and write_to_tx_queue count
        LOG_INF("Total mic buffer bytes: %u, GATT notify count: %u, Broadcast count: %u, TX queue writes: %u",
                total_mic_buffer_bytes, gatt_notify_count, broadcast_audio_count, write_to_tx_queue_count);

        // Update LED state based on connection and charging status
        set_led_state();

        k_msleep(1000);
    }

    printk("Exiting omi...");
    return 0;
}
