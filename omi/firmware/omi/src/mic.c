/*
 * Copyright (c) 2023 Omi Inc.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#include "lib/dk2/mic.h"

#include <nrfx_pdm.h>
#include <zephyr/audio/dmic.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

#include "lib/dk2/settings.h"

LOG_MODULE_REGISTER(mic, CONFIG_LOG_DEFAULT_LEVEL);

#define MAX_SAMPLE_RATE 16000
#define SAMPLE_BIT_WIDTH 16
#define BYTES_PER_SAMPLE sizeof(int16_t)
#define CHANNELS 2

/* Milliseconds to wait for a block to be read. */
#define READ_TIMEOUT 1000

/* Size of a block for 100 ms of audio data. */
#define BLOCK_SIZE(sample_rate, number_of_channels) (BYTES_PER_SAMPLE * (sample_rate / 10) * number_of_channels)

/* Driver will allocate blocks from this slab to receive audio data into them.
 * Application, after getting a given block from the driver and processing its
 * data, needs to free that block.
 */
#define MAX_BLOCK_SIZE BLOCK_SIZE(MAX_SAMPLE_RATE, 2)
#define BLOCK_COUNT 4

K_MEM_SLAB_DEFINE_STATIC(mem_slab, MAX_BLOCK_SIZE, BLOCK_COUNT, 4);

static const struct device *dmic_dev;
static volatile mix_handler callback_func = NULL;
static volatile bool mic_running = false;

static inline void
deinterleave_stereo(const int16_t *restrict interleaved, size_t frames, int16_t *restrict left, int16_t *restrict right)
{
    /* interleaved: L0, R0, L1, R1, ... */
    for (size_t i = 0, j = 0; i < frames; ++i, j += 2) {
        left[i] = interleaved[j + 0];
        right[i] = interleaved[j + 1];
    }
}

static inline void
mixdown_to_mono(const int16_t *restrict left, const int16_t *restrict right, size_t frames, int16_t *restrict mono_out)
{
    /* simple 0.5*(L+R) with saturation */
    for (size_t i = 0; i < frames; ++i) {
        int32_t s = (int32_t) left[i] + (int32_t) right[i];
        s >>= 1; /* divide by 2 to avoid clipping */
        if (s > 32767)
            s = 32767;
        if (s < -32768)
            s = -32768;
        mono_out[i] = (int16_t) s;
    }
}

static void process_audio_buffer(void *buffer, uint32_t size)
{
    /* size is total interleaved stereo size: frames * 2ch * 2bytes */
    __ASSERT_NO_MSG((size % (BYTES_PER_SAMPLE * CHANNELS)) == 0);
    size_t frames = size / (BYTES_PER_SAMPLE * CHANNELS);
    int16_t *inter = (int16_t *) buffer;

    /* Allocate contiguous L and R */
    int16_t *left = k_malloc(frames * BYTES_PER_SAMPLE);
    int16_t *right = k_malloc(frames * BYTES_PER_SAMPLE);

    if (!left || !right) {
        LOG_ERR("Out of memory for deinterleave (frames=%zu)", frames);
        if (left)
            k_free(left);
        if (right)
            k_free(right);
        /* Still free original slab block */
        k_mem_slab_free(&mem_slab, buffer);
        return;
    }

    deinterleave_stereo(inter, frames, left, right);

    /* Mix to mono and call mono callback */
    int16_t *mono = k_malloc(frames * BYTES_PER_SAMPLE);
    if (!mono) {
        LOG_ERR("Out of memory for mono mix (frames=%zu)", frames);
    } else {
        mixdown_to_mono(left, right, frames, mono);
        if (callback_func) {
            callback_func((int16_t *) mono);
        }
        k_free(mono);
    }

    /* Clean up */
    k_free(left);
    k_free(right);
    k_mem_slab_free(&mem_slab, buffer);
}

static void mic_thread_function(void *p1, void *p2, void *p3)
{
    ARG_UNUSED(p1);
    ARG_UNUSED(p2);
    ARG_UNUSED(p3);

    while (mic_running) {
        void *buffer;
        uint32_t size;

        int ret = dmic_read(dmic_dev, 0, &buffer, &size, READ_TIMEOUT);
        if (ret < 0) {
            LOG_ERR("Read failed: %d", ret);
            continue;
        }

        LOG_DBG("Got buffer %p of %u bytes", buffer, size);
        process_audio_buffer(buffer, size);
    }
}

