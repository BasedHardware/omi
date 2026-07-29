#ifndef CODEC_INPUT_CAPACITY_H
#define CODEC_INPUT_CAPACITY_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

static inline bool codec_pcm_frame_fits(size_t available_bytes, size_t sample_count)
{
    return sample_count <= SIZE_MAX / sizeof(int16_t) && available_bytes >= sample_count * sizeof(int16_t);
}

#endif
