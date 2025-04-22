/*
 * Copyright (c) 2023 Omi Inc.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#include <zephyr/kernel.h>
#include <zephyr/audio/dmic.h>
#include <zephyr/logging/log.h>
#include "lib/dk2/mic.h"

LOG_MODULE_REGISTER(mic, CONFIG_LOG_DEFAULT_LEVEL);

#define MAX_SAMPLE_RATE 16000
#define SAMPLE_BIT_WIDTH 16
#define BYTES_PER_SAMPLE sizeof(int16_t)

/* Milliseconds to wait for a block to be read. */
#define READ_TIMEOUT 1000

/* Size of a block for 100 ms of audio data. */
#define BLOCK_SIZE(sample_rate, number_of_channels) \
    (BYTES_PER_SAMPLE * (sample_rate / 10) * number_of_channels)

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

static void process_audio_buffer(void *buffer, uint32_t size)
{
    if (callback_func) {
        callback_func((int16_t *)buffer);
    }
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
K_THREAD_DEFINE(mic_thread_id, MIC_THREAD_STACK_SIZE, mic_thread_function,
                NULL, NULL, NULL, MIC_THREAD_PRIORITY, 0, -1);

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
    };

    struct dmic_cfg cfg = {
        .io = {
            /* These fields can be used to limit the PDM clock
             * configurations that the driver is allowed to use
             * to those supported by the microphone.
             */
            .min_pdm_clk_freq = 1000000,
            .max_pdm_clk_freq = 3500000,
            .min_pdm_clk_dc = 40,
            .max_pdm_clk_dc = 60,
        },
        .streams = &stream,
        .channel = {
            .req_num_streams = 1,
        },
    };

    /* Configure for mono audio */
    cfg.channel.req_num_chan = 1;
    cfg.channel.req_chan_map_lo = dmic_build_channel_map(0, 0, PDM_CHAN_LEFT);
    cfg.streams[0].pcm_rate = MAX_SAMPLE_RATE;
    cfg.streams[0].block_size = BLOCK_SIZE(cfg.streams[0].pcm_rate, cfg.channel.req_num_chan);

    LOG_INF("PCM output rate: %u, channels: %u",
            cfg.streams[0].pcm_rate, cfg.channel.req_num_chan);

    ret = dmic_configure(dmic_dev, &cfg);
    if (ret < 0) {
        LOG_ERR("Failed to configure the driver: %d", ret);
        return ret;
    }

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
