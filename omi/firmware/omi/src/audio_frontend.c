#include "audio_frontend.h"

#define INPUT_CHANNELS 2U
#define OUTPUTS_PER_INPUT 2U

size_t audio_frontend_8k_stereo_to_16k_mono(struct audio_frontend_state *state,
                                            const int16_t *interleaved,
                                            size_t input_frames,
                                            int16_t *mono_output,
                                            size_t output_capacity)
{
    if (state == NULL || interleaved == NULL || mono_output == NULL || input_frames == 0U ||
        output_capacity < input_frames * OUTPUTS_PER_INPUT) {
        return 0U;
    }

    size_t output_frame = 0U;
    for (size_t input_frame = 0U; input_frame < input_frames; ++input_frame) {
        size_t input = input_frame * INPUT_CHANNELS;
        int32_t mixed = (int32_t) interleaved[input] + (int32_t) interleaved[input + 1U];
        int16_t mono = (int16_t) (mixed / 2);

        if (!state->seeded) {
            state->previous_mono = mono;
            state->seeded = true;
        }

        mono_output[output_frame++] = (int16_t) (((int32_t) state->previous_mono + (int32_t) mono) / 2);
        mono_output[output_frame++] = mono;
        state->previous_mono = mono;
    }

    return output_frame;
}
