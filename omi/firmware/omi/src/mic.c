/*
 * Copyright (c) 2023 Omi Inc.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#include "lib/core/mic.h"

#include <nrfx_pdm.h>
#include <zephyr/audio/dmic.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/atomic.h>

#include "lib/core/settings.h"

#ifdef CONFIG_OMI_ENABLE_T5838_AAD
#include <zephyr/devicetree.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/sys/atomic.h>

#include "sd_card.h"
#include "storage.h"
#include "t5838_aad.h"
#include "transport.h"
#endif

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

/* Cooperative pause: mic_pause() asks the mic thread to stop cleanly between
 * reads and waits for it, so a dmic_read is never cut short (which would make
 * both this module and the nrfx PDM driver log a spurious error). */
static K_SEM_DEFINE(mic_stopped_sem, 0, 1);
static atomic_t mic_stop_req = ATOMIC_INIT(0);

#define MAX_FRAMES (MAX_SAMPLE_RATE / 10)
static int16_t mono_buffer[MAX_FRAMES];

#ifdef CONFIG_OMI_ENABLE_T5838_AAD
/*
 * Hardware AAD (T5838): during silence the mic is clocked into AAD sleep
 * (PDM off, ~20uA) and its WAKE pin (P1.02, active-HIGH) resumes it on sound.
 * Owned here since it shares the PDM peripheral and CLK pin.
 */
extern bool is_connected; /* from main.c: keep SD up while a phone can sync */

static const struct gpio_dt_spec aad_wake = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(pdm_wake_pin), gpios, {0});
static struct gpio_callback aad_wake_cb;

#define AAD_THREAD_STACK_SIZE 1024
#define AAD_THREAD_PRIORITY 5
static K_THREAD_STACK_DEFINE(aad_stack, AAD_THREAD_STACK_SIZE);
static struct k_thread aad_thread_data;
static bool aad_thread_started; /* aad_thread_data is a live thread */
static K_SEM_DEFINE(aad_sem, 0, 1);
#define AAD_PDM_SETTLE_MS 20

static atomic_t aad_wake_pending = ATOMIC_INIT(0); /* WAKE edge seen by ISR */
static atomic_t aad_woke = ATOMIC_INIT(0);         /* tell mic ctx it just woke */
static atomic_t aad_in_sleep = ATOMIC_INIT(0);     /* mic is in hardware AAD sleep */
static atomic_t aad_req_sleep = ATOMIC_INIT(0);    /* silence timer asked to sleep */
static int64_t aad_last_voice_ms;

static void aad_track_silence(const int16_t *buf, size_t n);
static int aad_hw_start(void);
#endif

static inline void
interleaved_stereo_to_mono(const int16_t *restrict interleaved, size_t frames, int16_t *restrict mono_out)
{
    /* Mix L and R channels directly from interleaved format: L0, R0, L1, R1, ... */
    for (size_t i = 0, j = 0; i < frames; ++i, j += 2) {
        int32_t left = (int32_t) interleaved[j + 0];
        int32_t right = (int32_t) interleaved[j + 1];
        int32_t sum = left + right;
        sum >>= 1; /* divide by 2 to avoid clipping */
        if (sum > 32767)
            sum = 32767;
        if (sum < -32768)
            sum = -32768;
        mono_out[i] = (int16_t) sum;
    }
}

static void process_audio_buffer(void *buffer, uint32_t size)
{
    /* size is total interleaved stereo size: frames * 2ch * 2bytes */
    __ASSERT_NO_MSG((size % (BYTES_PER_SAMPLE * CHANNELS)) == 0);
    size_t frames = size / (BYTES_PER_SAMPLE * CHANNELS);
    int16_t *inter = (int16_t *) buffer;

    /* Verify we don't exceed static buffer size */
    if (frames > MAX_FRAMES) {
        LOG_ERR("Frame count %zu exceeds MAX_FRAMES %d", frames, MAX_FRAMES);
        k_mem_slab_free(&mem_slab, buffer);
        return;
    }

    interleaved_stereo_to_mono(inter, frames, mono_buffer);

#ifdef CONFIG_OMI_ENABLE_T5838_AAD
    aad_track_silence(mono_buffer, frames);
#endif

    if (callback_func) {
        callback_func(mono_buffer);
    }

    k_mem_slab_free(&mem_slab, buffer);
}

