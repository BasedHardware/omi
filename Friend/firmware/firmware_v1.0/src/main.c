#include <zephyr/logging/log.h>
#include <zephyr/kernel.h>
#include "deepsleep_button.h"
#include "deep_sleep.h"
#include "transport.h"
#include "mic.h"
#include "utils.h"
#include "led.h"
#include "config.h"
#include "audio.h"
#include "codec.h"
#include "deep_sleep.h"

#define BOOT_BLINK_DURATION_MS 600
#define BOOT_PAUSE_DURATION_MS 200
#define LONG_PRESS_DURATION K_SECONDS(3)

LOG_MODULE_REGISTER(main, CONFIG_LOG_DEFAULT_LEVEL);
LOG_MODULE_REGISTER(main, LOG_LEVEL_INF);

static void codec_handler(uint8_t *data, size_t len)
{
	int err = broadcast_audio_packets(data, len);
    if (err) {
        LOG_ERR("Failed to broadcast audio packets: %d", err);
    }
}

static void mic_handler(int16_t *buffer)
{
    int err = codec_receive_pcm(buffer, MIC_BUFFER_SAMPLES);
    if (err) {
        LOG_ERR("Failed to process PCM data: %d", err);
    }
}

void bt_ctlr_assert_handle(char *name, int type)
{
	LOG_INF("Bluetooth assert: %s (type %d)", name ? name : "NULL", type);
}

bool is_connected = false;
bool is_charging = false;

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
	if (is_connected)
	{
		set_led_red(false);
		set_led_green(false);
		set_led_blue(true);
		return;
	}

	// Recording but lost connection - RED
	if (!is_connected)
	{
		set_led_red(true);
		set_led_green(false);
		set_led_blue(false);
		return;
	}

	// Not recording, but charging - WHITE
	if (is_charging)
	{
		set_led_red(true);
		set_led_green(true);
		set_led_blue(true);
		return;
	}

	// Not recording - OFF
	set_led_red(false);
	set_led_green(false);
	set_led_blue(false);
}

// void test_sd_card(void) {
//     char test_data[] = "Hello, SD card!";
//     int ret = create_file("test.txt");
//     if (ret) {
//         LOG_ERR("Failed to create test file: %d", ret);
//     }
//     ret = write_file((uint8_t *)test_data, strlen(test_data), false, true);
//     if (ret) {
//         LOG_ERR("Failed to write test data: %d", ret);
//     }
//     LOG_INF("Successfully wrote test data to SD card");
// }

// Main loop
int main(void)
{
	int err;

    LOG_INF("Friend device firmware starting...");
    err = led_start();
    if (err) {
        LOG_ERR("Failed to initialize LEDs: %d", err);
        return err;
    }
    // Run the boot LED sequence
    boot_led_sequence();

    configure_button_for_wake_up();


    // // Indicate storage initialization
    // set_led_red(true);
    // LOG_INF("Initializing storage...");
    // err = storage_init();
    // if (err) {
    //     LOG_ERR("Failed to initialize storage: %d", err);
    //     // Blink red LED to indicate error
    //     for (int i = 0; i < 5; i++) {
    //         set_led_red(!gpio_pin_get_dt(&led_red));
    //         k_msleep(200);
    //     }
    //     set_led_red(false);
    //     return err;
    // }
    // LOG_INF("Storage initialized successfully");
    // set_led_red(false);
    // test_sd_card();

    // Indicate transport initialization
    set_led_green(true);
    err = transport_start();
    if (err) {
        LOG_ERR("Failed to start transport: %d", err);
        // Blink green LED to indicate error
        for (int i = 0; i < 5; i++) {
            set_led_green(!gpio_pin_get_dt(&led_green));
            k_msleep(200);
        }
        set_led_green(false);
        return err;
    }
    set_led_green(false);

    // Indicate codec initialization
    set_led_blue(true);
    set_codec_callback(codec_handler);
    err = codec_start();
    if (err) {
        LOG_ERR("Failed to start codec: %d", err);
        // Blink blue LED to indicate error
        for (int i = 0; i < 5; i++) {
            set_led_blue(!gpio_pin_get_dt(&led_blue));
            k_msleep(200);
        }
        set_led_blue(false);
        return err;
    }
    set_led_blue(false);

    // Indicate microphone initialization
    set_led_red(true);
    set_led_green(true);
    LOG_INF("Starting microphone initialization");
    set_mic_callback(mic_handler);
    err = mic_start();
    if (err) {
        LOG_ERR("Failed to start microphone: %d", err);
        // Blink red and green LEDs to indicate error
        for (int i = 0; i < 5; i++) {
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
    LOG_INF("Omi firmware initialized successfully");
    set_led_blue(true);
    k_msleep(1000);
    set_led_blue(false);

	while (1)
	{
		set_led_state();

        //Deep sleep
        if (is_button_pressed()) {
            k_sleep(LONG_PRESS_DURATION);
            if (is_button_pressed()) {
                LOG_INF("Button long pressed, entering deep sleep...");
                enter_deep_sleep();
            }
        }

		k_msleep(500);
	}

	// Unreachable
	return 0;
}
