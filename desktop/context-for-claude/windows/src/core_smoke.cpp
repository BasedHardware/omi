#include "context_core/context_core.h"

#include <cstdio>

int main() {
    const char *version = ctx_core_version();
    const int opens_session = ctx_should_open_new_session(1, 0.0, 301.0, 300.0);
    const double score = ctx_recall_score(1.0, 1.0, 0.0);

    if (version == nullptr || opens_session != 1 || score != 1.0) {
        return 1;
    }

    std::printf("context_core %s: session=%d score=%.1f\n", version, opens_session, score);
    return 0;
}
