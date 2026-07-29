#include "context_core/context_core.h"

#include <cmath>

namespace {
constexpr double kInt16FullScale = 32768.0;
}

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