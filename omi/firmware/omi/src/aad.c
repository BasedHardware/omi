/*
 * AAD + VAD gate for Omi
 *
 * Owns voice-activity detection (VAD) state.  main.c calls
 * aad_process_audio() from the mic callback to decide whether
 * a frame should be forwarded to the codec or discarded.
 *
 * During VAD silence the SD card may be suspended to save power.
 * A dedicated thread manages SD lifecycle and auto-resumes on
 * BLE connect.  The T5838 WAKE pin (P1.2) is monitored via GPIO
 * ISR to reset VAD debounce on acoustic activity.
 */

#include "aad.h"

#include <string.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/atomic.h>

#include "lib/core/codec.h"
#include "lib/core/config.h"

LOG_MODULE_REGISTER(aad, CONFIG_LOG_DEFAULT_LEVEL);

/* ---- DTS GPIO spec for WAKE pin ---- */
static const struct gpio_dt_spec pin_wake = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(pdm_wake_pin), gpios, {0});
static struct gpio_callback wake_cb_data;

/* ---- Thread plumbing ---- */
#define AAD_THREAD_STACK_SIZE 1024
#define AAD_THREAD_PRIORITY 5

static K_THREAD_STACK_DEFINE(aad_stack, AAD_THREAD_STACK_SIZE);
static struct k_thread aad_thread_data;
static k_tid_t aad_tid;

static K_SEM_DEFINE(aad_sem, 0, 1);

/* ---- Atomic flags (ISR / cross-thread safe) ---- */
static atomic_t wake_pending = ATOMIC_INIT(0);
static atomic_t wake_consumed = ATOMIC_INIT(0);


/* ---- VAD state (mic callback context only) ---- */
static bool vad_is_recording = false;
static bool vad_sleeping = false;
static uint16_t vad_voice_streak = 0;
static int64_t vad_last_voice_ms = 0;
static int64_t vad_next_status_ms = 0;

/* ---- Pre-roll ring buffer ---- */
/* 8 frames * 100 ms/frame ~= 0.8 s pre-roll. */
#define VAD_PREROLL_FRAMES 8
/* Replay/backlog depth (also 0.8 s). With paced one-frame callbacks,
 * this avoids dropping transition speech while staying within RAM budget. */
#define VAD_PREROLL_FLUSH_MAX_FRAMES 8
static int16_t vad_preroll_buf[VAD_PREROLL_FRAMES][MIC_BUFFER_SAMPLES];
static uint8_t vad_preroll_wr = 0;
static uint8_t vad_preroll_cnt = 0;
static uint8_t vad_preroll_flush_rd = 0;
static uint8_t vad_preroll_flush_pending = 0;
static int16_t vad_live_backlog_buf[VAD_PREROLL_FLUSH_MAX_FRAMES][MIC_BUFFER_SAMPLES];
static uint8_t vad_live_backlog_rd = 0;
static uint8_t vad_live_backlog_wr = 0;
static uint8_t vad_live_backlog_cnt = 0;

#define VAD_STATUS_LOG_INTERVAL_MS 2000

/* ---- Helpers ---- */

static void preroll_reset(void)
{
    vad_preroll_wr = 0;
    vad_preroll_cnt = 0;
    vad_preroll_flush_rd = 0;
    vad_preroll_flush_pending = 0;
    vad_live_backlog_rd = 0;
    vad_live_backlog_wr = 0;
    vad_live_backlog_cnt = 0;
}

static bool live_backlog_push(const int16_t *buf)
{
    if (vad_live_backlog_cnt >= VAD_PREROLL_FLUSH_MAX_FRAMES) {
        LOG_ERR("VAD: live backlog overflow (cnt=%u)", vad_live_backlog_cnt);
        return false;
    }

    memcpy(vad_live_backlog_buf[vad_live_backlog_wr], buf, sizeof(vad_live_backlog_buf[0]));
    vad_live_backlog_wr = (vad_live_backlog_wr + 1) % VAD_PREROLL_FLUSH_MAX_FRAMES;
    vad_live_backlog_cnt++;
    return true;
}

