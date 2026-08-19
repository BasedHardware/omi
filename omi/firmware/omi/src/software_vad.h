#ifndef SOFTWARE_VAD_H
#define SOFTWARE_VAD_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define SOFTWARE_VAD_MAX_SAMPLES 1600U
#define SOFTWARE_VAD_PREROLL_FRAMES 5U
#define SOFTWARE_VAD_DIAG_MAGIC 0x56325631U

typedef int (*software_vad_emit_fn)(const int16_t *samples, size_t sample_count, void *context);

struct software_vad_metrics {
    uint32_t magic;
    uint32_t input_blocks;
    uint32_t emitted_blocks;
    uint32_t gated_blocks;
    uint32_t replayed_blocks;
    uint32_t active_transitions;
    uint32_t quiet_transitions;
    uint32_t emit_failures;
    uint32_t last_average_amplitude;
    uint32_t maximum_average_amplitude;
    uint32_t recording;
    uint32_t preroll_count;
};

struct software_vad_config {
    uint32_t amplitude_threshold;
    uint32_t debounce_frames;
    int64_t hold_ms;
};

struct software_vad_state {
    /* Keep metrics first so J-Link can decode them from the global symbol. */
    struct software_vad_metrics metrics;
    struct software_vad_config config;
    int64_t last_voice_ms;
    uint32_t voice_streak;
    uint32_t preroll_write;
    uint32_t preroll_count;
    bool recording;
    int16_t preroll[SOFTWARE_VAD_PREROLL_FRAMES][SOFTWARE_VAD_MAX_SAMPLES];
};

void software_vad_init(struct software_vad_state *state, const struct software_vad_config *config, int64_t now_ms);

/*
 * Process one PCM block. Active audio is emitted immediately. During quiet,
 * blocks are retained in a bounded pre-roll ring and replayed oldest-first
 * after the configured number of consecutive active blocks.
 *
 * Returns zero when all required emits succeed, otherwise the first negative
 * emit error. A failure never returns the VAD to quiet; subsequent live blocks
 * continue to be offered to the codec (fail open to capture).
 */
int software_vad_process(struct software_vad_state *state,
                         const int16_t *samples,
                         size_t sample_count,
                         int64_t now_ms,
                         software_vad_emit_fn emit,
                         void *context);

#endif /* SOFTWARE_VAD_H */
