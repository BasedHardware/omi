#include "context_core/context_core.h"

#include <cmath>

namespace {

// Coverage carries the larger weight because it is the only term that means the same thing in
// both tables: bm25 magnitudes depend on each table's row count, average document length, and
// term distribution, so a raw score is comparable only against other scores from the same table.
// Normalising within a table and then blending on coverage is what makes a merged ranking honest
// rather than a coin toss between two different scales.
constexpr double kCoverageWeight = 0.6;
constexpr double kLexicalWeight = 0.4;

/// The most of a hit's relevance that age is allowed to take away.
constexpr double kRecencyPull = 0.25;

/// e-folding time. Three days is roughly the horizon over which "I was just looking at this"
/// stops being a reason to prefer one match over a better one.
constexpr double kRecencyDecaySeconds = 3.0 * 24.0 * 60.0 * 60.0;

constexpr double kRelevanceFloorFraction = 0.4;

}  // namespace

extern "C" double ctx_recall_score(double coverage, double lexical, double age_seconds) {
    const double relevance = kCoverageWeight * coverage + kLexicalWeight * lexical;
    const double age = age_seconds > 0.0 ? age_seconds : 0.0;
    const double recency = std::exp(-age / kRecencyDecaySeconds);
    return relevance * (1.0 - kRecencyPull + kRecencyPull * recency);
}

extern "C" double ctx_relevance_floor(double best_score) {
    return kRelevanceFloorFraction * best_score;
}
