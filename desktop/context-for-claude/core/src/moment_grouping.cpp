#include "context_core/context_core.h"

#include <cstdint>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace {

/// Ten minutes. Deliberately generous: the frames being grouped are already filtered (by a
/// search term, or by app), so "the next matching frame" is not "the next frame" — a person
/// can sit in one window for minutes between two frames that mention the thing being searched
/// for. Longer than this and they went and did something else.
constexpr double kGapSeconds = 600.0;

/// The novelty bar for a window with no established churn, and the floor under every bar. Below
/// this is OCR wobble: the same page read twice never agrees to the word.
constexpr double kNoveltyFloor = 0.10;

/// A fraction alone would let one new word split a nine-word window. This is roughly a sentence:
/// the least new text a reader would call a different thing.
constexpr size_t kNoveltyMinimumWords = 12;

/// A frame this fraction new is a new moment however few words it has — the escape hatch for a
/// window too short to ever clear the word minimum.
///
/// Deliberately near the top of the range: it is meant to fire only for "almost nothing here was
/// here before", leaving every ordinary content change to the churn-relative bar. Measured, 0.6
/// costs a fifth of the collapse (1128 frames -> 267 moments rather than 214) for cases that bar
/// already catches; 0.8 costs 3 moments in 1128.
constexpr double kNoveltyDominantFraction = 0.8;

/// How far above a window's own churn a frame must land to count as a new moment. At 4.0 the
/// new-message case stops firing and at 2.5 the collapse gets measurably worse for nothing.
constexpr double kChurnMultiple = 3.0;

/// EWMA weight on the newest observation. High enough to follow a window that changes character,
/// low enough that one garbled OCR pass does not move the bar.
constexpr double kChurnSmoothing = 0.3;

/// A window with a moment currently open. `churn` outlives the moment on purpose: how much a
/// window normally changes is a property of the window, not of the stretch being grouped, and
/// resetting it on every break makes the bar collapse to the novelty floor and shatter the next
/// moment in the same way.
struct OpenMoment {
    int32_t group = 0;
    double last_at = 0.0;
    std::unordered_set<int64_t> words;
    bool has_churn = false;
    double churn = 0.0;
};

}  // namespace

extern "C" int32_t ctx_moment_groups(const ctx_moment_frame *frames,
                                     size_t frame_count,
                                     const char *key_bytes,
                                     size_t key_bytes_length,
                                     const int64_t *words,
                                     size_t words_length,
                                     int32_t *out_group_of_frame) {
    if (frame_count == 0) {
        return 0;
    }
    if (frames == nullptr || out_group_of_frame == nullptr) {
        return -1;
    }

    // Validated up front rather than per frame: a caller that mis-addressed one frame has a bug
    // that would otherwise surface as a plausible-looking grouping rather than as a failure.
    for (size_t i = 0; i < frame_count; ++i) {
        const ctx_moment_frame &frame = frames[i];
        if (frame.key_length > key_bytes_length ||
            frame.key_offset > key_bytes_length - frame.key_length) {
            return -1;
        }
        if (frame.word_count > words_length ||
            frame.word_offset > words_length - frame.word_count) {
            return -1;
        }
        if (frame.key_length > 0 && key_bytes == nullptr) {
            return -1;
        }
        if (frame.word_count > 0 && words == nullptr) {
            return -1;
        }
    }

    // Pointer arithmetic on a null base is undefined even at offset zero, and an empty Swift array
    // hands back exactly that. Substituting a real address for the empty case keeps the loop below
    // free of special cases.
    static const char kNoKeyBytes = '\0';
    static const int64_t kNoWords = 0;
    const char *keys = key_bytes != nullptr ? key_bytes : &kNoKeyBytes;
    const int64_t *word_pool = words != nullptr ? words : &kNoWords;

    int32_t group_count = 0;
    std::vector<OpenMoment> open;
    std::unordered_map<std::string, size_t> slots;

    for (size_t index = 0; index < frame_count; ++index) {
        const ctx_moment_frame &frame = frames[index];
        const std::string key(keys + frame.key_offset, frame.key_length);
        const int64_t *frame_words = word_pool + frame.word_offset;

        auto existing = slots.find(key);
        if (existing == slots.end()) {
            OpenMoment moment;
            moment.group = group_count++;
            moment.last_at = frame.at;
            moment.words.insert(frame_words, frame_words + frame.word_count);
            open.push_back(std::move(moment));
            slots.emplace(key, open.size() - 1);
            out_group_of_frame[index] = open.back().group;
            continue;
        }

        OpenMoment &slot = open[existing->second];
        bool starts_moment = frame.at - slot.last_at >= kGapSeconds;

        if (!starts_moment && frame.word_count > 0) {
            size_t novel = 0;
            for (size_t w = 0; w < frame.word_count; ++w) {
                if (slot.words.find(frame_words[w]) == slot.words.end()) {
                    ++novel;
                }
            }
            const double fraction =
                static_cast<double>(novel) / static_cast<double>(frame.word_count);

            // The first comparison a window ever gets cannot end a moment: there is no churn to
            // judge it against, and it is exactly the frame most likely to be a half-rendered
            // page.
            if (slot.has_churn) {
                // Two ways to be new, because the word minimum alone has a hole. Requiring 12
                // novel words stops a re-OCR of a long page from breaking on jitter — but it
                // also means a *short* frame can never break at all, however different it is. A
                // chat window whose whole content is "ok sounds good" is three words: entirely
                // new, and silently swallowed into the previous moment. So a frame that is
                // overwhelmingly novel counts regardless of how few words it has.
                const double bar = kNoveltyFloor > kChurnMultiple * slot.churn
                                       ? kNoveltyFloor
                                       : kChurnMultiple * slot.churn;
                if (fraction >= kNoveltyDominantFraction ||
                    (novel >= kNoveltyMinimumWords && fraction > bar)) {
                    starts_moment = true;
                }
            }

            // The bar learns from every frame, including the one that just broke the moment:
            // that frame is evidence about the window too.
            slot.churn = slot.has_churn
                             ? (1.0 - kChurnSmoothing) * slot.churn + kChurnSmoothing * fraction
                             : fraction;
            slot.has_churn = true;
        }

        if (starts_moment) {
            slot.group = group_count++;
            slot.last_at = frame.at;
            slot.words.clear();
            slot.words.insert(frame_words, frame_words + frame.word_count);
        } else {
            slot.last_at = frame.at;
            slot.words.insert(frame_words, frame_words + frame.word_count);
        }
        out_group_of_frame[index] = slot.group;
    }

    return group_count;
}
