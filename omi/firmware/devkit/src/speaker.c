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

// Block geometry mirrors the original burst implementation: one 10 KB stereo
// block = 312 ms of 8 kHz audio. The queue is sized so a whole clip is
// enqueued BEFORE START: i2s_nrfx is only race-safe for thread-side writes in
// the READY state - once the ISR owns the buffer chain, a thread supplying
// next-buffers alongside an END event strands the peripheral in
// I2S_STATE_ERROR (observed live: every write after the first post-START
// write returned -EIO until reboot). Seven blocks = ~2.2 s per continuous
// stream; longer content chains back-to-back streams (each re-arms after the
// previous DRAIN, which the write retry below waits out).
#define MAX_BLOCK_SIZE 10000
#define I2S_TX_BLOCK_SIZE 10000
#define I2S_TX_BLOCK_COUNT 7

#define SAMPLE_FREQUENCY 8000
#define NUMBER_OF_CHANNELS 2
#define PACKET_SIZE 400
#define WORD_SIZE 16
#define NUM_CHANNELS 2

#define PI 3.14159265358979323846

#define MAX_HAPTIC_DURATION 5000
// A 4-byte write re-arms the length header only while the stream is idle, or
// after the host has been quiet for this long: mid-stream, four bytes can be
// legitimate tail audio.
#define STREAM_IDLE_REARM_MS 2000

K_MEM_SLAB_DEFINE_STATIC(mem_slab, I2S_TX_BLOCK_SIZE, I2S_TX_BLOCK_COUNT, 2);

struct device *audio_speaker;

// Accumulation buffer: mono packets are duplicated into stereo here, and the
// buffer is handed to the I2S driver one full 10 KB block at a time.
static uint8_t tx_block[I2S_TX_BLOCK_SIZE];
static size_t tx_used;
static uint32_t stream_remaining;
static bool stream_active;
static bool stream_started;
static bool speaker_ready;
static int64_t last_packet_ms;

// speak() stages on the BT RX thread while play_talk_cue() runs on the system
// workqueue; both write tx_block and drive the same I2S queue, so an
// interleaved pair garbles audio. One mutex serializes every staging path.
K_MUTEX_DEFINE(speaker_tx_mutex);

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
        .block_size = I2S_TX_BLOCK_SIZE, /* same geometry the burst path proved */
        .timeout = 1000,                 /* a full Tx queue stalls the write up to this long;
                                            the stalled write delays the BLE response, which
                                            paces the host - no fixed sleep needed */
    };
    int err = i2s_configure(audio_speaker, I2S_DIR_TX, &config);
    if (err) {
        LOG_ERR("Failed to configure Speaker (%d)", err);
        return -1;
    }

    stream_remaining = 0;
    stream_active = false;
    stream_started = false;
    tx_used = 0;
    last_packet_ms = 0;
    speaker_ready = true;

    return 0;
}

// Enqueue the accumulation buffer as one full pre-START block. Thread-side
// writes are ONLY race-safe before START: i2s_nrfx_write, when called while
// RUNNING with the ISR mid-END, calls next_buffers_set out of turn, fails
// with -EIO, and the missed END strands the peripheral in I2S_STATE_ERROR
// (observed live: first block plays, every later write dies until reboot).
// So speak() queues every block in READY and STARTs once, at stream end.
static int flush_block(void)
{
    if (tx_used == 0) {
        return 0;
    }
    if (tx_used < I2S_TX_BLOCK_SIZE) {
        memset(&tx_block[tx_used], 0, I2S_TX_BLOCK_SIZE - tx_used);
    }
    tx_used = 0;

    void *block;
    int ret = k_mem_slab_alloc(&mem_slab, &block, K_MSEC(1000));
    if (ret) {
        LOG_WRN("No free I2S block (%d), dropping", ret);
        return ret;
    }
    memcpy(block, tx_block, I2S_TX_BLOCK_SIZE);

    // A previous stream's DRAIN leaves the driver in STOPPING, where writes
    // return -EIO; the retry waits it out (<= ~600 ms) so back-to-back
    // transmissions from compat clients lose nothing.
    for (int r = 0; r < 12; r++) {
        ret = i2s_write(audio_speaker, block, I2S_TX_BLOCK_SIZE);
        if (ret == 0 || ret != -EIO) {
            break;
        }
        k_sleep(K_MSEC(50));
    }
    if (ret) {
        LOG_WRN("Failed to write I2S block: %d", ret);
        k_mem_slab_free(&mem_slab, block); // write did not take ownership
        return ret;
    }
    return 0;
}

