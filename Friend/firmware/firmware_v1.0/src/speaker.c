#include <zephyr/logging/log.h>
#include <zephyr/drivers/i2s.h>
#include <math.h>
#include "speaker.h"

#define SAMPLE_FREQUENCY 44100
#define SAMPLE_BIT_WIDTH 16
#define NUM_CHANNELS 2
#define SAMPLE_NO 64

#define PI 3.14159265358979323846

#define MAX_BLOCK_SIZE 25000
#define BLOCK_COUNT 1
#define PACKET_SIZE 400

LOG_MODULE_REGISTER(speaker, CONFIG_LOG_DEFAULT_LEVEL);

static const struct device *i2s_dev;
static void *rx_buffer;
static int16_t *ptr2;
static int16_t *clear_ptr;
static uint32_t current_length;
static uint32_t offset;

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
    i2s_cfg.timeout = 1000;

    ret = i2s_configure(i2s_dev, I2S_DIR_TX, &i2s_cfg);
    if (ret < 0) {
        LOG_ERR("Failed to configure I2S: %d", ret);
        return ret;
    }
    LOG_INF("I2S configured successfully");

    ret = k_mem_slab_alloc(&mem_slab, &rx_buffer, K_NO_WAIT);
    if (ret) {
        LOG_ERR("Failed to allocate memory (%d)", ret);
        return ret;
    }
    memset(rx_buffer, 0, MAX_BLOCK_SIZE);

    return 0;
}

int play_boot_sound(void)
{
    int ret;
    int16_t *buffer = (int16_t *)rx_buffer;
    int samples_per_block = MAX_BLOCK_SIZE / (NUM_CHANNELS * sizeof(int16_t));
    float frequency = 440.0f;

    for (int i = 0; i < samples_per_block; i++) {
        float t = (float)i / SAMPLE_FREQUENCY;
        float value = sinf(2 * PI * frequency * t);
        int16_t sample = (int16_t)(value * 32767);
        buffer[i * NUM_CHANNELS] = sample;
        buffer[i * NUM_CHANNELS + 1] = sample;
    }

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

    k_sleep(K_MSEC(1000));

    ret = i2s_trigger(i2s_dev, I2S_DIR_TX, I2S_TRIGGER_STOP);
    if (ret != 0) {
        LOG_ERR("Failed to stop I2S transmission: %d", ret);
        return ret;
    }

    return 0;
}
