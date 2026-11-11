/*
 * Native unit tests for the portable core.
 *
 * Deliberately dependency-free: one translation unit, one macro, one exit code. This library's
 * whole reason to exist is that it builds on a machine nobody has configured, and a test suite
 * that first has to download GoogleTest is a test suite that stops running there.
 */

#include "context_core/context_core.h"

#include <cmath>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

namespace {

int g_failures = 0;
int g_checks = 0;

void check(bool condition, const char *expression, const char *file, int line) {
    ++g_checks;
    if (!condition) {
        ++g_failures;
        std::printf("FAIL %s:%d  %s\n", file, line, expression);
    }
}

void check_close(double actual, double expected, double tolerance, const char *expression,
                 const char *file, int line) {
    ++g_checks;
    if (!(std::fabs(actual - expected) <= tolerance)) {
        ++g_failures;
        std::printf("FAIL %s:%d  %s  (got %.10f, want %.10f)\n", file, line, expression, actual,
                    expected);
    }
}

#define CHECK(expr) check((expr), #expr, __FILE__, __LINE__)
#define CHECK_CLOSE(actual, expected, tol) \
    check_close((actual), (expected), (tol), #actual " ~= " #expected, __FILE__, __LINE__)

/* ------------------------------------------------------------------ session boundaries */

void test_session_boundaries() {
    const double gap = ctx_session_default_gap_seconds();
    CHECK_CLOSE(gap, 300.0, 0.0);

    // Nothing stored yet is always a new session.
    CHECK(ctx_should_open_new_session(0, 0.0, 0.0, gap) == 1);
    CHECK(ctx_should_open_new_session(0, 9999.0, 0.0, gap) == 1);

    // Strictly greater than the threshold, so a gap landing exactly on it continues.
    CHECK(ctx_should_open_new_session(1, 1000.0, 1000.0 + gap, gap) == 0);
    CHECK(ctx_should_open_new_session(1, 1000.0, 1000.0 + gap + 0.001, gap) == 1);
    CHECK(ctx_should_open_new_session(1, 1000.0, 1001.0, gap) == 0);

    // A backwards clock continues the current session rather than splitting it.
    CHECK(ctx_should_open_new_session(1, 1000.0, 1.0, gap) == 0);
    CHECK(ctx_should_open_new_session(1, 1000.0, 1000.0, gap) == 0);

    // An injected threshold is honoured, which is what lets callers express minutes without
    // waiting them out.
    CHECK(ctx_should_open_new_session(1, 0.0, 2.0, 1.0) == 1);
    CHECK(ctx_should_open_new_session(1, 0.0, 2.0, 60.0) == 0);
}

/* --------------------------------------------------------------------------- audio */

void test_pcm_rms() {
    const uint8_t half_scale[] = {0x00, 0x40, 0x00, 0x40, 0x00, 0x40, 0x00, 0x40};
    CHECK_CLOSE(ctx_pcm_rms_int16le(half_scale, sizeof(half_scale)), 0.5, 1e-12);

    const uint8_t silence[] = {0x00, 0x00, 0x00, 0x00};
    CHECK_CLOSE(ctx_pcm_rms_int16le(silence, sizeof(silence)), 0.0, 0.0);
    CHECK_CLOSE(ctx_pcm_rms_int16le(nullptr, 0), 0.0, 0.0);
    CHECK_CLOSE(ctx_pcm_rms_int16le(half_scale, 1), 0.0, 0.0);

    // The incomplete trailing byte is ignored, not treated as a second sample.
    const uint8_t ragged[] = {0x00, 0x40, 0x7f};
    CHECK_CLOSE(ctx_pcm_rms_int16le(ragged, sizeof(ragged)), 0.5, 1e-12);
}

void test_pcm_encode_little_endian_and_clamped() {
    // 0.5 * 32767 rounds to 16384 == 0x4000, low byte first.
    uint8_t buf[2] = {};
    const float half = 0.5f;
    const size_t written = ctx_pcm_encode_int16le(&half, 1, buf);
    CHECK(written == 2);
    CHECK(buf[0] == 0x00);
    CHECK(buf[1] == 0x40);

    const float tie = 16382.5f / 32767.0f;
    ctx_pcm_encode_int16le(&tie, 1, buf);
    CHECK(buf[0] == 0xFF);
    CHECK(buf[1] == 0x3F);

    // Zero.
    const float zero = 0.0f;
    ctx_pcm_encode_int16le(&zero, 1, buf);
    CHECK(buf[0] == 0x00);
    CHECK(buf[1] == 0x00);

    // Positive clamp: values above 1.0 clamp to 0x7FFF (32767).
    const float over = 2.0f;
    ctx_pcm_encode_int16le(&over, 1, buf);
    CHECK(buf[0] == 0xFF);
    CHECK(buf[1] == 0x7F);

    // Negative clamp: values below -1.0 clamp to 0x8001 (-32767).
    const float under = -3.0f;
    ctx_pcm_encode_int16le(&under, 1, buf);
    CHECK(buf[0] == 0x01);
    CHECK(buf[1] == 0x80);

    // NaN maps to silence (0x0000).
    const float nan_val = std::nanf("");
    ctx_pcm_encode_int16le(&nan_val, 1, buf);
    CHECK(buf[0] == 0x00);
    CHECK(buf[1] == 0x00);

    // Empty input.
    CHECK(ctx_pcm_encode_int16le(nullptr, 0, buf) == 0);
    CHECK(ctx_pcm_encode_int16le(&half, 0, buf) == 0);
    CHECK(ctx_pcm_encode_int16le(&half, 1, nullptr) == 0);
}

void test_pcm_decode_basic() {
    // Decode 0x4000 (16384) → 0.5.
    const uint8_t encoded[] = {0x00, 0x40, 0x00, 0xC0};  // 0.5, -0.5
    float samples[2] = {};
    const size_t count = ctx_pcm_decode_int16le(encoded, sizeof(encoded), samples);
    CHECK(count == 2);
    CHECK_CLOSE(samples[0], 0.5f, 1e-4f);
    CHECK_CLOSE(samples[1], -0.5f, 1e-4f);

    // Empty input.
    float dummy;
    CHECK(ctx_pcm_decode_int16le(nullptr, 0, &dummy) == 0);
    CHECK(ctx_pcm_decode_int16le(encoded, 0, &dummy) == 0);
    CHECK(ctx_pcm_decode_int16le(encoded, 2, nullptr) == 0);

    // Odd trailing byte is ignored.
    const uint8_t ragged[] = {0x00, 0x40, 0x7F};
    float ragged_samples[1] = {};
    CHECK(ctx_pcm_decode_int16le(ragged, sizeof(ragged), ragged_samples) == 1);
    CHECK_CLOSE(ragged_samples[0], 0.5f, 1e-4f);
}

void test_pcm_roundtrip_stays_within_one_lsb() {
    const float samples[] = {0.0f, 0.5f, -0.5f, 0.123f, -0.987f, 1.0f, -1.0f};
    const size_t n = sizeof(samples) / sizeof(samples[0]);

    uint8_t encoded[n * 2];
    ctx_pcm_encode_int16le(samples, n, encoded);

    float decoded[n];
    ctx_pcm_decode_int16le(encoded, n * 2, decoded);

    for (size_t i = 0; i < n; ++i) {
        CHECK(std::fabs(decoded[i] - samples[i]) <= 1e-4f);
    }
}

void test_pcm_downmix_averages_channels() {
    // Stereo: (1,0) (0.5,-0.5) (0.2,0.2) → mono: 0.5, 0, 0.2
    const float stereo[] = {1.0f, 0.0f, 0.5f, -0.5f, 0.2f, 0.2f};
    float mono[3] = {};
    const size_t count = ctx_pcm_downmix_mono(stereo, 6, 2, mono);
    CHECK(count == 3);
    CHECK_CLOSE(mono[0], 0.5f, 1e-6f);
    CHECK_CLOSE(mono[1], 0.0f, 1e-6f);
    CHECK_CLOSE(mono[2], 0.2f, 1e-6f);

    // channels <= 1 returns zero (caller should use input untouched).
    float dummy[3];
    CHECK(ctx_pcm_downmix_mono(stereo, 6, 1, dummy) == 0);
    CHECK(ctx_pcm_downmix_mono(stereo, 6, 0, dummy) == 0);

    // Empty input.
    CHECK(ctx_pcm_downmix_mono(nullptr, 0, 2, mono) == 0);
    CHECK(ctx_pcm_downmix_mono(stereo, 0, 2, mono) == 0);
    CHECK(ctx_pcm_downmix_mono(stereo, 6, 2, nullptr) == 0);

    // Ragged buffer: partial frame truncated.
    const float ragged[] = {1.0f, 0.0f, 1.0f};
    float ragged_mono[1] = {};
    CHECK(ctx_pcm_downmix_mono(ragged, 3, 2, ragged_mono) == 1);
    CHECK_CLOSE(ragged_mono[0], 0.5f, 1e-6f);
}

/* ------------------------------------------------------------------- recall ranking */

void test_recall_score() {
    // The property the whole floor design rests on: a document containing every query term cannot
    // be discarded however old it is and however poor its lexical score, because the highest floor
    // any query can produce is 0.4 * 1.0 and full coverage is worth 0.6 * 0.75 even at infinite age.
    const double ancient_full_coverage = ctx_recall_score(1.0, 0.0, 1.0e9);
    CHECK(ancient_full_coverage > ctx_relevance_floor(1.0));
    CHECK_CLOSE(ancient_full_coverage, 0.45, 1e-9);

    // Nothing can exceed 1.0, and a perfect fresh hit reaches it.
    CHECK_CLOSE(ctx_recall_score(1.0, 1.0, 0.0), 1.0, 1e-12);
    CHECK(ctx_recall_score(1.0, 1.0, 1.0e9) <= 1.0);

    // Age is a bounded multiplier: an infinitely old hit keeps exactly 75% of its relevance.
    CHECK_CLOSE(ctx_recall_score(1.0, 1.0, 1.0e12), 0.75, 1e-9);

    // A negative age is clamped rather than rewarded.
    CHECK_CLOSE(ctx_recall_score(0.5, 0.5, -1000.0), ctx_recall_score(0.5, 0.5, 0.0), 1e-12);

    // Recency can never overturn a relevance gap of more than 25%.
    const double stale_strong = ctx_recall_score(1.0, 1.0, 1.0e12);
    const double fresh_weak = ctx_recall_score(0.7, 0.7, 0.0);
    CHECK(stale_strong > fresh_weak);

    // Coverage outweighs lexical quality at equal magnitude.
    CHECK(ctx_recall_score(1.0, 0.0, 0.0) > ctx_recall_score(0.0, 1.0, 0.0));

    CHECK_CLOSE(ctx_relevance_floor(1.0), 0.4, 1e-12);
    CHECK_CLOSE(ctx_relevance_floor(0.0), 0.0, 1e-12);
}

/* ------------------------------------------------------------------ moment grouping */

/// Builds the flat buffers the ABI takes from a readable list of (time, key, words).
struct MomentFixture {
    std::vector<ctx_moment_frame> frames;
    std::string keys;
    std::vector<int64_t> words;

    void add(double at, const std::string &key, const std::vector<int64_t> &frame_words) {
        ctx_moment_frame frame;
        frame.at = at;
        frame.key_offset = keys.size();
        frame.key_length = key.size();
        frame.word_offset = words.size();
        frame.word_count = frame_words.size();
        keys += key;
        words.insert(words.end(), frame_words.begin(), frame_words.end());
        frames.push_back(frame);
    }

    /// Returns the group index per frame, or an empty vector when the call reported an error.
    std::vector<int32_t> group(int32_t *out_count) {
        std::vector<int32_t> assignment(frames.size(), -1);
        const int32_t count = ctx_moment_groups(
            frames.empty() ? nullptr : frames.data(), frames.size(),
            keys.empty() ? nullptr : keys.data(), keys.size(),
            words.empty() ? nullptr : words.data(), words.size(),
            assignment.empty() ? nullptr : assignment.data());
        *out_count = count;
        if (count < 0) {
            return {};
        }
        return assignment;
    }
};

std::vector<int64_t> range(int64_t first, size_t count) {
    std::vector<int64_t> result;
    result.reserve(count);
    for (size_t i = 0; i < count; ++i) {
        result.push_back(first + static_cast<int64_t>(i));
    }
    return result;
}

void test_moment_empty_input() {
    int32_t count = -1;
    MomentFixture fixture;
    const std::vector<int32_t> groups = fixture.group(&count);
    CHECK(count == 0);
    CHECK(groups.empty());
}

void test_moment_single_frame_is_one_moment() {
    MomentFixture fixture;
    fixture.add(0.0, "Arc\x01omi pull request", range(1, 20));
    int32_t count = -1;
    const std::vector<int32_t> groups = fixture.group(&count);
    CHECK(count == 1);
    CHECK(groups.size() == 1 && groups[0] == 0);
}

void test_moment_static_page_stays_one_moment() {
    // A still page re-OCR'd: a couple of words wobble each pass and nothing else changes.
    MomentFixture fixture;
    for (int i = 0; i < 8; ++i) {
        std::vector<int64_t> frame_words = range(1, 60);
        frame_words.push_back(1000 + i);  // one novel word per frame — OCR wobble, not a change
        fixture.add(i * 3.0, "Arc\x01omi docs", frame_words);
    }
    int32_t count = -1;
    const std::vector<int32_t> groups = fixture.group(&count);
    CHECK(count == 1);
    for (size_t i = 0; i < groups.size(); ++i) {
        CHECK(groups[i] == 0);
    }
}

void test_moment_gap_opens_a_new_moment() {
    MomentFixture fixture;
    fixture.add(0.0, "Warp\x01omi main", range(1, 30));
    fixture.add(600.0, "Warp\x01omi main", range(1, 30));
    int32_t count = -1;
    const std::vector<int32_t> groups = fixture.group(&count);
    CHECK(count == 2);
    CHECK(groups[0] == 0 && groups[1] == 1);

    // One second under the gap is still the same moment — the boundary is inclusive on open.
    MomentFixture under;
    under.add(0.0, "Warp\x01omi main", range(1, 30));
    under.add(599.0, "Warp\x01omi main", range(1, 30));
    int32_t under_count = -1;
    const std::vector<int32_t> under_groups = under.group(&under_count);
    CHECK(under_count == 1);
    CHECK(under_groups[0] == 0 && under_groups[1] == 0);
}

void test_moment_dominant_novelty_opens_a_new_moment() {
    // Two identical frames establish a churn of zero, then the window is replaced wholesale.
    MomentFixture fixture;
    fixture.add(0.0, "Messages\x01priyanka", range(1, 10));
    fixture.add(3.0, "Messages\x01priyanka", range(1, 10));
    fixture.add(6.0, "Messages\x01priyanka", range(500, 10));
    int32_t count = -1;
    const std::vector<int32_t> groups = fixture.group(&count);
    CHECK(count == 2);
    CHECK(groups[0] == 0 && groups[1] == 0 && groups[2] == 1);
}

void test_moment_first_comparison_never_breaks() {
    // The very first comparison a window gets has no churn to judge against — it is the frame most
    // likely to be a half-rendered page — so even a wholesale replacement stays in the moment.
    MomentFixture fixture;
    fixture.add(0.0, "Arc\x01periphery", range(1, 40));
    fixture.add(3.0, "Arc\x01periphery", range(900, 40));
    int32_t count = -1;
    const std::vector<int32_t> groups = fixture.group(&count);
    CHECK(count == 1);
    CHECK(groups[0] == 0 && groups[1] == 0);
}

void test_moment_high_churn_window_does_not_shatter() {
    // A terminal that rewrites a third of itself every frame must not start a moment every frame:
    // the bar is relative to the window's own churn, so a steady 30% never clears 3x30%.
    MomentFixture fixture;
    int64_t next = 1;
    std::vector<int64_t> carried = range(next, 60);
    next += 60;
    fixture.add(0.0, "Warp\x01claude code", carried);
    for (int i = 1; i < 10; ++i) {
        std::vector<int64_t> frame_words(carried.begin() + 20, carried.end());
        const std::vector<int64_t> fresh = range(next, 20);
        next += 20;
        frame_words.insert(frame_words.end(), fresh.begin(), fresh.end());
        fixture.add(i * 3.0, "Warp\x01claude code", frame_words);
        carried = frame_words;
    }
    int32_t count = -1;
    const std::vector<int32_t> groups = fixture.group(&count);
    // The second frame establishes the churn and the third is the first that could ever break;
    // a window at steady state must not produce a moment per frame.
    CHECK(count <= 2);
    CHECK(groups.front() == 0);
}

void test_moment_grouping_is_per_window_not_adjacent() {
    // A person alternating between two windows must not restart both moments on every switch.
    MomentFixture fixture;
    for (int i = 0; i < 4; ++i) {
        fixture.add(i * 6.0, "Arc\x01omi pull request", range(1, 30));
        fixture.add(i * 6.0 + 3.0, "Warp\x01omi main", range(500, 30));
    }
    int32_t count = -1;
    const std::vector<int32_t> groups = fixture.group(&count);
    CHECK(count == 2);
    for (size_t i = 0; i < groups.size(); ++i) {
        CHECK(groups[i] == static_cast<int32_t>(i % 2));
    }
}

void test_moment_distinct_keys_never_merge() {
    MomentFixture fixture;
    fixture.add(0.0, "Arc\x01one", range(1, 10));
    fixture.add(1.0, "Arc\x01two", range(1, 10));
    fixture.add(2.0, "Xcode\x01one", range(1, 10));
    int32_t count = -1;
    const std::vector<int32_t> groups = fixture.group(&count);
    CHECK(count == 3);
    CHECK(groups[0] == 0 && groups[1] == 1 && groups[2] == 2);
}

void test_moment_empty_word_sets_are_not_novelty() {
    // A frame with no OCR at all (title only, or OCR skipped) carries no evidence either way and
    // must never break the moment it lands in.
    MomentFixture fixture;
    fixture.add(0.0, "Arc\x01omi docs", range(1, 30));
    fixture.add(3.0, "Arc\x01omi docs", {});
    fixture.add(6.0, "Arc\x01omi docs", range(1, 30));
    int32_t count = -1;
    const std::vector<int32_t> groups = fixture.group(&count);
    CHECK(count == 1);
    CHECK(groups[0] == 0 && groups[1] == 0 && groups[2] == 0);
}

void test_moment_every_frame_lands_in_exactly_one_group() {
    MomentFixture fixture;
    for (int i = 0; i < 50; ++i) {
        const std::string key = i % 3 == 0 ? "Arc\x01a" : (i % 3 == 1 ? "Warp\x01b" : "Xcode\x01c");
        fixture.add(i * 120.0, key, range(i * 7 + 1, 15));
    }
    int32_t count = -1;
    const std::vector<int32_t> groups = fixture.group(&count);
    CHECK(count > 0);
    CHECK(groups.size() == 50);
    std::vector<int> seen(static_cast<size_t>(count), 0);
    for (size_t i = 0; i < groups.size(); ++i) {
        CHECK(groups[i] >= 0 && groups[i] < count);
        if (groups[i] >= 0 && groups[i] < count) {
            seen[static_cast<size_t>(groups[i])] = 1;
        }
    }
    for (size_t i = 0; i < seen.size(); ++i) {
        CHECK(seen[i] == 1);  // no group is ever opened and left empty
    }
}

void test_moment_rejects_out_of_range_frames() {
    ctx_moment_frame frame;
    frame.at = 0.0;
    frame.key_offset = 0;
    frame.key_length = 8;  // longer than the buffer below
    frame.word_offset = 0;
    frame.word_count = 0;
    const char keys[] = "abc";
    int32_t assignment = -1;
    CHECK(ctx_moment_groups(&frame, 1, keys, 3, nullptr, 0, &assignment) == -1);

    frame.key_length = 3;
    frame.word_count = 4;  // longer than the word pool below
    const int64_t words[] = {1, 2};
    CHECK(ctx_moment_groups(&frame, 1, keys, 3, words, 2, &assignment) == -1);

    frame.word_count = 2;
    CHECK(ctx_moment_groups(&frame, 1, keys, 3, words, 2, nullptr) == -1);
    CHECK(ctx_moment_groups(&frame, 1, keys, 3, words, 2, &assignment) == 1);
}

void test_version_is_reported() {
    const char *version = ctx_core_version();
    CHECK(version != nullptr);
    CHECK(version != nullptr && std::strlen(version) > 0);
}

}  // namespace

int main() {
    test_session_boundaries();
    test_pcm_rms();
    test_pcm_encode_little_endian_and_clamped();
    test_pcm_decode_basic();
    test_pcm_roundtrip_stays_within_one_lsb();
    test_pcm_downmix_averages_channels();
    test_recall_score();
    test_moment_empty_input();
    test_moment_single_frame_is_one_moment();
    test_moment_static_page_stays_one_moment();
    test_moment_gap_opens_a_new_moment();
    test_moment_dominant_novelty_opens_a_new_moment();
    test_moment_first_comparison_never_breaks();
    test_moment_high_churn_window_does_not_shatter();
    test_moment_grouping_is_per_window_not_adjacent();
    test_moment_distinct_keys_never_merge();
    test_moment_empty_word_sets_are_not_novelty();
    test_moment_every_frame_lands_in_exactly_one_group();
    test_moment_rejects_out_of_range_frames();
    test_version_is_reported();

    std::printf("%d checks, %d failures\n", g_checks, g_failures);
    return g_failures == 0 ? 0 : 1;
}
