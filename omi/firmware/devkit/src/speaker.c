#include "speaker.h"

#include <math.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/l2cap.h>
#include <zephyr/bluetooth/services/bas.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/i2s.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/logging/log_ctrl.h>

LOG_MODULE_REGISTER(speaker, CONFIG_LOG_DEFAULT_LEVEL);

#define MAX_BLOCK_SIZE 10000 // ~0.31 s of 8 kHz stereo 16-bit

#define SAMPLE_FREQUENCY 8000
#define NUMBER_OF_CHANNELS 2
#define PACKET_SIZE 400
#define WORD_SIZE 16
#define NUM_CHANNELS 2

#define PI 3.14159265358979323846

#define MAX_HAPTIC_DURATION 5000

// Streaming queue: one block holds exactly one 400-byte mono packet after the
// mono-to-stereo duplication (400 * 2 channels * 2 bytes = 25 ms of audio).
// Twelve blocks add ~300 ms of slack so a stalled BLE write cannot underrun
// the I2S peripheral.
#define I2S_TX_BLOCK_SIZE 800
#define I2S_TX_BLOCK_COUNT 12
// A 4-byte write re-arms the length header only while the stream is idle, or
// after the host has been quiet for this long: mid-stream, four bytes can be
// legitimate tail audio.
#define STREAM_IDLE_REARM_MS 2000

K_MEM_SLAB_DEFINE_STATIC(mem_slab, I2S_TX_BLOCK_SIZE, I2S_TX_BLOCK_COUNT, 2);

struct device *audio_speaker;

static uint8_t stereo_stage[I2S_TX_BLOCK_SIZE];
static uint8_t chime_buffer[MAX_BLOCK_SIZE];
static uint32_t stream_remaining;
static bool stream_active;
static bool stream_started;
static int64_t last_packet_ms;

struct gpio_dt_spec haptic_gpio_pin = {.port = DEVICE_DT_GET(DT_NODELABEL(gpio1)),
                                       .pin = 11,
                                       .dt_flags = GPIO_INT_DISABLE};

struct gpio_dt_spec speaker_gpio_pin = {.port = DEVICE_DT_GET(DT_NODELABEL(gpio0)),
                                        .pin = 4,
                                        .dt_flags = GPIO_INT_DISABLE};

// ble service
//

static void speaker_ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value);
static ssize_t speaker_haptic_handler(struct bt_conn *conn,
                                      const struct bt_gatt_attr *attr,
                                      const void *buf,
                                      uint16_t len,
                                      uint16_t offset,
                                      uint8_t flags);

static struct bt_uuid_128 speaker_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0xCAB1AB95, 0x2EA5, 0x4F4D, 0xBB56, 0x874B72CFC984));
static struct bt_uuid_128 speaker_haptic_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0xCAB1AB96, 0x2EA5, 0x4F4D, 0xBB56, 0x874B72CFC984));

static struct bt_gatt_attr speaker_service_attr[] = {
    BT_GATT_PRIMARY_SERVICE(&speaker_uuid),
    BT_GATT_CHARACTERISTIC(&speaker_haptic_uuid.uuid,
                           BT_GATT_CHRC_WRITE | BT_GATT_CHRC_NOTIFY,
                           BT_GATT_PERM_WRITE,
                           NULL,
                           speaker_haptic_handler,
                           NULL),
    BT_GATT_CCC(speaker_ccc_config_changed_handler, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
};
static struct bt_gatt_service speaker_service = BT_GATT_SERVICE(speaker_service_attr);

void register_speaker_service()
{
    bt_gatt_service_register(&speaker_service);
}

static void speaker_ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value)
{
    if (value == BT_GATT_CCC_NOTIFY) {
        LOG_INF("Client subscribed for notifications");
    } else if (value == 0) {
        LOG_INF("Client unsubscribed from notifications");
    } else {
        LOG_ERR("Invalid CCC value: %u", value);
    }
}

static ssize_t speaker_haptic_handler(struct bt_conn *conn,
                                      const struct bt_gatt_attr *attr,
                                      const void *buf,
                                      uint16_t len,
                                      uint16_t offset,
                                      uint8_t flags)
{
    LOG_INF("play the haptic");

    uint8_t value = ((uint8_t *) buf)[0];
    LOG_INF("value %d  ", value);

    if (value < 1 || value > 3) {
        return 0;
    }

    if (value == 1) {
        play_haptic_milli(20);
    } else if (value == 2) {
        play_haptic_milli(50);
    } else if (value == 3) {
        play_haptic_milli(500);
    }

    return 1;
}

