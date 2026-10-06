#include <setjmp.h>
#include <stdio.h>
#include <string.h>

/* Compile and exercise the production mic module through a controllable seam. */
#include "../../src/mic.c"

int64_t test_now;
unsigned test_starts, test_stops, test_freed;
int test_wake_level;
const struct device test_device = {.name = "host-pdm"};
bool is_connected, is_charging;
static bool subscribed, live_mode, transfer;
static unsigned hw_entries, sd_requests, delivered, read_count;
static bool pause_timeout;
static int16_t pcm[MAX_FRAMES * CHANNELS];
static jmp_buf mic_step, aad_step;

bool transport_audio_connected(void)
{
    return is_connected;
}
bool transport_is_audio_subscribed(void)
{
    return is_connected && subscribed;
}
bool transport_audio_live_mode(void)
{
    return live_mode;
}
bool storage_transfer_active(void)
{
    return transfer;
}
uint8_t app_settings_get_mic_gain(void)
{
    return 6;
}
int t5838_aad_init(void)
{
    return 0;
}
int t5838_aad_enter(void)
{
    ++hw_entries;
    return 0;
}
void t5838_aad_release_clk(void) {}
void t5838_aad_power(bool on)
{
    ARG_UNUSED(on);
}
void sd_request_power(bool on)
{
    ARG_UNUSED(on);
    ++sd_requests;
}

int dmic_read(const struct device *d, int stream, void **buf, uint32_t *size, int timeout)
{
    ARG_UNUSED(d);
    ARG_UNUSED(stream);
    ARG_UNUSED(timeout);
    if (read_count++ != 0)
        longjmp(mic_step, 1);
    *buf = pcm;
    *size = sizeof(pcm);
    return 0;
}

int k_sem_take(struct k_sem *s, int64_t timeout)
{
    ARG_UNUSED(timeout);
    if (s == &mic_stopped_sem && !s->count) {
        if (pause_timeout)
            return -EAGAIN;
        read_count = 0;
        if (setjmp(mic_step) == 0)
            mic_thread_function(NULL, NULL, NULL);
    }
    if (s == &mic_run_sem)
        longjmp(mic_step, 1);
    if (s == &aad_sem && !s->count)
        longjmp(aad_step, 1);
    if (!s->count)
        return -EAGAIN;
    --s->count;
    return 0;
}

static void capture(int16_t *samples)
{
    assert(samples[0] == pcm[0]);
    ++delivered;
}

static void reset(void)
{
    test_now = 120000;
    test_starts = test_stops = test_freed = 0;
    hw_entries = sd_requests = delivered = 0;
    is_connected = subscribed = live_mode = true;
    is_charging = transfer = pause_timeout = false;
    test_wake_level = 0;
    mic_running = true;
    dmic_dev = &test_device;
    callback_func = capture;
    aad_last_voice_ms = 0;
    aad_observed_generation = aad_vad_generation = 0;
    atomic_clear(&aad_woke);
    atomic_clear(&aad_wake_pending);
    atomic_clear(&aad_in_sleep);
    atomic_clear(&aad_req_sleep);
    atomic_clear(&aad_policy_generation);
    atomic_clear(&aad_recheck_policy);
    atomic_clear(&aad_first_frame_pending);
    k_sem_reset(&aad_sem);
    k_sem_reset(&mic_run_sem);
    const struct software_vad_config cfg = {.amplitude_threshold = 250, .debounce_frames = 3, .hold_ms = 10000};
    software_vad_init(&aad_vad, &cfg, 0);
    memset(pcm, 0, sizeof(pcm));
}

static void run_aad_event(void)
{
    if (setjmp(aad_step) == 0)
        aad_thread_fn(NULL, NULL, NULL);
}

int main(void)
{
    reset();
    test_now = 119999;
    assert(!aad_sleep_due());
    test_now = 120000;
    assert(aad_sleep_due());
    for (size_t i = 0; i < MAX_FRAMES * CHANNELS; ++i)
        pcm[i] = 2000;
    enter_hw_aad();
    assert(mic_running && !mic_in_aad_sleep() && hw_entries == 0);
    assert(test_stops == 0);
    assert(delivered == 1 && test_freed == 1); /* final-read first word retained */

    reset();
    enter_hw_aad();
    assert(mic_in_aad_sleep() && !mic_running && hw_entries == 1);
    assert(sd_requests == 0 && test_stops == 1);
    assert(test_now == 120020); /* live entry did not mask WAKE for 800 ms */
    test_now = 120100;
    aad_wake_isr(&test_device, &aad_wake_cb, BIT(2));
    run_aad_event();
    assert(mic_running && !mic_in_aad_sleep() && test_starts == 1);
    assert(mic_run_sem.count == 1 && sd_requests == 0);
    assert(!aad_sleep_due()); /* no immediate re-sleep before first wake PCM */
    for (size_t i = 0; i < MAX_FRAMES * CHANNELS; ++i)
        pcm[i] = 2000;
    process_audio_buffer(pcm, sizeof(pcm));
    assert(delivered == 2 && test_freed == 2); /* no three-frame debounce */
    assert(!atomic_get(&aad_woke) && !atomic_get(&aad_first_frame_pending));
    assert(aad_last_voice_ms == test_now);

    reset();
    enter_hw_aad();
    live_mode = false;
    mic_aad_policy_changed();
    run_aad_event();
    assert(mic_running && !mic_in_aad_sleep()); /* batch change wakes quietly */
    assert(aad_silence_timeout() == 0);
    process_audio_buffer(pcm, sizeof(pcm));
    assert(delivered == 2); /* batch quiet bypasses software gate */

    reset();
    enter_hw_aad();
    subscribed = false;
    mic_aad_policy_changed();
    run_aad_event();
    assert(mic_running && !mic_in_aad_sleep());

    reset();
    mic_aad_policy_changed();
    assert(!aad_sleep_due()); /* stale requests cannot cross a mode generation */
    reset();
    pause_timeout = true;
    enter_hw_aad();
    assert(mic_running && test_stops == 0 && hw_entries == 0);
    assert(!mic_transition_mutex.locked);
    reset();
    is_charging = true;
    enter_hw_aad();
    assert(test_now == 120820); /* existing charger settle is retained */
    puts("AAD production mic transitions passed (host seam)");
    return 0;
}
