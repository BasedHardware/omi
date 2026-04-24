#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

bool audio_preprocess_process(
    const int16_t* in,
    size_t in_samples,
    int battery_percent,
    int16_t* out,
    size_t out_capacity_samples,
    size_t* out_samples);

