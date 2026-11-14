#include "speaker.h"

#include <errno.h>
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
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/byteorder.h>

LOG_MODULE_REGISTER(speaker, CONFIG_LOG_DEFAULT_LEVEL);

#define MAX_BLOCK_SIZE 10000 // 24000 * 2

#define BLOCK_COUNT 1
#define SAMPLE_FREQUENCY 8000
#define NUMBER_OF_CHANNELS 2
#define PACKET_SIZE 400
#define WORD_SIZE 16
#define NUM_CHANNELS 2

#define PI 3.14159265358979323846

#define MAX_HAPTIC_DURATION 5000
K_MEM_SLAB_DEFINE_STATIC(mem_slab, MAX_BLOCK_SIZE, BLOCK_COUNT, 2);

struct device *audio_speaker;

static void *rx_buffer;
// The slab owns the DMA buffer while I2S plays it. Only the speaker thread
// waits for its return; Bluetooth RX never sleeps for playback.
static uint16_t current_length;
static uint16_t offset;
static uint16_t playback_bytes;
static atomic_t playing;
static struct bt_conn *playback_conn;
K_SEM_DEFINE(playback_ready, 0, 1);

static int play_pcm_block(size_t bytes)
{
    void *block = rx_buffer;
    if (block == NULL)
        return -EIO;
    int result = i2s_write(audio_speaker, block, bytes);
    if (result < 0)
        return result;
    rx_buffer = NULL; // I2S now owns and eventually frees this slab block.
    result = i2s_trigger(audio_speaker, I2S_DIR_TX, I2S_TRIGGER_START);
    if (result == 0)
        result = i2s_trigger(audio_speaker, I2S_DIR_TX, I2S_TRIGGER_DRAIN);
    if (result < 0)
        i2s_trigger(audio_speaker, I2S_DIR_TX, I2S_TRIGGER_DROP);
    // One slab block: reacquiring it proves DMA has released the previous
    // transmission. The bound covers the maximum 312.5 ms audio block.
    int allocated = k_mem_slab_alloc(&mem_slab, &rx_buffer, K_MSEC(1000));
    if (allocated < 0) {
        rx_buffer = NULL;
        return allocated;
    }
    return result;
}

static void play_pending_block(void)
{
    int result = play_pcm_block(playback_bytes);
    struct bt_conn *conn = playback_conn;
    playback_conn = NULL;
    atomic_clear(&playing);
    speaker_notify_complete(conn, result == 0);
    bt_conn_unref(conn);
}

static void speaker_thread(void *a, void *b, void *c)
{
    ARG_UNUSED(a);
    ARG_UNUSED(b);
    ARG_UNUSED(c);
    while (true) {
        k_sem_take(&playback_ready, K_FOREVER);
        play_pending_block();
    }
}

K_THREAD_DEFINE(speaker_thread_id, 1024, speaker_thread, NULL, NULL, NULL, 7, 0, 0);

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
        .mem_slab = &mem_slab,        /* Memory slab to store rx/tx data */
        .block_size = MAX_BLOCK_SIZE, /* size of ONE memory block in bytes */
        .timeout = -1, /* Number of milliseconds to wait in case Tx queue is full or RX queue is empty, or 0, or
                          SYS_FOREVER_MS */
    };
    int err = i2s_configure(audio_speaker, I2S_DIR_TX, &config);
    if (err) {
        LOG_ERR("Failed to configure Speaker (%d)", err);
        return -1;
    }
    err = k_mem_slab_alloc(&mem_slab, &rx_buffer, K_MSEC(200));
    if (err) {
        LOG_INF("Failed to allocate memory for speaker%d)", err);
        return -1;
    }

    return 0;
}

int speak(uint16_t len, const void *buf, struct bt_conn *conn)
{
    if (atomic_get(&playing))
        return -EBUSY;
    if (rx_buffer == NULL)
        return -EIO;
    if (current_length == 0) {
        if (len != 4)
            return -EINVAL;
        uint32_t size = sys_get_le32(buf);
        if (size == 0 || size > MAX_BLOCK_SIZE / 2 || (size & 1))
            return -EINVAL;
        current_length = size;
        offset = 0;
        return len;
    }
    if (len == 0 || len > PACKET_SIZE || (len & 1) || len > current_length)
        return -EINVAL;
    const uint8_t *samples = buf;
    int16_t *stereo = (int16_t *) rx_buffer;
    for (size_t i = 0; i < len; i += 2) {
        int16_t sample = (int16_t) sys_get_le16(samples + i);
        stereo[offset + i] = sample;
        stereo[offset + i + 1] = sample;
    }
    offset += len;
    current_length -= len;
    if (current_length == 0) {
        playback_bytes = offset * 2;
        playback_conn = bt_conn_ref(conn);
        atomic_set(&playing, 1);
        k_sem_give(&playback_ready);
    }
    return len;
}

void speaker_reset_stream(void)
{
    // Called on disconnect; a queued DMA block still finishes on its worker.
    current_length = 0;
    offset = 0;
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
    if (rx_buffer == NULL)
        return -EIO;
    const int samples_per_block = MAX_BLOCK_SIZE / (NUM_CHANNELS * sizeof(int16_t));
    generate_gentle_chime((int16_t *) rx_buffer, samples_per_block);
    return play_pcm_block(MAX_BLOCK_SIZE);
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
