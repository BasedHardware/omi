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
#ifdef CONFIG_OMI_ENABLE_MONITOR
#include "lib/core/monitor.h"
#endif
#include "lib/core/capture_mute.h"
#include "lib/core/settings.h"
#include "lib/core/transport.h"
#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
#include "lib/core/storage.h"
#endif
#ifndef CONFIG_OMI_NATIVE_SIM
#include <zephyr/fatal.h>
#endif

#include "boot_telemetry.h"
#include "imu.h"
#include "lib/core/sd_card.h"
#include "rtc.h"
#include "safe_mode.h"
#include "spi_flash.h"
#include "wdog_facade.h"

LOG_MODULE_REGISTER(main, CONFIG_LOG_DEFAULT_LEVEL);

#ifdef CONFIG_OMI_ENABLE_BATTERY
#define BATTERY_FULL_THRESHOLD_PERCENT 98 // 98%
extern uint8_t battery_percentage;
#endif
bool is_connected = false;
bool is_charging = false;
bool is_off = false;
bool blink_toggle = false;

static void codec_handler(uint8_t *data, size_t len)
{
#ifdef CONFIG_OMI_ENABLE_MONITOR
    monitor_inc_broadcast_audio();
#endif
    int err = broadcast_audio_packets(data, len);
    if (err) {
#ifdef CONFIG_OMI_ENABLE_MONITOR
        monitor_inc_broadcast_audio_failed();
#endif
    }
}

static void mic_handler(int16_t *buffer)
{
#ifdef CONFIG_OMI_ENABLE_MONITOR
    // Track total bytes processed (each sample is 2 bytes)
    monitor_inc_mic_buffer();
#endif

    // Hardware AAD (T5838) is handled inside mic.c; the mic callback only
    // forwards audio to the codec here.
    int err = codec_receive_pcm(buffer, MIC_BUFFER_SAMPLES);
    if (err) {
        LOG_ERR("Failed to process PCM data: %d", err);
    }
}

void set_led_state()
{
    // If device is off, turn off all LEDs immediately
    if (is_off) {
        led_off();
        return;
    }

#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
    // If RTC not synced, blink red to warn user to connect phone app
    if (!rtc_is_valid()) {
        set_led_green(is_charging);
        set_led_blue(!blink_toggle && is_connected);
        set_led_red(blink_toggle);
        blink_toggle = !blink_toggle;
        return;
    }
#endif

    bool green = false;
    bool blue = false;
    bool red = false;

    if (is_charging) {
#ifdef CONFIG_OMI_ENABLE_BATTERY
        // Solid green if battery is full (>= BATTERY_FULL_THRESHOLD_PERCENT)
        if (battery_percentage >= BATTERY_FULL_THRESHOLD_PERCENT) {
            green = true;
        } else
#endif
        {
            green = blink_toggle;
            blue = !blink_toggle && is_connected;
            red = !blink_toggle && !is_connected;
            blink_toggle = !blink_toggle;
        }
    } else {
        blue = is_connected;
        red = !is_connected;
    }

    set_led_green(green);
    set_led_blue(blue);
    set_led_red(red);
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

#ifdef CONFIG_OMI_NATIVE_SIM
    safe_mode_early_boot();
#endif

    // Initialize watchdog first to catch any early freezes
    ret = watchdog_init();
    if (ret) {
        LOG_WRN("Watchdog init failed (err %d), continuing without watchdog", ret);
    }

    /* Decide from validated RAM first. Only cold/invalid RAM (or an interrupted
     * DFU commit) needs the isolated bootstate read. Never load app settings in SAFE.
     */
    safe_mode_restore();
    if (safe_mode_boot()) {
        safe_mode_run();
        return 0;
    }
    int setting_ret = app_settings_init();
    safe_mode_settings_ready(setting_ret);
    if (!setting_ret) {
        omi_boot_telemetry_open();
    }
    ret = safe_mode_devices_init();
    if (ret) {
        LOG_ERR("Deferred device initialization failed (%d)", ret);
        return ret;
    }
#ifdef CONFIG_OMI_FAULT_INJECT_HARD_FAULT
    printk("FAULT_INJECT: fatal before BLE\n");
    k_msleep(CONFIG_OMI_FAULT_INJECT_HARD_FAULT_DELAY_MS);
    __asm__ volatile("udf #0");
    CODE_UNREACHABLE;
#endif

    // Initialize Haptic driver first; this is building up for future of omi turn on sequence - long press to turn on
    // instead of short press
#ifdef CONFIG_OMI_ENABLE_HAPTIC
    ret = haptic_init();
    if (ret) {
        LOG_ERR("Failed to initialize Haptic driver (err %d)", ret);
        error_haptic();
        // Non-critical, continue boot
    } else {
        LOG_INF("Haptic driver initialized");
        play_haptic_milli(100);
    }
#endif

    // Initialize LEDs
    LOG_INF("Initializing LEDs...\n");

    ret = led_start();
    if (ret) {
        LOG_ERR("Failed to initialize LEDs (err %d)", ret);
        error_led_driver();
        return ret;
    }

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
    if (setting_ret) {
        LOG_ERR("Failed to initialize settings (err %d)", setting_ret);
    }

    // Initialize RTC from saved epoch
    init_rtc();
    if (!rtc_is_valid()) {
        LOG_WRN("UTC time not synchronized yet");
    }

    (void) lsm6dsl_time_boot_adjust_rtc();

#ifdef CONFIG_OMI_ENABLE_MONITOR
    // Initialize monitoring system
    LOG_INF("Initializing monitoring system...\n");
    ret = monitor_init();
    if (ret) {
        LOG_ERR("Failed to initialize monitoring system (err %d)", ret);
    }
#endif

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

    // SD Card
    ret = app_sd_init();
    if (ret) {
        LOG_ERR("Failed to initialize SD Card (err %d)", ret);
        error_sd_card();
        return ret;
    }

    /* app_sd_init() clears the in-memory write-pause bit. Re-apply the
     * persisted mute so a reboot cannot resume capture (issue #5054). */
    capture_mute_apply_runtime();

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
    // Hardware AAD (T5838) is started inside mic_start().

    LOG_INF("Device initialized successfully\n");

    safe_mode_main_loop_ready(transport_advertising_started());
    while (1) {
#ifdef CONFIG_OMI_FAULT_INJECT_WDT_STARVE
        if (k_uptime_get() >= 30000) {
            printk("FAULT_INJECT: watchdog starvation\n");
            for (;;) {
                k_msleep(1000);
            }
        }
#endif
        safe_mode_poll();
        watchdog_feed();
#ifdef CONFIG_OMI_ENABLE_MONITOR
        monitor_log_metrics();
#endif

        set_led_state();
        k_msleep(1000);
    }

    printk("Exiting omi...");
    return 0;
}
