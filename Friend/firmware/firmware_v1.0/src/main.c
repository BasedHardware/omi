#include <zephyr/logging/log.h>
#include <zephyr/kernel.h>
#include "transport.h"
#include "mic.h"
#include "utils.h"
#include "led.h"
#include "config.h"
#include "codec.h"
#include "button.h"
#include "sdcard.h"
#include "storage.h"
#include "speaker.h"
#include "usb.h"
#define BOOT_BLINK_DURATION_MS 600
#define BOOT_PAUSE_DURATION_MS 200
#define VBUS_DETECT (1U << 20)
#define WAKEUP_DETECT (1U << 16)
LOG_MODULE_REGISTER(main, CONFIG_LOG_DEFAULT_LEVEL);

static void codec_handler(uint8_t *data, size_t len)
{
    int err = broadcast_audio_packets(data, len);
    if (err)
    {
        LOG_ERR("Failed to broadcast audio packets: %d", err);
    }
}

static void mic_handler(int16_t *buffer)
{
    int err = codec_receive_pcm(buffer, MIC_BUFFER_SAMPLES);
    if (err)
    {
        LOG_ERR("Failed to process PCM data: %d", err);
    }
}

void bt_ctlr_assert_handle(char *name, int type)
{
    LOG_INF("Bluetooth assert: %s (type %d)", name ? name : "NULL", type);
}


bool is_connected = false;
bool is_charging = false;
extern bool is_off;
extern bool usb_charge;
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

void set_led_state()
{
    // Recording and connected state - BLUE

    if(usb_charge)
    {
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
    if(is_off)
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

    // Recording but lost connection - RED
    if (!is_connected)
    {
        set_led_red(true);
        set_led_blue(false);
        return;
    }
}

int main(void)
{
    int err;

    // Store reset reason code
    uint32_t reset_reason = NRF_POWER->RESETREAS;

    NRF_POWER->DCDCEN=1;
    NRF_POWER->DCDCEN0=1;
    NRF_POWER->RESETREAS=1;

    LOG_INF("Booting...\n");

    LOG_INF("Model: %s", CONFIG_BT_DIS_MODEL);
    LOG_INF("Firmware revision: %s", CONFIG_BT_DIS_FW_REV_STR);
    LOG_INF("Hardware revision: %s", CONFIG_BT_DIS_HW_REV_STR);

    LOG_DBG("Reset reason: %d\n", reset_reason);

    LOG_PRINTK("\n");
    LOG_INF("Initializing LEDs...\n");

    err = led_start();
    if (err)
    {
        LOG_ERR("Failed to initialize LEDs (err %d)", err);
        return err;
    }

    // Run the boot LED sequence
    boot_led_sequence();

    // Enable battery
#ifdef CONFIG_OMI_ENABLE_BATTERY
    err = battery_init();
    if (err)
    {
        LOG_ERR("Battery init failed (err %d)", err);
        return err;
    }

    err == battery_charge_start();
    if (err)
    {
        LOG_ERR("Battery failed to start (err %d)", err);
        return err;
    }
    LOG_INF("Battery initialized");
#endif


    // Enable button
#ifdef CONFIG_OMI_ENABLE_BUTTON
    err = button_init();
    if (err)
    {
        LOG_ERR("Failed to initialize Button (err %d)", err);
        return err;
    }
    LOG_INF("Button initialized");
    activate_button_work();
#endif

    // Enable accelerometer
#ifdef CONFIG_OMI_ENABLE_ACCELEROMETER
    err = accel_start();
    if (err)
    {
        LOG_ERR("Accelerometer failed to activated (err %d)", err);
        return err;
    }
    LOG_INF("Accelerometer initialized");
#endif

    // Enable speaker
#ifdef CONFIG_OMI_ENABLE_SPEAKER
    err = speaker_init();
    if (err)
    {
        LOG_ERR("Speaker failed to start");
        return err;
    }
    LOG_INF("Speaker initialized");
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

    // Enable haptic
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

    // Enable usb
#ifdef CONFIG_ENABLE_USB
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
        // TODO: Detect the current core is app core or net core
        // // Blink green LED to indicate error
        // for (int i = 0; i < 5; i++)
        // {
        //     set_led_green(!gpio_pin_get_dt(&led_green));
        //     k_msleep(200);
        // }
        // set_led_green(false);
        // // return err;
        return transportErr;
    }

#ifdef CONFIG_OMI_ENABLE_SPEAKER
#ifndef CONFIG_UART_CONSOLE
    LOG_PRINTK("\n");
    LOG_INF("Play boot sound...\n");

    // This messes up the UART console, so comment out
    // if console logs are enabled
    play_boot_sound();
#else
    LOG_INF("UART console enabled, not playing boot sound");
#endif
#endif

    LOG_PRINTK("\n");
    LOG_INF("Initializing codec...\n");

    set_led_blue(true);

    // Audio codec(opus) callback
    set_codec_callback(codec_handler);
    err = codec_start();
    if (err)
    {
        LOG_ERR("Failed to start codec: %d", err);
        // Blink blue LED to indicate error
        for (int i = 0; i < 5; i++)
        {
            set_led_blue(!gpio_pin_get_dt(&led_blue));
            k_msleep(200);
        }
        set_led_blue(false);
        return err;
    }

#ifdef CONFIG_OMI_ENABLE_HAPTIC
    play_haptic_milli(500);
#endif
    set_led_blue(false);

    // Indicate microphone initialization
    LOG_PRINTK("\n");
    LOG_INF("Initializing microphone...\n");

    set_led_red(true);
    set_led_green(true);

    set_mic_callback(mic_handler);
    err = mic_start();
    if (err)
    {
        LOG_ERR("Failed to start microphone: %d", err);
        // Blink red and green LEDs to indicate error
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

    set_led_red(false);
    set_led_green(false);

    // Indicate successful initialization
    LOG_PRINTK("\n");
    LOG_INF("Device initialized successfully\n");

    set_led_blue(true);
    k_msleep(1000);
    set_led_blue(false);

    // Main loop
    LOG_PRINTK("\n");
    LOG_INF("Entering main loop...\n");

    while (1)
    {
        set_led_state();
        k_msleep(500);
    }

    // Unreachable
    return 0;
}
