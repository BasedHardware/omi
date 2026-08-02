#include "context_core/context_core.h"

#include <iomanip>
#include <iostream>

int main() {
    const double score = ctx_recall_score(0.75, 0.5, 0.0);
    const double floor = ctx_relevance_floor(score);

    std::cout << "context-core=" << ctx_core_version() << " recall-score=" << std::fixed
              << std::setprecision(6) << score << " relevance-floor=" << floor << '\n';
    return 0;
}
