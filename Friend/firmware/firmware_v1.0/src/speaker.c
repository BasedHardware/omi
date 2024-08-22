#include <zephyr/logging/log.h>
#include <zephyr/drivers/i2s.h>
#include <math.h>
#include "speaker.h"

#define SAMPLE_FREQUENCY 7500
#define SAMPLE_BIT_WIDTH 16
#define NUM_CHANNELS 2

#define PI 3.14159265358979323846

#define MAX_BLOCK_SIZE 25000
#define BLOCK_COUNT 3

LOG_MODULE_REGISTER(speaker, CONFIG_LOG_DEFAULT_LEVEL);

static const struct device *i2s_dev;
static void *audio_buffer;
static uint32_t buffer_offset;
static uint32_t total_length;

K_MEM_SLAB_DEFINE_STATIC(mem_slab, MAX_BLOCK_SIZE, BLOCK_COUNT, 4);

int speaker_init(void)
{
    struct i2s_config i2s_cfg;
    int ret;

    i2s_dev = DEVICE_DT_GET(DT_NODELABEL(i2s0));
    if (!device_is_ready(i2s_dev)) {
        LOG_ERR("I2S device not ready");
        return -ENODEV;
    }
    LOG_INF("I2S device is ready");

    i2s_cfg.word_size = SAMPLE_BIT_WIDTH;
    i2s_cfg.channels = NUM_CHANNELS;
    i2s_cfg.format = I2S_FMT_DATA_FORMAT_LEFT_JUSTIFIED;
    i2s_cfg.options = I2S_OPT_FRAME_CLK_MASTER | I2S_OPT_BIT_CLK_MASTER | I2S_OPT_BIT_CLK_GATED;
    i2s_cfg.frame_clk_freq = SAMPLE_FREQUENCY;
    i2s_cfg.block_size = MAX_BLOCK_SIZE;
    i2s_cfg.mem_slab = &mem_slab;
    i2s_cfg.timeout = 10000;

    ret = i2s_configure(i2s_dev, I2S_DIR_TX, &i2s_cfg);
    if (ret < 0) {
        LOG_ERR("Failed to configure I2S: %d", ret);
        return ret;
    }
    LOG_INF("I2S configured successfully");

    ret = k_mem_slab_alloc(&mem_slab, &audio_buffer, K_NO_WAIT);
    if (ret) {
        LOG_ERR("Failed to allocate memory (%d)", ret);
        return ret;
    }
    memset(audio_buffer, 0, MAX_BLOCK_SIZE);

    return 0;
}

static void generate_gentle_chime(int16_t *buffer, int num_samples)
{
    float frequencies[] = {523.25, 659.25, 783.99, 1046.50}; // C5, E5, G5, C6
    int num_freqs = sizeof(frequencies) / sizeof(frequencies[0]);

    for (int i = 0; i < num_samples; i++) {
        float t = (float)i / SAMPLE_FREQUENCY;
        float sample = 0;
        for (int j = 0; j < num_freqs; j++) {
            sample += sinf(2 * PI * frequencies[j] * t) * (1.0 - t);
        }
        int16_t int_sample = (int16_t)(sample / num_freqs * 32767 * 0.5);
        buffer[i * NUM_CHANNELS] = int_sample;
        buffer[i * NUM_CHANNELS + 1] = int_sample;
    }
}

int play_boot_sound(void)
{
    int ret;
    int16_t *buffer = (int16_t *)audio_buffer;
    int samples_per_block = MAX_BLOCK_SIZE / (NUM_CHANNELS * sizeof(int16_t));

    generate_gentle_chime(buffer, samples_per_block);

    ret = i2s_write(i2s_dev, buffer, MAX_BLOCK_SIZE);
    if (ret < 0) {
        LOG_ERR("Failed to write initial I2S data: %d", ret);
        return ret;
    }

    ret = i2s_trigger(i2s_dev, I2S_DIR_TX, I2S_TRIGGER_START);
    if (ret != 0) {
        LOG_ERR("Failed to start I2S transmission: %d", ret);
        return ret;
    }

    k_sleep(K_MSEC(2000));  // Increased from 1000 to 2000 ms

    ret = i2s_trigger(i2s_dev, I2S_DIR_TX, I2S_TRIGGER_STOP);
    if (ret != 0) {
        LOG_ERR("Failed to stop I2S transmission: %d", ret);
        return ret;
    }

    return 0;
}

