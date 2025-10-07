#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/pm/device_runtime.h>
#include <zephyr/shell/shell.h>

#include "lib/core/button.h"
#include "lib/core/codec.h"
#include "lib/core/config.h"
#include "lib/core/feedback.h"
#include "lib/core/haptic.h"
#include "lib/core/led.h"
#include "lib/core/lib/battery/battery.h"
#include "lib/core/mic.h"
#include "lib/core/monitor.h"
#include "lib/core/settings.h"
#include "lib/core/transport.h"
#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
#include "lib/core/storage.h"
#endif
#include "lib/core/sd_card.h"
#include "spi_flash.h"

LOG_MODULE_REGISTER(main, CONFIG_LOG_DEFAULT_LEVEL);

bool is_connected = false;
bool is_charging = false;
bool is_off = false;

static void codec_handler(uint8_t *data, size_t len)
{
    monitor_inc_broadcast_audio();
    int err = broadcast_audio_packets(data, len);
    if (err) {
        monitor_inc_broadcast_audio_failed();
    }
}

static void mic_handler(int16_t *buffer)
{
    // Track total bytes processed (each sample is 2 bytes)
    monitor_inc_mic_buffer();

    int err = codec_receive_pcm(buffer, MIC_BUFFER_SAMPLES);
    if (err) {
        LOG_ERR("Failed to process PCM data: %d", err);
    }
}

static void boot_led_sequence(void)
{
    // Quick blue pulse = "I'm alive, booting..."
    set_led_blue(true);
    k_msleep(300);
    led_off();
}

static void boot_ready_sequence(void)
{
    const int steps = 50;
    const int delay_ms = 10;

    // Smooth green fade in/out 2 times = "Ready!"
    for (int cycle = 0; cycle < 2; cycle++) {
        // Fade in: ease-in-out
        for (int i = 0; i <= steps; i++) {
            float t = (float) i / steps;
            // Ease-in-out quadratic
            float eased = t < 0.5f ? 2.0f * t * t : 1.0f - 2.0f * (1.0f - t) * (1.0f - t);
            uint8_t level = (uint8_t) (eased * 50.0f);
            set_led_pwm(LED_GREEN, level);
            k_msleep(delay_ms);
        }

        // Fade out: ease-in-out
        for (int i = 0; i <= steps; i++) {
            float t = (float) i / steps;
            float eased = t < 0.5f ? 2.0f * t * t : 1.0f - 2.0f * (1.0f - t) * (1.0f - t);
            uint8_t level = (uint8_t) ((1.0f - eased) * 70.0f);
            set_led_pwm(LED_GREEN, level);
            k_msleep(delay_ms);
        }
    }
    k_msleep(10);
    led_off();
    k_msleep(10);
}

void set_led_state()
{
    // Set LED state based on connection and charging status
    if (is_charging) {
        set_led_green(true);
    } else {
        set_led_green(false);
    }

    // If device is off, turn off all status LEDs except charging indicator
    if (is_off) {
        set_led_red(false);
        set_led_blue(false);
        return;
    }

    if (is_connected) {
        set_led_blue(true);
        set_led_red(false);
        return;
    }

    // Not connected - RED
    if (!is_connected) {
        set_led_red(true);
        set_led_blue(false);
        return;
    }
}

static int suspend_unused_modules(void)
{
    int err = flash_off();
    if (err) {
        LOG_ERR("Can not suspend the spi flash module: %d", err);
    }

    return 0;
}

int main(void)
{
    int ret;

    printk("Starting omi ...\n");

    // Suspend unused modules
    LOG_PRINTK("\n");
    LOG_INF("Suspending unused modules...\n");
    ret = suspend_unused_modules();
    if (ret) {
        LOG_ERR("Failed to suspend unused modules (err %d)", ret);
        ret = 0;
    }

    // Initialize settings
    LOG_INF("Initializing settings...\n");
    int setting_ret = app_settings_init();
    if (setting_ret) {
        LOG_ERR("Failed to initialize settings (err %d)", setting_ret);
    }

    // Initialize monitoring system
    LOG_INF("Initializing monitoring system...\n");
    ret = monitor_init();
    if (ret) {
        LOG_ERR("Failed to initialize monitoring system (err %d)", ret);
    }

    // Initialize LEDs
    LOG_INF("Initializing LEDs...\n");

    ret = led_start();
    if (ret) {
        LOG_ERR("Failed to initialize LEDs (err %d)", ret);
        error_led_driver();
        return ret;
    }

    // Run the boot LED sequence
    boot_led_sequence();

    if (setting_ret) {
        error_settings();
        app_settings_save_dim_ratio(30);
    }

    // Initialize battery
#ifdef CONFIG_OMI_ENABLE_BATTERY
    ret = battery_init();
    if (ret) {
        LOG_ERR("Battery init failed (err %d)", ret);
        error_battery_init();
        return ret;
    }

    ret = battery_charge_start();
    if (ret) {
        LOG_ERR("Battery failed to start (err %d)", ret);
        error_battery_charge();
        return ret;
    }
    LOG_INF("Battery initialized");
#endif

    // Initialize button
#ifdef CONFIG_OMI_ENABLE_BUTTON
    ret = button_init();
    if (ret) {
        LOG_ERR("Failed to initialize Button (err %d)", ret);
        error_button();
        return ret;
    }
    LOG_INF("Button initialized");
    activate_button_work();
#endif

    // Initialize Haptic driver
#ifdef CONFIG_OMI_ENABLE_HAPTIC
    ret = haptic_init();
    if (ret) {
        LOG_ERR("Failed to initialize Haptic driver (err %d)", ret);
        error_haptic();
        // Non-critical, continue boot
    } else {
        LOG_INF("Haptic driver initialized");
        play_haptic_milli(50);
    }
#endif

    // SD Card
    ret = app_sd_init();
    if (ret) {
        LOG_ERR("Failed to initialize SD Card (err %d)", ret);
        error_sd_card();
        return ret;
    }

#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
    // Initialize storage service for offline audio
    ret = storage_init();
    if (ret) {
        LOG_ERR("Failed to initialize storage service (err %d)", ret);
        error_storage();
        // Non-critical, continue boot
    } else {
        LOG_INF("Storage service initialized");
    }
#endif

    // Indicate transport initialization
    LOG_PRINTK("\n");
    LOG_INF("Initializing transport...\n");

    // Start transport
    int transportErr;
    transportErr = transport_start();
    if (transportErr) {
        LOG_ERR("Failed to start transport (err %d)", transportErr);
        error_transport();
        return transportErr;
    }

    // Initialize codec
    LOG_INF("Initializing codec...\n");

    // Set codec callback
    set_codec_callback(codec_handler);
    ret = codec_start();
    if (ret) {
        LOG_ERR("Failed to start codec: %d", ret);
        error_codec();
        return ret;
    }

    // Initialize microphone
    LOG_INF("Initializing microphone...\n");
    set_mic_callback(mic_handler);
    ret = mic_start();
    if (ret) {
        LOG_ERR("Failed to start microphone: %d", ret);
        error_microphone();
        return ret;
    }

    LOG_INF("Device initialized successfully\n");

    // Show ready sequence
    boot_ready_sequence();

    while (1) {
        monitor_log_metrics();

        set_led_state();

        k_msleep(1000);
    }

    printk("Exiting omi...");
    return 0;
}