#define MIC_THREAD_STACK_SIZE 2048
#define MIC_THREAD_PRIORITY 5
K_THREAD_DEFINE(mic_thread_id,
                MIC_THREAD_STACK_SIZE,
                mic_thread_function,
                NULL,
                NULL,
                NULL,
                MIC_THREAD_PRIORITY,
                0,
                -1);

int mic_start()
{
    int ret;

    dmic_dev = DEVICE_DT_GET(DT_ALIAS(dmic0));
    if (!device_is_ready(dmic_dev)) {
        LOG_ERR("%s is not ready", dmic_dev->name);
        return -ENODEV;
    }

    struct pcm_stream_cfg stream = {
        .pcm_width = SAMPLE_BIT_WIDTH,
        .mem_slab = &mem_slab,
        .pcm_rate = MAX_SAMPLE_RATE,
        .block_size = BLOCK_SIZE(MAX_SAMPLE_RATE, CHANNELS),
    };

    struct dmic_cfg cfg = {
        .io =
            {
                .min_pdm_clk_freq = 512000,
                .max_pdm_clk_freq = 3500000,
                .min_pdm_clk_dc = 48,
                .max_pdm_clk_dc = 52,
            },
        .streams = &stream,
        .channel =
            {
                .req_num_streams = 1,
                .req_num_chan = CHANNELS,
                .req_chan_map_lo =
                    dmic_build_channel_map(0, 0, PDM_CHAN_LEFT) | dmic_build_channel_map(1, 0, PDM_CHAN_RIGHT),
            },

    };

    LOG_INF("PCM output rate: %u, channels: %u", cfg.streams[0].pcm_rate, cfg.channel.req_num_chan);

    ret = dmic_configure(dmic_dev, &cfg);
    if (ret < 0) {
        LOG_ERR("Failed to configure the driver: %d", ret);
        return ret;
    }

    // Apply saved mic gain setting
    uint8_t saved_gain = app_settings_get_mic_gain();
    mic_set_gain(saved_gain);

    ret = dmic_trigger(dmic_dev, DMIC_TRIGGER_START);
    if (ret < 0) {
        LOG_ERR("START trigger failed: %d", ret);
        return ret;
    }

    mic_running = true;
    k_thread_start(mic_thread_id);

    LOG_INF("Microphone started");
    return 0;
}

void set_mic_callback(mix_handler callback)
{
    callback_func = callback;
}

void mic_off()
{
    if (mic_running) {
        mic_running = false;
        k_thread_abort(mic_thread_id);

        int ret = dmic_trigger(dmic_dev, DMIC_TRIGGER_STOP);
        if (ret < 0) {
            LOG_ERR("STOP trigger failed: %d", ret);
        }

        LOG_INF("Microphone stopped");
    }
}

void mic_on()
{
    if (!mic_running) {
        int ret = dmic_trigger(dmic_dev, DMIC_TRIGGER_START);
        if (ret < 0) {
            LOG_ERR("START trigger failed: %d", ret);
            return;
        }

        mic_running = true;
        k_thread_start(mic_thread_id);

        LOG_INF("Microphone restarted");
    }
}

void mic_set_gain(uint8_t gain_level)
{
    // Map gain level (0-8) to hardware values
    // Level 0: 0x00 = mute
    // Level 1: 0x14 = -20dB
    // Level 2: 0x1E = -10dB
    // Level 3: 0x28 = +0dB
    // Level 4: 0x2E = +6dB
    // Level 5: 0x32 = +10dB
    // Level 6: 0x3C = +20dB (default)
    // Level 7: 0x46 = +30dB
    // Level 8: 0x50 = +40dB (max)

    static const uint8_t gain_map[9] = {
        0x00, // Level 0: mute
        0x14, // Level 1: -20dB
        0x1E, // Level 2: -10dB
        0x28, // Level 3: +0dB
        0x2E, // Level 4: +6dB
        0x32, // Level 5: +10dB
        0x3C, // Level 6: +20dB
        0x46, // Level 7: +30dB
        0x50  // Level 8: +40dB
    };

    // Clamp to valid level range
    if (gain_level > 8) {
        gain_level = 8;
    }

    uint8_t hw_gain = gain_map[gain_level];

    LOG_INF("Setting mic gain to level %u (0x%02x)", gain_level, hw_gain);

#ifdef NRF_PDM0_S
    nrf_pdm_gain_set(NRF_PDM0_S, hw_gain, hw_gain);
#else
    nrf_pdm_gain_set(NRF_PDM0_NS, hw_gain, hw_gain);
#endif
}