static void live_backlog_flush_one(void)
{
    if (vad_live_backlog_cnt == 0) {
        return;
    }

    int err = codec_receive_pcm(vad_live_backlog_buf[vad_live_backlog_rd], MIC_BUFFER_SAMPLES);
    if (err) {
        LOG_ERR("VAD: live backlog flush failed (pending=%u): %d", vad_live_backlog_cnt, err);
        return;
    }

    vad_live_backlog_rd = (vad_live_backlog_rd + 1) % VAD_PREROLL_FLUSH_MAX_FRAMES;
    vad_live_backlog_cnt--;
}

static void preroll_store(const int16_t *buf)
{
    memcpy(vad_preroll_buf[vad_preroll_wr], buf, sizeof(vad_preroll_buf[0]));
    vad_preroll_wr = (vad_preroll_wr + 1) % VAD_PREROLL_FRAMES;
    if (vad_preroll_cnt < VAD_PREROLL_FRAMES) {
        vad_preroll_cnt++;
    }
}

static void preroll_queue_flush(void)
{
    if (vad_preroll_cnt == 0) {
        return;
    }
    uint8_t frames_to_flush = vad_preroll_cnt;
    if (frames_to_flush > VAD_PREROLL_FLUSH_MAX_FRAMES) {
        frames_to_flush = VAD_PREROLL_FLUSH_MAX_FRAMES;
    }

    /* Keep the most recent buffered audio when truncating flush burst. */
    vad_preroll_flush_rd = (vad_preroll_wr + VAD_PREROLL_FRAMES - frames_to_flush) % VAD_PREROLL_FRAMES;
    vad_preroll_flush_pending = frames_to_flush;

    uint8_t dropped = (vad_preroll_cnt > frames_to_flush) ? (vad_preroll_cnt - frames_to_flush) : 0;
    LOG_INF("VAD: queued %u/%u pre-roll frame(s), dropped %u", frames_to_flush, vad_preroll_cnt, dropped);

    /* Reset capture ring state; queued frames remain accessible via
     * vad_preroll_flush_rd + vad_preroll_flush_pending. */
    vad_preroll_wr = 0;
    vad_preroll_cnt = 0;
}