uint16_t speak(uint16_t len, const void *buf) // direct from bt
{
    if (len == 0) {
        return 0;
    }

    int64_t now = k_uptime_get();
    k_mutex_lock(&speaker_tx_mutex, K_FOREVER);

    // A 4-byte write arms a new stream while idle, or after the host has gone
    // quiet: mid-stream those four bytes are tail audio, not a header. This is
    // also why the old firmware stalled on a total that was a multiple of
    // PACKET_SIZE - its '>' and '<' branches left the == case unhandled.
    if (len == 4 && (!stream_active || now - last_packet_ms > STREAM_IDLE_REARM_MS)) {
        stream_remaining = ((const uint32_t *) buf)[0];
        stream_active = stream_remaining > 0;
        stream_started = false;
        tx_used = 0;
        // Self-heal: an overflowed stream can strand i2s_nrfx in
        // I2S_STATE_ERROR (sticky: every write -EIO until reset). PREPARE is
        // the driver's ERROR->READY recovery and is rejected harmlessly from
        // every other state, so a new transmission always clears the trap.
        (void) i2s_trigger(audio_speaker, I2S_DIR_TX, I2S_TRIGGER_PREPARE);
        LOG_INF("About to write %u bytes", stream_remaining);
        k_mutex_unlock(&speaker_tx_mutex);
        return len;
    }

    if (!stream_active) {
        LOG_WRN("Speaker data before header, dropped %u bytes", len);
        k_mutex_unlock(&speaker_tx_mutex);
        return 0;
    }
    last_packet_ms = now;

    // Duplicate mono samples into both channels in the accumulation buffer. A
    // packet that would overflow the current block is split across two flushes.
    const int16_t *mono = (const int16_t *) buf;
    size_t samples = len / 2;
    for (size_t i = 0; i < samples; i++) {
        if (tx_used + 2 * sizeof(int16_t) > I2S_TX_BLOCK_SIZE) {
            flush_block();
        }
        int16_t *out = (int16_t *) &tx_block[tx_used];
        out[0] = mono[i];
        out[1] = mono[i];
        tx_used += 2 * sizeof(int16_t);
    }

    stream_remaining = stream_remaining > len ? stream_remaining - len : 0;

    if (stream_remaining == 0) {
        int ret = flush_block();
        // All blocks are queued in READY; one START hands the chain to the ISR,
        // which supplies each block at END and drives STOPPING -> READY after
        // the DRAIN below. No further thread-side writes happen during play.
        int start_ret = i2s_trigger(audio_speaker, I2S_DIR_TX, I2S_TRIGGER_START);
        if (start_ret == 0) {
            stream_started = true;
        } else {
            LOG_WRN("Failed to start I2S stream: %d", start_ret);
        }
        if (stream_started) {
            ret = i2s_trigger(audio_speaker, I2S_DIR_TX, I2S_TRIGGER_DRAIN);
            if (ret) {
                LOG_WRN("Failed to drain I2S transmission: %d", ret);
            }
        }
        stream_active = false;
        stream_started = false;
        LOG_INF("Speaker stream done");
    }

    k_mutex_unlock(&speaker_tx_mutex);
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
    k_mutex_lock(&speaker_tx_mutex, K_FOREVER);
    int16_t *buffer = (int16_t *) tx_block;
    const int chime_frames = MAX_BLOCK_SIZE / (NUM_CHANNELS * sizeof(int16_t));

    generate_gentle_chime(buffer, chime_frames);
    LOG_INF("Writing to speaker");
    k_sleep(K_MSEC(100));

    tx_used = MAX_BLOCK_SIZE; // exactly one block
    flush_block();

    int ret = i2s_trigger(audio_speaker, I2S_DIR_TX, I2S_TRIGGER_START);
    if (ret) {
        LOG_ERR("Chime start failed: %d", ret);
        k_mutex_unlock(&speaker_tx_mutex);
        return ret;
    }
    ret = i2s_trigger(audio_speaker, I2S_DIR_TX, I2S_TRIGGER_DRAIN);
    if (ret) {
        LOG_ERR("Failed to drain I2S transmission: %d", ret);
        k_mutex_unlock(&speaker_tx_mutex);
        return ret;
    }
    // DRAIN stops the peripheral once the queue empties (~0.3 s of chime).
    k_sleep(K_MSEC(500));
    k_mutex_unlock(&speaker_tx_mutex);

    return 0;
}

