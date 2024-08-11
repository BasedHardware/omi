#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include "transport.h"
#include "mic.h"
#include "utils.h"
#include "led.h"
#include "config.h"
#include "audio.h"
#include "codec.h"
#include "storage.h"

LOG_MODULE_REGISTER(main, CONFIG_LOG_DEFAULT_LEVEL);

static void codec_handler(uint8_t *data, size_t len)
{
    int err = broadcast_audio_packets(data, len);
    if (err) {
        LOG_ERR("Failed to broadcast audio packets: %d", err);
    }

    err = save_audio_to_storage(data, len);
    if (err) {
        LOG_ERR("Failed to save audio to storage: %d", err);
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
    LOG_ERR("Bluetooth assert: %s (type %d)", name ? name : "NULL", type);
}

static bool is_connected = false;
static bool is_recording = false;

static void update_led_state(void)
{
    set_led_state(is_connected, is_recording);
}

static void connection_callback(bool connected)
{
    is_connected = connected;
    update_led_state();
}

int main(void)
{
    int err;

    LOG_INF("Omi firmware starting...");

    err = led_start();
    if (err) {
        LOG_ERR("Failed to initialize LEDs: %d", err);
        return err;
    }
    set_led_red(true);  // Indicate startup with red LED

    LOG_INF("Initializing storage...");
    err = storage_init();
    if (err) {
        LOG_ERR("Failed to initialize storage: %d", err);
        return err;
    }

    err = transport_start(connection_callback);
    if (err) {
        LOG_ERR("Failed to start transport: %d", err);
        return err;
    }

    set_codec_callback(codec_handler);
    err = codec_start();
    if (err) {
        LOG_ERR("Failed to start codec: %d", err);
        return err;
    }

    set_mic_callback(mic_handler);
    err = mic_start();
    if (err) {
        LOG_ERR("Failed to start microphone: %d", err);
        return err;
    }

    LOG_INF("Omi firmware initialized successfully");
    set_led_red(false);  // Turn off red LED after successful initialization

    while (1) {
        // Check if recording should start or stop based on connection state
        bool should_record = is_connected;
        if (should_record != is_recording) {
            is_recording = should_record;
            if (is_recording) {
                LOG_INF("Starting recording");
                err = mic_start_recording();
                if (err) {
                    LOG_ERR("Failed to start recording: %d", err);
                    is_recording = false;
                }
            } else {
                LOG_INF("Stopping recording");
                err = mic_stop_recording();
                if (err) {
                    LOG_ERR("Failed to stop recording: %d", err);
                }
            }
            update_led_state();
        }

        // Perform any necessary periodic tasks here

        k_sleep(K_MSEC(100));  // Sleep for 100ms to prevent busy-waiting
    }

    // Unreachable
    return 0;
}