static void preroll_push_one(void)
{
    if (vad_preroll_flush_pending == 0) {
        return;
    }

    uint8_t idx = vad_preroll_flush_rd;
    int err = codec_receive_pcm(vad_preroll_buf[idx], MIC_BUFFER_SAMPLES);
    if (err) {
        LOG_ERR("Preroll push failed (pending=%u): %d", vad_preroll_flush_pending, err);
        vad_preroll_flush_pending = 0;
        return;
    }

    vad_preroll_flush_rd = (vad_preroll_flush_rd + 1) % VAD_PREROLL_FRAMES;
    vad_preroll_flush_pending--;

    if (vad_preroll_flush_pending == 0) {
        LOG_INF("VAD: pre-roll flush complete");
    }
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

/* ---- WAKE pin ISR ---- */

static void wake_pin_isr(const struct device *dev, struct gpio_callback *cb, uint32_t pins)
{
    ARG_UNUSED(dev);
    ARG_UNUSED(cb);
    ARG_UNUSED(pins);

    atomic_set(&wake_pending, 1);
    k_sem_give(&aad_sem);
}

/* ---- Handler thread (SD suspend / resume) ---- */

static void aad_thread_fn(void *p1, void *p2, void *p3)
{
    ARG_UNUSED(p1);
    ARG_UNUSED(p2);
    ARG_UNUSED(p3);

    LOG_INF("AAD handler thread running");

    while (1) {
        k_sem_take(&aad_sem, K_MSEC(100));

        /* WAKE event from ISR */
        if (atomic_cas(&wake_pending, 1, 0)) {
            atomic_set(&wake_consumed, 1);
            LOG_INF("AAD: WAKE detected");
        }
    }
}

/* ================================================================
 * Public API
 * ================================================================ */

bool aad_process_audio(int16_t *buffer, size_t sample_count)
{
    /* WAKE pin event -> reset VAD debounce */
    if (atomic_cas(&wake_consumed, 1, 0)) {
        vad_voice_streak = 0;
        vad_last_voice_ms = k_uptime_get();
        vad_is_recording = false;
        LOG_INF("AAD: WAKE, VAD reset");
    }

    uint32_t avg = avg_abs_amplitude(buffer, sample_count);
    int64_t now = k_uptime_get();
    bool has_voice = avg >= CONFIG_OMI_VAD_ABS_THRESHOLD;

    if (has_voice) {
        vad_last_voice_ms = now;
        if (!vad_is_recording) {
            vad_voice_streak++;
            if (vad_voice_streak >= CONFIG_OMI_VAD_DEBOUNCE_FRAMES) {
                preroll_queue_flush();
                vad_is_recording = true;
                vad_sleeping = false;
                LOG_INF("VAD: RECORDING (avg=%u)", avg);
            }
        }
    } else {
        vad_voice_streak = 0;
        if (vad_is_recording) {
            int64_t silent_ms = now - vad_last_voice_ms;
            if (silent_ms >= CONFIG_OMI_VAD_HOLD_MS) {
                vad_is_recording = false;
                vad_sleeping = true;
                LOG_INF("VAD: SLEEP (silent %lld ms)", silent_ms);
                preroll_reset();
            }
        }
    }

    /* Periodic status log */
    if (now >= vad_next_status_ms) {
        LOG_INF("VAD: %s (avg=%u thr=%u deb=%u hold=%d)",
                vad_is_recording ? "REC" : "SLEEP",
                avg,
                CONFIG_OMI_VAD_ABS_THRESHOLD,
                CONFIG_OMI_VAD_DEBOUNCE_FRAMES,
                CONFIG_OMI_VAD_HOLD_MS);
        vad_next_status_ms = now + VAD_STATUS_LOG_INTERVAL_MS;
    }

    if (!vad_is_recording) {
        preroll_store(buffer);
        return false;
    }

    /* While replaying pre-roll, output only queued pre-roll frames
     * at the same one-frame-per-callback cadence as normal recording.
     * This avoids interleaving historical frames with current live frames
     * (which corrupts temporal ordering). */
    if (vad_preroll_flush_pending > 0) {
        /* Preserve current live frame while we replay pre-roll. */
        if (!live_backlog_push(buffer)) {
            return false;
        }
        preroll_push_one();
        return false;
    }

    /* Once pre-roll replay has started, keep a single-frame cadence:
     * flush one queued live frame, then queue current frame.
     * This preserves FIFO ordering and avoids two-frame bursts into codec. */
    if (vad_live_backlog_cnt > 0) {
        live_backlog_flush_one();
        if (!live_backlog_push(buffer)) {
            return false;
        }
        return false;
    }

    return true;
}

int aad_start(void)
{
    int ret;

    if (!gpio_is_ready_dt(&pin_wake)) {
        LOG_ERR("AAD: WAKE gpio not ready");
        return -ENODEV;
    }

    ret = gpio_pin_configure_dt(&pin_wake, GPIO_INPUT | GPIO_PULL_DOWN);
    if (ret) {
        LOG_ERR("AAD: WAKE pin config failed (%d)", ret);
        return ret;
    }

    gpio_init_callback(&wake_cb_data, wake_pin_isr, BIT(pin_wake.pin));
    ret = gpio_add_callback(pin_wake.port, &wake_cb_data);
    if (ret) {
        LOG_ERR("AAD: WAKE callback failed (%d)", ret);
        return ret;
    }

    ret = gpio_pin_interrupt_configure_dt(&pin_wake, GPIO_INT_EDGE_RISING);
    if (ret) {
        LOG_ERR("AAD: WAKE IRQ config failed (%d)", ret);
        return ret;
    }

    aad_tid = k_thread_create(&aad_thread_data,
                              aad_stack,
                              K_THREAD_STACK_SIZEOF(aad_stack),
                              aad_thread_fn,
                              NULL,
                              NULL,
                              NULL,
                              AAD_THREAD_PRIORITY,
                              0,
                              K_NO_WAIT);
    k_thread_name_set(aad_tid, "aad");

    LOG_INF("AAD: started (WAKE=P1.%d, thr=%d deb=%d hold=%d)",
            pin_wake.pin,
            CONFIG_OMI_VAD_ABS_THRESHOLD,
            CONFIG_OMI_VAD_DEBOUNCE_FRAMES,
            CONFIG_OMI_VAD_HOLD_MS);
    return 0;
}

bool aad_is_sleeping(void)
{
    return vad_sleeping;
}