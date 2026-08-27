#include "software_vad.h"

#include <errno.h>
#include <string.h>

static uint32_t average_absolute_amplitude(const int16_t *samples, size_t sample_count)
{
    uint64_t total = 0U;
    for (size_t i = 0U; i < sample_count; ++i) {
        int32_t sample = samples[i];
        total += (uint32_t) (sample < 0 ? -sample : sample);
    }
    return sample_count == 0U ? 0U : (uint32_t) (total / sample_count);
}

static void store_preroll(struct software_vad_state *state, const int16_t *samples)
{
    memcpy(state->preroll[state->preroll_write], samples, sizeof(state->preroll[0]));
    state->preroll_write = (state->preroll_write + 1U) % SOFTWARE_VAD_PREROLL_FRAMES;
    if (state->preroll_count < SOFTWARE_VAD_PREROLL_FRAMES) {
        state->preroll_count++;
    }
    state->metrics.preroll_count = state->preroll_count;
}

static int emit_block(struct software_vad_state *state,
                      const int16_t *samples,
                      size_t sample_count,
                      software_vad_emit_fn emit,
                      void *context,
                      bool replayed)
{
    int ret = emit(samples, sample_count, context);
    if (ret != 0) {
        state->metrics.emit_failures++;
        return ret;
    }
    state->metrics.emitted_blocks++;
    if (replayed) {
        state->metrics.replayed_blocks++;
    }
    return 0;
}

void software_vad_init(struct software_vad_state *state, const struct software_vad_config *config, int64_t now_ms)
{
    memset(state, 0, sizeof(*state));
    state->metrics.magic = SOFTWARE_VAD_DIAG_MAGIC;
    state->config = *config;
    state->last_voice_ms = now_ms;
    state->recording = true;
    state->metrics.recording = 1U;
}

int software_vad_process(struct software_vad_state *state,
                         const int16_t *samples,
                         size_t sample_count,
                         int64_t now_ms,
                         software_vad_emit_fn emit,
                         void *context)
{
    if (state == NULL || samples == NULL || emit == NULL || sample_count != SOFTWARE_VAD_MAX_SAMPLES) {
        return -EINVAL;
    }

    uint32_t average = average_absolute_amplitude(samples, sample_count);
    bool voice = average >= state->config.amplitude_threshold;
    state->metrics.input_blocks++;
    state->metrics.last_average_amplitude = average;
    if (average > state->metrics.maximum_average_amplitude) {
        state->metrics.maximum_average_amplitude = average;
    }

    if (state->recording) {
        if (voice) {
            state->last_voice_ms = now_ms;
        }

        int ret = emit_block(state, samples, sample_count, emit, context, false);
        if (!voice && now_ms - state->last_voice_ms >= state->config.hold_ms) {
            state->recording = false;
            state->voice_streak = 0U;
            state->preroll_count = 0U;
            state->preroll_write = 0U;
            state->metrics.quiet_transitions++;
            state->metrics.recording = 0U;
            state->metrics.preroll_count = 0U;
        }
        return ret;
    }

    store_preroll(state, samples);
    state->metrics.gated_blocks++;
    if (voice) {
        state->voice_streak++;
    } else {
        state->voice_streak = 0U;
    }

    if (state->voice_streak < state->config.debounce_frames) {
        return 0;
    }

    state->recording = true;
    state->last_voice_ms = now_ms;
    state->voice_streak = 0U;
    state->metrics.active_transitions++;
    state->metrics.recording = 1U;

    uint32_t first =
        (state->preroll_write + SOFTWARE_VAD_PREROLL_FRAMES - state->preroll_count) % SOFTWARE_VAD_PREROLL_FRAMES;
    int first_error = 0;
    for (uint32_t i = 0U; i < state->preroll_count; ++i) {
        uint32_t index = (first + i) % SOFTWARE_VAD_PREROLL_FRAMES;
        int ret = emit_block(state, state->preroll[index], sample_count, emit, context, true);
        if (ret != 0 && first_error == 0) {
            first_error = ret;
        }
    }

    state->preroll_count = 0U;
    state->preroll_write = 0U;
    state->metrics.preroll_count = 0U;
    return first_error;
}