int speaker_init()
{
    LOG_INF("Speaker init");
    audio_speaker = device_get_binding("I2S_0");

    if (!device_is_ready(audio_speaker)) {
        LOG_ERR("Speaker device is not supported : %s", audio_speaker->name);
        return -1;
    }

    if (gpio_is_ready_dt(&speaker_gpio_pin)) {
        LOG_PRINTK("Speaker Pin ready\n");
    } else {
        LOG_PRINTK("Error setting up speaker Pin\n");
        return -1;
    }
    if (gpio_pin_configure_dt(&speaker_gpio_pin, GPIO_OUTPUT_INACTIVE) < 0) {
        LOG_PRINTK("Error setting up Haptic Pin\n");
        return -1;
    }
    gpio_pin_set_dt(&speaker_gpio_pin, 1);

    struct i2s_config config = {
        .word_size = WORD_SIZE,                       // how long is one left/right word.
        .channels = NUMBER_OF_CHANNELS,               // how many words in a frame 2
        .format = I2S_FMT_DATA_FORMAT_LEFT_JUSTIFIED, // format
        // .format = I2S_FMT_DATA_FORMAT_I2S,
        .options =
            I2S_OPT_FRAME_CLK_MASTER | I2S_OPT_BIT_CLK_MASTER | I2S_OPT_BIT_CLK_GATED, // how to configure the mclock
        .frame_clk_freq = SAMPLE_FREQUENCY,                                            /* Sampling rate */
        .mem_slab = &mem_slab,           /* Memory slab to store rx/tx data */
        .block_size = I2S_TX_BLOCK_SIZE, /* one packet, duplicated to stereo */
        .timeout = 1000,                 /* ms a full Tx queue may stall a write; a blocked write delays BLE pacing */
    };
    int err = i2s_configure(audio_speaker, I2S_DIR_TX, &config);
    if (err) {
        LOG_ERR("Failed to configure Speaker (%d)", err);
        return -1;
    }

    stream_remaining = 0;
    stream_active = false;
    stream_started = false;
    last_packet_ms = 0;

    return 0;
}

uint16_t speak(uint16_t len, const void *buf) // direct from bt
{
    if (len == 0) {
        return 0;
    }

    int64_t now = k_uptime_get();

    // A 4-byte write arms a new stream while idle, or after the host has gone
    // quiet: mid-stream those four bytes are tail audio, not a header. This is
    // why the old firmware silently stalled on a total that was a multiple of
    // PACKET_SIZE - the '>' and '<' branches left the == case unhandled.
    if (len == 4 && (!stream_active || now - last_packet_ms > STREAM_IDLE_REARM_MS)) {
        stream_remaining = ((const uint32_t *) buf)[0];
        stream_active = stream_remaining > 0;
        stream_started = false;
        LOG_INF("About to write %u bytes", stream_remaining);
        return len;
    }

    if (!stream_active) {
        LOG_WRN("Speaker data before header, dropped %u bytes", len);
        return 0;
    }
    last_packet_ms = now;

    // Duplicate the mono packet into both channels and queue it as its own I2S
    // block. The driver, not a fixed sleep, now paces the stream: i2s_write
    // blocks when the queue is full, which delays the BLE write response.
    size_t samples = len / 2;
    const size_t max_samples = I2S_TX_BLOCK_SIZE / (NUM_CHANNELS * sizeof(int16_t));
    if (samples > max_samples) {
        samples = max_samples;
    }
    int16_t *stage = (int16_t *) stereo_stage;
    for (size_t i = 0; i < samples; i++) {
        const int16_t sample = ((const int16_t *) buf)[i];
        stage[2 * i] = sample;
        stage[2 * i + 1] = sample;
    }
    size_t staged = samples * NUM_CHANNELS * sizeof(int16_t);
    memset(&stereo_stage[staged], 0, I2S_TX_BLOCK_SIZE - staged);

    if (!stream_started) {
        int err = i2s_trigger(audio_speaker, I2S_DIR_TX, I2S_TRIGGER_START);
        if (err) {
            LOG_WRN("Failed to start I2S transmission: %d", err);
        }
        stream_started = true;
    }

    int res = i2s_write(audio_speaker, stereo_stage, I2S_TX_BLOCK_SIZE);
    if (res) {
        LOG_WRN("Failed to write I2S data: %d", res);
    }

    stream_remaining = stream_remaining > len ? stream_remaining - len : 0;

    if (stream_remaining == 0) {
        res = i2s_trigger(audio_speaker, I2S_DIR_TX, I2S_TRIGGER_DRAIN);
        if (res) {
            LOG_WRN("Failed to drain I2S transmission: %d", res);
        }
        stream_active = false;
        stream_started = false;
        LOG_INF("Speaker stream done");
    }

    return len;
}