static void generate_vibrate(int16_t *buffer, int num_samples)
{
    float frequency = 30.0; // Slightly higher frequency
    float period = SAMPLE_FREQUENCY / frequency;

    for (int i = 0; i < num_samples; i++) {
        float t = (float)i / SAMPLE_FREQUENCY;
        float phase = fmodf(t * frequency, 1.0f);
        float sample;

        if (phase < 0.5f) {
            sample = phase * 4.0f - 1.0f; // Triangle wave rising edge
        } else {
            sample = 3.0f - phase * 4.0f; // Triangle wave falling edge
        }

        int16_t int_sample = (int16_t)(sample * 32767 * 0.5); // Adjust amplitude
        buffer[i * NUM_CHANNELS] = int_sample;
        buffer[i * NUM_CHANNELS + 1] = int_sample;
    }
}

int vibrate_speaker(void)
{
    int ret;
    int16_t *buffer = (int16_t *)audio_buffer;
    int samples_per_block = MAX_BLOCK_SIZE / (NUM_CHANNELS * sizeof(int16_t));

    generate_vibrate(buffer, samples_per_block);

    ret = i2s_write(i2s_dev, buffer, MAX_BLOCK_SIZE);
    if (ret < 0) {
        LOG_ERR("Failed to write vibrate I2S data: %d", ret);
        return ret;
    }

    ret = i2s_trigger(i2s_dev, I2S_DIR_TX, I2S_TRIGGER_START);
    if (ret != 0) {
        LOG_ERR("Failed to start I2S transmission: %d", ret);
        return ret;
    }

    k_sleep(K_MSEC(500));  // Duration of the vibration (adjust as needed)

    ret = i2s_trigger(i2s_dev, I2S_DIR_TX, I2S_TRIGGER_STOP);
    if (ret != 0) {
        LOG_ERR("Failed to stop I2S transmission: %d", ret);
        return ret;
    }

    return 0;
}


int start_audio_playback(uint32_t length)
{
    if (length == 0 || length > MAX_BLOCK_SIZE) {
        LOG_ERR("Invalid audio length: %u", length);
        return -EINVAL;
    }

    total_length = length;
    buffer_offset = 0;
    memset(audio_buffer, 0, MAX_BLOCK_SIZE);

    LOG_INF("Starting audio playback, total length: %u bytes", total_length);
    return 0;
}

int write_audio_data(const void *data, uint16_t length)
{
    if (buffer_offset + length > total_length) {
        LOG_ERR("Attempting to write more data than expected");
        return -EINVAL;
    }

    memcpy((uint8_t *)audio_buffer + buffer_offset, data, length);
    buffer_offset += length;

    if (buffer_offset == total_length) {
        LOG_INF("Audio data complete, starting playback");
        int ret = i2s_write(i2s_dev, audio_buffer, total_length);
        if (ret < 0) {
            LOG_ERR("Failed to write I2S data: %d", ret);
            return ret;
        }

        ret = i2s_trigger(i2s_dev, I2S_DIR_TX, I2S_TRIGGER_START);
        if (ret != 0) {
            LOG_ERR("Failed to start I2S transmission: %d", ret);
            return ret;
        }

        k_sleep(K_MSEC(2000));  // Adjust this based on your audio length

        ret = i2s_trigger(i2s_dev, I2S_DIR_TX, I2S_TRIGGER_STOP);
        if (ret != 0) {
            LOG_ERR("Failed to stop I2S transmission: %d", ret);
            return ret;
        }

        // Reset for next playback
        buffer_offset = 0;
        total_length = 0;
    }

    return length;
}
