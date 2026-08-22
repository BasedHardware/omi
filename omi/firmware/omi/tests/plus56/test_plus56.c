#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "audio_frontend.h"
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

static void test_audio_frontend_interpolates_across_blocks(void)
{
    struct audio_frontend_state state = {0};
    const int16_t first[] = {100, 100, 300, 300};
    int16_t output[4] = {0};
    assert(audio_frontend_8k_stereo_to_16k_mono(&state, first, 2U, output, 4U) == 4U);
    assert(output[0] == 100);
    assert(output[1] == 100);
    assert(output[2] == 200);
    assert(output[3] == 300);

    const int16_t second[] = {500, 500};
    assert(audio_frontend_8k_stereo_to_16k_mono(&state, second, 1U, output, 2U) == 2U);
    assert(output[0] == 400);
    assert(output[1] == 500);
    assert(audio_frontend_8k_stereo_to_16k_mono(&state, second, 1U, output, 1U) == 0U);
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
    assert(state.recording);
    assert(state.metrics.magic == SOFTWARE_VAD_DIAG_MAGIC);

    fill_block(block, 0);
    assert(software_vad_process(&state, block, SOFTWARE_VAD_MAX_SAMPLES, 0, capture_emit, &log) == 0);
    assert(software_vad_process(&state, block, SOFTWARE_VAD_MAX_SAMPLES, 500, capture_emit, &log) == 0);
    assert(software_vad_process(&state, block, SOFTWARE_VAD_MAX_SAMPLES, 1000, capture_emit, &log) == 0);
    assert(!state.recording);
    assert(state.metrics.quiet_transitions == 1U);

    fill_block(block, 10);
    assert(software_vad_process(&state, block, SOFTWARE_VAD_MAX_SAMPLES, 1100, capture_emit, &log) == 0);
    fill_block(block, 200);
    assert(software_vad_process(&state, block, SOFTWARE_VAD_MAX_SAMPLES, 1200, capture_emit, &log) == 0);
    assert(software_vad_process(&state, block, SOFTWARE_VAD_MAX_SAMPLES, 1300, capture_emit, &log) == 0);
    assert(software_vad_process(&state, block, SOFTWARE_VAD_MAX_SAMPLES, 1400, capture_emit, &log) == 0);

    assert(state.recording);
    assert(state.metrics.active_transitions == 1U);
    assert(state.metrics.gated_blocks == 4U);
    assert(state.metrics.replayed_blocks == 4U);
    assert(state.metrics.emitted_blocks == 7U);
    assert(log.count == 7U);
    assert(log.first_sample[3] == 10);
    assert(log.first_sample[4] == 200);
    assert(log.first_sample[5] == 200);
    assert(log.first_sample[6] == 200);

    fill_block(block, 0);
    assert(software_vad_process(&state, block, SOFTWARE_VAD_MAX_SAMPLES, 2500, capture_emit, &log) == 0);
    assert(!state.recording);
    assert(state.metrics.quiet_transitions == 2U);
}

static void test_software_vad_fails_open_after_emit_error(void)
{
    struct software_vad_state state;
    const struct software_vad_config config = {
        .amplitude_threshold = 100U,
        .debounce_frames = 1U,
        .hold_ms = 500,
    };
    struct emit_log log = {.fail_at = 1U};
    int16_t block[SOFTWARE_VAD_MAX_SAMPLES];

    software_vad_init(&state, &config, 0);
    fill_block(block, 0);
    assert(software_vad_process(&state, block, SOFTWARE_VAD_MAX_SAMPLES, 500, capture_emit, &log) == 0);
    assert(!state.recording);

    fill_block(block, 200);
    assert(software_vad_process(&state, block, SOFTWARE_VAD_MAX_SAMPLES, 600, capture_emit, &log) == -ENOSPC);
    assert(state.recording);
    assert(state.metrics.emit_failures == 1U);

    log.fail_at = SIZE_MAX;
    assert(software_vad_process(&state, block, SOFTWARE_VAD_MAX_SAMPLES, 700, capture_emit, &log) == 0);
    assert(state.recording);
}

int main(void)
{
    test_audio_frontend_interpolates_across_blocks();
    test_software_vad_preroll_and_transitions();
    test_software_vad_fails_open_after_emit_error();
    puts("plus56 audio frontend and software VAD tests passed");
    return 0;
}
