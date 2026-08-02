#include "context_core/context_core.h"

#include <cstdio>

int main() {
    const char *version = ctx_core_version();
    const int opens_session = ctx_should_open_new_session(1, 0.0, 301.0, 300.0);
    const double score = ctx_recall_score(1.0, 1.0, 0.0);
    const uint8_t key[] = {'a'};
    const ctx_byte_span repeated[] = {{key, 1}, {key, 1}, {key, 1}, {key, 1}};
    uint8_t keep[4] = {};
    const int32_t transcript = ctx_transcript_collapse_repeated_runs(repeated, 4, 4, keep);

    if (version == nullptr || opens_session != 1 || score != 1.0 || transcript != 0 || keep[0] != 1 ||
        keep[1] != 0 || keep[2] != 0 || keep[3] != 0) {
        return 1;
    }

    std::printf("context_core %s: session=%d score=%.1f\n", version, opens_session, score);
    return 0;
}
