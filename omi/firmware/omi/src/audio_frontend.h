#ifndef AUDIO_FRONTEND_H
#define AUDIO_FRONTEND_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

struct audio_frontend_state {
    int16_t previous_mono;
    bool seeded;
};

/*
 * Mix 8 kHz interleaved stereo PCM to mono and linearly interpolate it to
 * 16 kHz. The state preserves the previous sample across DMA block boundaries.
 * Returns the number of mono output frames, or zero for invalid arguments.
 */
size_t audio_frontend_8k_stereo_to_16k_mono(struct audio_frontend_state *state,
                                            const int16_t *interleaved,
                                            size_t input_frames,
                                            int16_t *mono_output,
                                            size_t output_capacity);

#endif /* AUDIO_FRONTEND_H */
