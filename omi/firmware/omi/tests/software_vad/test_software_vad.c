#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "software_vad.h"

struct emit_log {
    int16_t first_sample[32];
    size_t count;
    size_t fail_at;
};

static int capture_emit(const int16_t *samples, size_t sample_count, void *context)
{
    struct emit_log *log = context;
    assert(sample_count == SOFTWARE_VAD_MAX_SAMPLES);
    if (log->count == log->fail_at) {
        log->count++;
        return -ENOSPC;
    }
    log->first_sample[log->count++] = samples[0];
    return 0;
}

static void fill_block(int16_t *block, int16_t value)
{
    for (size_t i = 0U; i < SOFTWARE_VAD_MAX_SAMPLES; ++i) {
        block[i] = value;
    }
}

static void test_software_vad_preroll_and_transitions(void)
{
    struct software_vad_state state;
    const struct software_vad_config config = {
        .amplitude_threshold = 100U,
        .debounce_frames = 3U,
        .hold_ms = 1000,
    };
    struct emit_log log = {.fail_at = SIZE_MAX};
    int16_t block[SOFTWARE_VAD_MAX_SAMPLES];

    software_vad_init(&state, &config, 0);
    assert(software_vad_is_recording(&state));
    assert(state.metrics.magic == SOFTWARE_VAD_DIAG_MAGIC);

    fill_block(block, 0);
    assert(software_vad_process(&state, block, SOFTWARE_VAD_MAX_SAMPLES, 0, capture_emit, &log) == 0);
    assert(software_vad_process(&state, block, SOFTWARE_VAD_MAX_SAMPLES, 500, capture_emit, &log) == 0);
    assert(software_vad_process(&state, block, SOFTWARE_VAD_MAX_SAMPLES, 1000, capture_emit, &log) == 0);
    assert(!software_vad_is_recording(&state));
    assert(state.metrics.quiet_transitions == 1U);

    fill_block(block, 10);
    assert(software_vad_process(&state, block, SOFTWARE_VAD_MAX_SAMPLES, 1100, capture_emit, &log) == 0);
    fill_block(block, 200);
    assert(software_vad_process(&state, block, SOFTWARE_VAD_MAX_SAMPLES, 1200, capture_emit, &log) == 0);
    assert(software_vad_process(&state, block, SOFTWARE_VAD_MAX_SAMPLES, 1300, capture_emit, &log) == 0);
    assert(software_vad_process(&state, block, SOFTWARE_VAD_MAX_SAMPLES, 1400, capture_emit, &log) == 0);

    assert(software_vad_is_recording(&state));
    assert(state.metrics.active_transitions == 1U);
    assert(state.metrics.gated_blocks == 4U);
    assert(state.metrics.replayed_blocks == 4U);
    assert(state.metrics.emitted_blocks == 7U);
    assert(log.count == 7U);
    assert(log.first_sample[3] == 10);
    assert(log.first_sample[4] == 200);
}

static void test_software_vad_on_hardware_wake(void)
{
    struct software_vad_state state;
    const struct software_vad_config config = {
        .amplitude_threshold = 100U,
        .debounce_frames = 3U,
        .hold_ms = 1000,
    };
    struct emit_log log = {.fail_at = SIZE_MAX};
    int16_t block[SOFTWARE_VAD_MAX_SAMPLES];

    software_vad_init(&state, &config, 0);
    fill_block(block, 0);
    assert(software_vad_process(&state, block, SOFTWARE_VAD_MAX_SAMPLES, 1000, capture_emit, &log) == 0);
    assert(!software_vad_is_recording(&state));

    software_vad_on_hardware_wake(&state, 2000);
    assert(software_vad_is_recording(&state));
    fill_block(block, 50);
    size_t emits_before = log.count;
    assert(software_vad_process(&state, block, SOFTWARE_VAD_MAX_SAMPLES, 2100, capture_emit, &log) == 0);
    assert(log.count == emits_before + 1U);
    assert(log.first_sample[log.count - 1] == 50);
}

static void test_software_vad_emit_failure_stays_active(void)
{
    struct software_vad_state state;
    const struct software_vad_config config = {
        .amplitude_threshold = 100U,
        .debounce_frames = 3U,
        .hold_ms = 1000,
    };
    struct emit_log log = {.fail_at = 3U};
    int16_t block[SOFTWARE_VAD_MAX_SAMPLES];

    software_vad_init(&state, &config, 0);
    fill_block(block, 0);
    assert(software_vad_process(&state, block, SOFTWARE_VAD_MAX_SAMPLES, 1000, capture_emit, &log) == 0);
    assert(!software_vad_is_recording(&state));

    fill_block(block, 200);
    assert(software_vad_process(&state, block, SOFTWARE_VAD_MAX_SAMPLES, 1100, capture_emit, &log) == 0);
    assert(software_vad_process(&state, block, SOFTWARE_VAD_MAX_SAMPLES, 1200, capture_emit, &log) == 0);
    assert(software_vad_process(&state, block, SOFTWARE_VAD_MAX_SAMPLES, 1300, capture_emit, &log) == -ENOSPC);
    assert(software_vad_is_recording(&state));
    assert(state.metrics.emit_failures == 1U);

    log.fail_at = SIZE_MAX;
    assert(software_vad_process(&state, block, SOFTWARE_VAD_MAX_SAMPLES, 1400, capture_emit, &log) == 0);
    assert(software_vad_is_recording(&state));
}

int main(void)
{
    test_software_vad_preroll_and_transitions();
    test_software_vad_on_hardware_wake();
    test_software_vad_emit_failure_stays_active();
    puts("software_vad host tests passed");
    return 0;
}