void generate_gentle_chime(int16_t *buffer, int num_samples)
{
    LOG_INF("Generating gentle chime");                                 // 2500
    const float frequencies[] = {523.25, 659.25, 783.99, 1046.50};      // C5, E5, G5, C6
    const int num_freqs = sizeof(frequencies) / sizeof(frequencies[0]); // 4

    for (int i = 0; i < num_samples; i++) {
        float t = (float) i / SAMPLE_FREQUENCY; // 0.000125
        float sample = 0;
        for (int j = 0; j < num_freqs; j++) {
            sample += sinf(2 * PI * frequencies[j] * t) * (1.0 - t);
        }
        int16_t int_sample = (int16_t) (sample / num_freqs * 32767 * 0.5);
        buffer[i * NUM_CHANNELS] = int_sample;
        buffer[i * NUM_CHANNELS + 1] = int_sample;
    }
    LOG_INF("Done generating gentle chime");
}

int play_boot_sound(void)
{
    int ret;
    int16_t *buffer = (int16_t *) chime_buffer;
    const int samples_per_block = MAX_BLOCK_SIZE / (NUM_CHANNELS * sizeof(int16_t));

    generate_gentle_chime(buffer, samples_per_block);
    LOG_INF("Writing to speaker");
    k_sleep(K_MSEC(100));

    // Start before the write: the chime spans more blocks than the queue holds,
    // so the driver must be consuming while the remaining blocks are written.
    ret = i2s_trigger(audio_speaker, I2S_DIR_TX, I2S_TRIGGER_START);
    if (ret) {
        LOG_ERR("Failed to start I2S transmission: %d", ret);
        return ret;
    }

    ret = i2s_write(audio_speaker, buffer, MAX_BLOCK_SIZE);
    if (ret) {
        LOG_ERR("Failed to write initial I2S data: %d", ret);
        return ret;
    }

    ret = i2s_trigger(audio_speaker, I2S_DIR_TX, I2S_TRIGGER_DRAIN);
    if (ret != 0) {
        LOG_ERR("Failed to drain I2S transmission: %d", ret);
        return ret;
    }
    // DRAIN stops the peripheral once the queue empties (~0.3 s of chime).
    // The old 3 s wait was padding around a blocking write, not a requirement.
    k_sleep(K_MSEC(500));

    return 0;
}

int init_haptic_pin()
{
    if (gpio_is_ready_dt(&haptic_gpio_pin)) {
        LOG_INF("Haptic Pin ready");
    } else {
        LOG_ERR("Error setting up Haptic Pin");
        return -1;
    }
    if (gpio_pin_configure_dt(&haptic_gpio_pin, GPIO_OUTPUT_INACTIVE) < 0) {
        LOG_ERR("Error setting up Haptic Pin");
        return -1;
    }
    gpio_pin_set_dt(&haptic_gpio_pin, 0);

    return 0;
}
K_SEM_DEFINE(haptic_sem, 0, 1);
void haptic_timer_callback(struct k_timer *timer);

K_TIMER_DEFINE(my_status_timer, haptic_timer_callback, NULL);

void haptic_timer_callback(struct k_timer *timer)
{
    // k_sem_give(&haptic_sem);
    gpio_pin_set_dt(&haptic_gpio_pin, 0);
}

void play_haptic_milli(uint32_t duration)
{
    if (duration > MAX_HAPTIC_DURATION) {
        LOG_ERR("Duration is too long");
        return;
    }
    gpio_pin_set_dt(&haptic_gpio_pin, 1);
    // if (k_sem_take(&haptic_sem, K_MSEC(50)) != 0)
    // {

    // }
    // else
    // {
    k_timer_start(&my_status_timer, K_MSEC(duration), K_NO_WAIT);
    // }
}

void speaker_off()
{

    gpio_pin_set_dt(&speaker_gpio_pin, 0);
}
