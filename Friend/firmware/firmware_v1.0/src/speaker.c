#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>
#include <zephyr/device.h>
#include <zephyr/drivers/i2s.h>
#include <zephyr/drivers/gpio.h>
#include <math.h>
#include <zephyr/logging/log.h>
#include <zephyr/logging/log_ctrl.h>
#include "speaker.h"

LOG_MODULE_REGISTER(speaker, CONFIG_LOG_DEFAULT_LEVEL);

#define MAX_BLOCK_SIZE   20000
#define BLOCK_COUNT 2     
#define SAMPLE_FREQUENCY 8000
#define PACKET_SIZE 400
#define WORD_SIZE 16
#define NUM_CHANNELS 2

#define PI 3.14159265358979323846
#define MAX_HAPTIC_DURATION 5000

#define AUDIO_END_FLAG 0x01
#define AUDIO_START_FLAG 0x02

// Define the audio buffer and related variables
static uint8_t audio_buffer[MAX_BLOCK_SIZE];
static size_t buffer_offset = 0;   // Tracks the end of valid data in the buffer
static size_t played_offset = 0;   // Tracks the amount of data already played
static const struct device *audio_speaker;

static int16_t buffer1[PACKET_SIZE / 2];
static int16_t buffer2[PACKET_SIZE / 2];
static int16_t *active_buffer = buffer1;
static int16_t *fill_buffer = buffer2;
static bool buffer_ready = false;

K_MEM_SLAB_DEFINE_STATIC(mem_slab, MAX_BLOCK_SIZE, BLOCK_COUNT, 2);

const static struct device *audio_speaker;
static void* rx_buffer;
static void* buzz_buffer;
static int16_t *ptr2;
static int16_t *clear_ptr;

static uint16_t current_length;
static uint16_t offset;

struct gpio_dt_spec haptic_gpio_pin = {.port = DEVICE_DT_GET(DT_NODELABEL(gpio1)), .pin=11, .dt_flags = GPIO_INT_DISABLE};

void clear_audio_buffer() {
    buffer_offset = 0;
    memset(audio_buffer, 0, sizeof(audio_buffer));
}

void prune_audio_buffer(size_t required_space) {
    // Calculate the minimum data needed to discard
    size_t data_to_discard = required_space + buffer_offset - MAX_BLOCK_SIZE;

    if (data_to_discard >= buffer_offset) {
        // Clear the entire buffer if required space is more than available data
        clear_audio_buffer();
    } else {
        // Shift remaining data to make exactly the required space
        memmove(audio_buffer, audio_buffer + data_to_discard, buffer_offset - data_to_discard);
        buffer_offset -= data_to_discard;
        printk("Pruned %zu bytes from the audio buffer\n", data_to_discard);
    }
}

uint16_t speak(uint16_t len, const void *buf) {
    printk("speaker.c - speak invoked\n");

    // Extract the flags from the last two bytes of the packet
    const uint8_t *data = (const uint8_t *)buf;
    uint8_t is_first_packet = data[len - 2] == AUDIO_START_FLAG;
    uint8_t is_last_packet = data[len - 1] == AUDIO_END_FLAG;
    size_t audio_data_length = len - 2;  // Exclude the last two bytes (flags)

    // Clear buffer if it's the first packet
    if (is_first_packet) {
        printk("Received first packet, clearing audio buffer\n");
        clear_audio_buffer();
    }

    // Check and handle buffer overflow by pruning old data if needed
    if (buffer_offset + audio_data_length * 2 > MAX_BLOCK_SIZE) {
        printk("Buffer overflow: too much audio data. Pruning old data...\n");
        prune_audio_buffer(audio_data_length * 2);
    }

    // Ensure we have enough space after pruning
    if (buffer_offset + audio_data_length * 2 > MAX_BLOCK_SIZE) {
        printk("Still not enough space in buffer after pruning\n");
        return 0;  // Exit if there's still insufficient space
    }

    const int16_t *input_data = (const int16_t *)data;
    int16_t *output_data = (int16_t *)&audio_buffer[buffer_offset];

    // Copy and duplicate samples for stereo playback
    for (size_t i = 0; i < audio_data_length / 2; i++) {
        int16_t sample = input_data[i];
        *output_data++ = sample;  // Left channel
        *output_data++ = sample;  // Right channel
    }

    buffer_offset += audio_data_length * 2;

    printk("Received packet of length: %u, total buffered: %u\n", audio_data_length, buffer_offset);

    int ret = i2s_buf_write(audio_speaker, audio_buffer, buffer_offset);
    if (ret < 0) {
        printk("Failed to write to I2S: %d\n", ret);
        return 0;
    }

    ret = i2s_trigger(audio_speaker, I2S_DIR_TX, I2S_TRIGGER_START);
    if (ret) {
        LOG_ERR("Failed to start I2S transmission: %d", ret);
        return ret;
    }

    // Reset buffer after playback if it's the last packet
    if (is_last_packet) {
        buffer_offset = 0;
    }

    return len;
}