static void mic_thread_function(void *p1, void *p2, void *p3)
{
    ARG_UNUSED(p1);
    ARG_UNUSED(p2);
    ARG_UNUSED(p3);

    while (true) {
        if (!mic_running) {
            k_sleep(K_MSEC(100));
            continue;
        }

        void *buffer = NULL;
        uint32_t size = 0;
        int ret = dmic_read(dmic_dev, 0, &buffer, &size, READ_TIMEOUT);

        /* Cooperative pause: honour a stop request here, between reads, so the
         * STOP never interrupts an in-flight dmic_read. */
        if (atomic_get(&mic_stop_req)) {
            if (ret == 0 && buffer) {
                k_mem_slab_free(&mem_slab, buffer);
            }
            (void) dmic_trigger(dmic_dev, DMIC_TRIGGER_STOP);
            mic_running = false;
            atomic_clear(&mic_stop_req);
            k_sem_give(&mic_stopped_sem);
            continue;
        }

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

#ifdef CONFIG_OMI_ENABLE_T5838_AAD
    /* Power the mic 1.8V rail (and level-shifter VCCA) before starting the PDM. */
    ret = t5838_aad_init();
    if (ret) {
        LOG_ERR("t5838 AAD init failed (%d): mic rail may be unpowered", ret);
    }
#endif

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

#ifdef CONFIG_OMI_ENABLE_T5838_AAD
    ret = aad_hw_start(); /* WAKE pin ISR + hardware-AAD thread */
    if (ret) {
        /* Non-fatal: the mic still records, it just won't power-save via AAD.
         * Log loudly so a broken AAD (device never sleeps) is diagnosable. */
        LOG_ERR("AAD start failed (%d): mic runs without hardware sleep", ret);
    }
#endif

    LOG_INF("Microphone started");
    return 0;
}

void set_mic_callback(mix_handler callback)
{
    callback_func = callback;
}

void mic_pause()
{
    if (!mic_running) {
        return;
    }
    LOG_INF("Pausing microphone");

    /* Request a clean stop and wait for the mic thread to finish its current
     * read, so no dmic_read is interrupted (avoids spurious -EAGAIN errors). */
    k_sem_reset(&mic_stopped_sem);
    atomic_set(&mic_stop_req, 1);
    if (k_sem_take(&mic_stopped_sem, K_MSEC(READ_TIMEOUT + 200)) != 0) {
        LOG_WRN("mic pause timed out; forcing stop");
        atomic_clear(&mic_stop_req);
        (void) dmic_trigger(dmic_dev, DMIC_TRIGGER_STOP);
        mic_running = false;
    }
}

void mic_resume()
{
    LOG_INF("Resuming microphone");
    if (!mic_running) {
        int ret = dmic_trigger(dmic_dev, DMIC_TRIGGER_START);
        if (ret < 0) {
            LOG_ERR("START trigger failed: %d", ret);
            return;
        }
        mic_running = true;
    }
}

bool mic_is_running()
{
    return mic_running;
}

bool mic_in_aad_sleep(void)
{
#ifdef CONFIG_OMI_ENABLE_T5838_AAD
    return atomic_get(&aad_in_sleep) != 0;
#else
    return false;
#endif
}

#ifdef CONFIG_OMI_ENABLE_T5838_AAD

/* Force-disable the PDM hardware so the CLK/DIN pins revert to GPIO control.
 * dmic STOP alone does not reliably release the CLK pin for FAKE2C bit-banging. */
static void pdm_hw_disable(void)
{
#ifdef NRF_PDM0_S
    nrf_pdm_disable(NRF_PDM0_S);
#else
    nrf_pdm_disable(NRF_PDM0_NS);
#endif
}

static uint32_t avg_abs_amplitude(const int16_t *buf, size_t n)
{
    if (n == 0) {
        return 0;
    }
    uint64_t sum = 0;
    for (size_t i = 0; i < n; i++) {
        int32_t s = buf[i];
        sum += (uint32_t) (s < 0 ? -s : s);
    }
    return (uint32_t) (sum / n);
}

static void aad_wake_irq(bool enable)
{
    gpio_pin_interrupt_configure_dt(&aad_wake, enable ? GPIO_INT_EDGE_RISING : GPIO_INT_DISABLE);
}

static void aad_wake_isr(const struct device *dev, struct gpio_callback *cb, uint32_t pins)
{
    ARG_UNUSED(dev);
    ARG_UNUSED(cb);
    ARG_UNUSED(pins);
    atomic_set(&aad_wake_pending, 1);
    k_sem_give(&aad_sem);
}

/* Drop the mic into T5838 hardware AAD sleep (aad thread context). */
static void enter_hw_aad(void)
{
    aad_wake_irq(false); /* mask WAKE during config bit-bang */
    mic_pause();         /* stop PDM peripheral */
    k_msleep(AAD_PDM_SETTLE_MS);
    pdm_hw_disable();                   /* fully release the CLK pin for bit-banging */
    t5838_aad_enter();                  /* program AAD mode-A + clock into sleep */
    k_msleep(CONFIG_OMI_AAD_SETTLE_MS); /* settle noise floor; swallow entry transient */

    /* BLE keeps advertising during sleep so a phone can connect at any time.
     * Connection parameters are left as negotiated -- forcing slow interval +
     * slave latency here was causing dropped BLE connections. */
    /* Keep the SD powered while a phone is connected so it can sync recordings at
     * any time; only cut SD power when offline + idle. */
    if (!is_connected) {
        sd_request_power(false);
    }

    atomic_set(&aad_in_sleep, 1);

    atomic_clear(&aad_wake_pending);
    aad_wake_irq(true); /* arm: only real acoustic activity wakes now */

    /* If WAKE is already HIGH at arm time (sound during entry) the edge would be
     * missed -> wake immediately instead of freezing. */
    if (gpio_pin_get_dt(&aad_wake)) {
        atomic_set(&aad_wake_pending, 1);
        k_sem_give(&aad_sem);
    }
    LOG_INF("AAD: hardware sleep (mic off)");
}

/* Bring the mic back online (aad thread context). */
static void exit_hw_aad(void)
{
    aad_wake_irq(false);
    t5838_aad_release_clk(); /* hand CLK back to the PDM peripheral */
    atomic_set(&aad_in_sleep, 0);
    atomic_set(&aad_woke, 1); /* reset silence timer in mic ctx */
    sd_request_power(true);   /* power on + remount SD before audio starts flowing */
    mic_resume();             /* dmic START reclaims CLK via pinctrl */
    LOG_INF("AAD: WAKE -> mic resumed");
}

static void aad_thread_fn(void *p1, void *p2, void *p3)
{
    ARG_UNUSED(p1);
    ARG_UNUSED(p2);
    ARG_UNUSED(p3);

    while (1) {
        /* Block until signalled: both transitions give aad_sem (silence timer ->
         * sleep request, WAKE ISR -> wake). No periodic poll needed, so the thread
         * stays asleep and adds no idle CPU wakeups. */
        k_sem_take(&aad_sem, K_FOREVER);

        if (atomic_cas(&aad_req_sleep, 1, 0) && !atomic_get(&aad_in_sleep)) {
            enter_hw_aad();
        }

        if (atomic_cas(&aad_wake_pending, 1, 0)) {
            if (atomic_get(&aad_in_sleep)) {
                exit_hw_aad();
            }
        }
    }
}

/* Called per mic frame: track silence and request AAD sleep after a hold. */
static void aad_track_silence(const int16_t *buf, size_t n)
{
    int64_t now = k_uptime_get();

    if (atomic_cas(&aad_woke, 1, 0)) {
        aad_last_voice_ms = now;
    }
    if (avg_abs_amplitude(buf, n) >= CONFIG_OMI_VAD_ABS_THRESHOLD) {
        aad_last_voice_ms = now;
    }
    /* Sleep after a long silence whether online or offline. When connected, the
     * BLE link stays up (only the mic + PDM sleep); sound resumes streaming.
     * BUT never sleep while a BLE sync transfer is running: the AAD entry +
     * conn-param low-power would stall the sync. Defer sleep until it finishes. */
    if (!atomic_get(&aad_in_sleep) && !storage_transfer_active() &&
        (now - aad_last_voice_ms) >= CONFIG_OMI_VAD_HOLD_MS) {
        atomic_set(&aad_req_sleep, 1);
        k_sem_give(&aad_sem);
    }
}

static int aad_hw_start(void)
{
    /* t5838_aad_init() already ran in mic_start() (to power the rail before the
     * PDM was configured); don't re-init here. */
    int ret;
    if (!gpio_is_ready_dt(&aad_wake)) {
        LOG_ERR("AAD: WAKE gpio not ready");
        return -ENODEV;
    }
    ret = gpio_pin_configure_dt(&aad_wake, GPIO_INPUT | GPIO_PULL_DOWN);
    if (ret) {
        LOG_ERR("AAD: WAKE pin config failed (%d)", ret);
        return ret;
    }
    gpio_init_callback(&aad_wake_cb, aad_wake_isr, BIT(aad_wake.pin));
    ret = gpio_add_callback(aad_wake.port, &aad_wake_cb);
    if (ret) {
        LOG_ERR("AAD: WAKE callback failed (%d)", ret);
        return ret;
    }
    (void) gpio_pin_interrupt_configure_dt(&aad_wake, GPIO_INT_DISABLE); /* armed on first sleep */

    aad_last_voice_ms = k_uptime_get();
    k_thread_create(&aad_thread_data,
                    aad_stack,
                    K_THREAD_STACK_SIZEOF(aad_stack),
                    aad_thread_fn,
                    NULL,
                    NULL,
                    NULL,
                    AAD_THREAD_PRIORITY,
                    0,
                    K_NO_WAIT);
    k_thread_name_set(&aad_thread_data, "aad");
    aad_thread_started = true;
    LOG_INF("AAD (hardware) started: WAKE=P1.%d thr=%d hold=%dms settle=%dms",
            aad_wake.pin,
            CONFIG_OMI_VAD_ABS_THRESHOLD,
            CONFIG_OMI_VAD_HOLD_MS,
            CONFIG_OMI_AAD_SETTLE_MS);
    return 0;
}

#endif /* CONFIG_OMI_ENABLE_T5838_AAD */

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

#ifdef CONFIG_OMI_ENABLE_T5838_AAD
    /* Stop the AAD worker first so it can't run a sleep/wake transition (re-driving
     * pins or the rail) after we cut power. Mask WAKE, then drop PDM_EN so the
     * T5838 + TXS0104 level-shifter lose power (otherwise the shifter's pull-ups
     * keep leaking ~1 mA through system-off). mic_off is the power-down path. */
    aad_wake_irq(false);
    if (aad_thread_started) {
        k_thread_abort(&aad_thread_data);
        aad_thread_started = false;
    }
    t5838_aad_power(false);
#endif
}

void mic_on()
{
    if (!mic_running) {
#ifdef CONFIG_OMI_ENABLE_T5838_AAD
        /* Restore the mic/level-shifter rail in case a prior mic_off() cut it,
         * so capture works again after an off/on cycle. */
        t5838_aad_power(true);
        k_msleep(AAD_PDM_SETTLE_MS);
#endif
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
    static const uint8_t gain_map[9] = {
        0x00, // Level 0: mute
        0x14, // Level 1: -20dB
        0x1E, // Level 2: -10dB
        0x28, // Level 3: +0dB
        0x2E, // Level 4: +6dB
        0x32, // Level 5: +10dB
        0x3C, // Level 6: +20dB (default)
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
