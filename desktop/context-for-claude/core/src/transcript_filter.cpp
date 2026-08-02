#include "context_core/context_core.h"

#include <cstring>

namespace {

bool equal(const ctx_byte_span &left, const ctx_byte_span &right) {
    return left.length == right.length &&
           (left.length == 0 || std::memcmp(left.bytes, right.bytes, left.length) == 0);
}

}

extern "C" int32_t ctx_transcript_collapse_repeated_runs(const ctx_byte_span *keys,
                                                           size_t key_count,
                                                           size_t repeat_run_threshold,
                                                           uint8_t *out_keep) {
    if (repeat_run_threshold == 0) {
        return -1;
    }
    if (key_count == 0) {
        return 1;
    }
    if (keys == nullptr || out_keep == nullptr) {
        return -1;
    }
    for (size_t index = 0; index < key_count; ++index) {
        if (keys[index].length > 0 && keys[index].bytes == nullptr) {
            return -1;
        }
        out_keep[index] = 1;
    }

    size_t repeated_words = 0;
    size_t index = 0;
    while (index < key_count) {
        size_t end = index + 1;
        while (end < key_count && equal(keys[end], keys[index])) {
            ++end;
        }
        const size_t run_length = end - index;
        if (run_length >= repeat_run_threshold) {
            repeated_words += run_length;
            for (size_t repeated = index + 1; repeated < end; ++repeated) {
                out_keep[repeated] = 0;
            }
        }
        index = end;
    }

    return repeated_words > 0 && repeated_words >= key_count - repeated_words ? 0 : 1;
}