void play_talk_cue(void)
{
    if (!speaker_ready) {
        return;
    }
    k_mutex_lock(&speaker_tx_mutex, K_FOREVER);
    if (stream_active && k_uptime_get() - last_packet_ms <= STREAM_IDLE_REARM_MS) {
        // A live BLE stream owns the queue; interleaved cue blocks would garble
        // the audio mid-sentence. The BLE DOUBLE_TAP notify still fires. Only a
        // FRESH stream may silence the cue: speak() re-arms after this same
        // window when a host abandons a stream mid-way, so an old flag must not
        // mute the cue forever.
        LOG_INF("Talk cue skipped: speaker stream in progress");
        k_mutex_unlock(&speaker_tx_mutex);
        return;
    }

    // Two quick ascending blips (A5 -> E6, ~83 ms each): "speak now".
    // Padded into one block - the same write size the burst path proved.
    int16_t *buffer = (int16_t *) tx_block;
    const int note_samples = SAMPLE_FREQUENCY / 12;
    const float freqs[2] = {880.0f, 1318.51f};
    for (int note = 0; note < 2; note++) {
        for (int i = 0; i < note_samples; i++) {
            float t = (float) i / SAMPLE_FREQUENCY;
            float sample = sinf(2 * PI * freqs[note] * t) * (1.0f - t * 10.0f) * 0.5f;
            int16_t v = (int16_t) (sample * 32767);
            int idx = note * note_samples + i;
            buffer[idx * 2] = v;
            buffer[idx * 2 + 1] = v;
        }
    }
    tx_used = 2 * note_samples * NUM_CHANNELS * sizeof(int16_t);
    flush_block(); // queue-only (READY): pads to a full block and enqueues

    int ret;
    for (int r = 0; r < 12; r++) {
        // START is rejected while a previous stream's DRAIN is still winding
        // down (STOPPING). The retry loop waits it out, as flush_block() does
        // for writes. If the block still cannot start it stays queued; nothing
        // poisons the device, because PREPARE at the next transmission header
        // purges the queue before rebuilding it (driver: purge_queue + READY).
        ret = i2s_trigger(audio_speaker, I2S_DIR_TX, I2S_TRIGGER_START);
        if (ret == 0) {
            break;
        }
        k_sleep(K_MSEC(50));
    }
    if (ret) {
        LOG_WRN("Talk cue start failed: %d", ret);
        k_mutex_unlock(&speaker_tx_mutex);
        return;
    }
    ret = i2s_trigger(audio_speaker, I2S_DIR_TX, I2S_TRIGGER_DRAIN);
    if (ret) {
        LOG_WRN("Talk cue drain failed: %d", ret);
    }
    k_mutex_unlock(&speaker_tx_mutex);
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
