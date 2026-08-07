#include "context_core/context_core.h"

#include <cmath>
#include <cstdint>

namespace {
constexpr double kInt16FullScale = 32768.0;
constexpr float kFloatFullScale = 32768.0f;
constexpr float kPeakAmplitude = 32767.0f;
}  // namespace

extern "C" double ctx_pcm_rms_int16le(const uint8_t *bytes, size_t byte_count) {
    const size_t sample_count = byte_count / 2;
    if (bytes == nullptr || sample_count == 0) {
        return 0.0;
    }

    double sum_of_squares = 0.0;
    for (size_t index = 0; index < sample_count; ++index) {
        const size_t offset = index * 2;
        const uint16_t word = static_cast<uint16_t>(bytes[offset]) |
                              (static_cast<uint16_t>(bytes[offset + 1]) << 8U);
        // Avoid converting an out-of-range unsigned value directly to int16_t:
        // the C++ standard leaves that conversion implementation-defined.
        const int32_t sample = word < 0x8000U ? static_cast<int32_t>(word)
                                              : static_cast<int32_t>(word) - 0x10000;
        const double magnitude = static_cast<double>(sample);
        sum_of_squares += magnitude * magnitude;
    }
    return std::sqrt(sum_of_squares / static_cast<double>(sample_count)) / kInt16FullScale;
}

/* --------------------------------------------------------------------------- encode */

extern "C" size_t ctx_pcm_encode_int16le(const float *samples, size_t sample_count,
                                         uint8_t *out_bytes) {
    if (samples == nullptr || out_bytes == nullptr || sample_count == 0) {
        return 0;
    }
    for (size_t index = 0; index < sample_count; ++index) {
        // Clamp to -1…1, mapping NaN to silence. The guard form (rather than nested min/max)
        // is deliberate: min(max(NaN, -1), 1) propagates NaN into the Int16 conversion, which
        // is undefined behaviour in C and a trap in Swift.
        float value = samples[index];
        if (value != value) {
            value = 0.0f;  // NaN check
        }
        if (value < -1.0f) {
            value = -1.0f;
        } else if (value > 1.0f) {
            value = 1.0f;
        }
        // Round to nearest, then scale. `round` rounds half-away-from-zero,
        // matching Swift's `rounded()`.
        const int32_t scaled = static_cast<int32_t>(std::round(value * kPeakAmplitude));
        const uint16_t pattern = static_cast<uint16_t>(static_cast<int16_t>(scaled));
        out_bytes[index * 2] = static_cast<uint8_t>(pattern & 0xFFU);
        out_bytes[index * 2 + 1] = static_cast<uint8_t>((pattern >> 8U) & 0xFFU);
    }
    return sample_count * 2;
}

/* --------------------------------------------------------------------------- decode */

extern "C" size_t ctx_pcm_decode_int16le(const uint8_t *bytes, size_t byte_count,
                                         float *out_samples) {
    const size_t sample_count = byte_count / 2;
    if (bytes == nullptr || out_samples == nullptr || sample_count == 0) {
        return 0;
    }
    for (size_t index = 0; index < sample_count; ++index) {
        const size_t offset = index * 2;
        const uint16_t word = static_cast<uint16_t>(bytes[offset]) |
                              (static_cast<uint16_t>(bytes[offset + 1]) << 8U);
        // Same safe conversion as in ctx_pcm_rms_int16le.
        const int32_t sample = word < 0x8000U ? static_cast<int32_t>(word)
                                              : static_cast<int32_t>(word) - 0x10000;
        out_samples[index] = static_cast<float>(sample) / kFloatFullScale;
    }
    return sample_count;
}

/* -------------------------------------------------------------------------- downmix */

extern "C" size_t ctx_pcm_downmix_mono(const float *interleaved, size_t sample_count, int channels,
                                       float *out_mono) {
    if (channels <= 1 || interleaved == nullptr || out_mono == nullptr) {
        return 0;
    }
    const size_t frame_count = sample_count / static_cast<size_t>(channels);
    if (frame_count == 0) {
        return 0;
    }
    const float scale = 1.0f / static_cast<float>(channels);
    for (size_t frame = 0; frame < frame_count; ++frame) {
        float sum = 0.0f;
        const size_t base = frame * static_cast<size_t>(channels);
        for (int ch = 0; ch < channels; ++ch) {
            sum += interleaved[base + static_cast<size_t>(ch)];
        }
        out_mono[frame] = sum * scale;
    }
    return frame_count;
}
