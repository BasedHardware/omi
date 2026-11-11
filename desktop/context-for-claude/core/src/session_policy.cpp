#include "context_core/context_core.h"

namespace {
constexpr double kDefaultGapSeconds = 300.0;
constexpr const char *kVersion = "1.0.0";
}  // namespace

extern "C" double ctx_session_default_gap_seconds(void) {
    return kDefaultGapSeconds;
}

extern "C" int ctx_should_open_new_session(int has_last_segment,
                                           double last_segment_ended_at,
                                           double next_segment_started_at,
                                           double gap_seconds) {
    if (has_last_segment == 0) {
        return 1;
    }
    const double gap = next_segment_started_at - last_segment_ended_at;
    if (!(gap > 0.0)) {
        // Also catches NaN, which every comparison below would answer "no" to anyway — but
        // spelling it as "not greater than zero" makes that deliberate rather than incidental.
        return 0;
    }
    return gap > gap_seconds ? 1 : 0;
}

extern "C" const char *ctx_core_version(void) {
    return kVersion;
}