int speaker_init() 
{
    LOG_INF("Speaker init");
    audio_speaker = device_get_binding("I2S_0");
    
    if (!device_is_ready(audio_speaker)) 
    {
        LOG_ERR("Speaker device is not supported : %s", audio_speaker->name);
        return -1;
    }
    struct i2s_config config = {
    .word_size= WORD_SIZE, //how long is one left/right word.
    .channels = NUMBER_OF_CHANNELS, //how many words in a frame 2 
    .format = I2S_FMT_DATA_FORMAT_LEFT_JUSTIFIED, //format
    // .format = I2S_FMT_DATA_FORMAT_I2S,
    .options = I2S_OPT_FRAME_CLK_MASTER | I2S_OPT_BIT_CLK_MASTER | I2S_OPT_BIT_CLK_GATED, //how to configure the mclock
    .frame_clk_freq = SAMPLE_FREQUENCY, /* Sampling rate */ 
    .mem_slab = &mem_slab,/* Memory slab to store rx/tx data */
    .block_size = MAX_BLOCK_SIZE,/* size of ONE memory block in bytes */
    .timeout = -1, /* Number of milliseconds to wait in case Tx queue is full or RX queue is empty, or 0, or SYS_FOREVER_MS */
    };
    int err = i2s_configure(audio_speaker, I2S_DIR_TX, &config);
    if (err) 
    {
        LOG_ERR("Failed to configure Speaker (%d)", err);
        return -1;
    }
    err = k_mem_slab_alloc(&mem_slab, &rx_buffer, K_MSEC(200));
	if (err)
    {
		LOG_INF("Failed to allocate memory for speaker%d)", err);
        return -1;
	}

	err = k_mem_slab_alloc(&mem_slab, &buzz_buffer, K_MSEC(200));
	if (err) 
    {
		LOG_INF("Failed to allocate for chime (%d)", err);
        return -1;
	}
      
    memset(rx_buffer, 0, MAX_BLOCK_SIZE);
    memset(buzz_buffer, 0, MAX_BLOCK_SIZE);
    return 0;
}

void switch_buffers() {
    if (active_buffer == buffer1) {
        active_buffer = buffer2;
        fill_buffer = buffer1;
    } else {
        active_buffer = buffer1;
        fill_buffer = buffer2;
    }
    buffer_ready = true;
}

// Function to remove played audio from the buffer
void remove_played_audio(size_t bytes_played) {
    if (bytes_played >= buffer_offset) {
        buffer_offset = 0;  // All data played, clear buffer
    } else {
        memmove(audio_buffer, audio_buffer + bytes_played, buffer_offset - bytes_played);
        buffer_offset -= bytes_played;
    }
}

void generate_gentle_chime(int16_t *buffer, int num_samples)
{
    LOG_INF("Generating gentle chime");//2500
    const float frequencies[] = {523.25, 659.25, 783.99, 1046.50}; // C5, E5, G5, C6
    const int num_freqs = sizeof(frequencies) / sizeof(frequencies[0]);//4

    for (int i = 0; i < num_samples; i++) 
    { 
        float t = (float)i / SAMPLE_FREQUENCY;//0.000125
        float sample = 0;
        for (int j = 0; j < num_freqs; j++) 
        {
           sample += sinf(2 * PI * frequencies[j] * t) * (1.0 - t);
        }
        int16_t int_sample = (int16_t)(sample / num_freqs * 32767 * 0.5);
        buffer[i * NUM_CHANNELS] = int_sample;
        buffer[i * NUM_CHANNELS + 1] = int_sample;
    }
    LOG_INF("Done generating gentle chime");
}

int play_boot_sound(void)
{
    int ret;
    int16_t *buffer = (int16_t *) buzz_buffer;
    const int samples_per_block = MAX_BLOCK_SIZE / (NUM_CHANNELS * sizeof(int16_t));

    generate_gentle_chime(buffer, samples_per_block);
    LOG_INF("Writing to speaker");
    k_sleep(K_MSEC(100));
    ret = i2s_write(audio_speaker, buffer, MAX_BLOCK_SIZE);
    if (ret) 
    {
        LOG_ERR("Failed to write initial I2S data: %d", ret);
        return ret;
    }

    ret = i2s_trigger(audio_speaker, I2S_DIR_TX, I2S_TRIGGER_START);
    if (ret) 
    {
        LOG_ERR("Failed to start I2S transmission: %d", ret);
        return ret;
    }  


    ret = i2s_trigger(audio_speaker, I2S_DIR_TX, I2S_TRIGGER_DRAIN);
    if (ret != 0) 
    {
        LOG_ERR("Failed to drain I2S transmission: %d", ret);
        return ret;
    }
    k_sleep(K_MSEC(3000));  

    return 0;
}

int init_haptic_pin() 
{
    if (gpio_is_ready_dt(&haptic_gpio_pin)) 
    {
		LOG_INF("Haptic Pin ready");
	}
    else 
    {
		LOG_ERR("Error setting up Haptic Pin");
        return -1;
	}
	if (gpio_pin_configure_dt(&haptic_gpio_pin, GPIO_OUTPUT_INACTIVE) < 0) 
    {
		LOG_ERR("Error setting up Haptic Pin");
        return -1;
	}
    gpio_pin_set_dt(&haptic_gpio_pin, 0);

    return 0;
}

void haptic_timer_callback(struct k_timer *timer);

K_TIMER_DEFINE(my_status_timer, haptic_timer_callback, NULL);

void haptic_timer_callback(struct k_timer *timer)
{
    gpio_pin_set_dt(&haptic_gpio_pin, 0);
}

void play_haptic_milli(uint32_t duration)
{
    if (duration > MAX_HAPTIC_DURATION)
    {
        LOG_ERR("Duration is too long");
        return;
    }
    gpio_pin_set_dt(&haptic_gpio_pin, 1);
    k_timer_start(&my_status_timer, K_MSEC(duration), K_NO_WAIT);
}
