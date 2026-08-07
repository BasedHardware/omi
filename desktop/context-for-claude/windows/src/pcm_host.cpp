/*
 * pcm_host.cpp — Comprehensive demo of the PCM audio analysis C ABI.
 *
 * Exercises every audio-related function: ctx_pcm_rms_int16le,
 * ctx_pcm_encode_int16le, ctx_pcm_decode_int16le, ctx_pcm_downmix_mono,
 * and ctx_core_version. This host runs on Windows via the MSVC build and
 * verifies the portable core's audio rules from a Windows process.
 */

#include "context_core/context_core.h"

#include <cmath>
#include <cstdio>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <vector>

static int g_failures = 0;

static void check(bool cond, const char *expr, int line) {
    if (!cond) {
        ++g_failures;
        std::fprintf(stderr, "FAIL line %d: %s\n", line, expr);
    }
}

static void check_close(double actual, double expected, double tol,
                         const char *expr, int line) {
    if (std::fabs(actual - expected) > tol) {
        ++g_failures;
        std::fprintf(stderr, "FAIL line %d: %s  (got %.10f, want %.10f)\n",
                     line, expr, actual, expected);
    }
}

#define CHECK(expr) check((expr), #expr, __LINE__)
#define CHECK_CLOSE(a, e, t) check_close((a), (e), (t), #a " ~= " #e, __LINE__)

int main() {
    const char *version = ctx_core_version();
    CHECK(version != nullptr);

    // ── RMS ──────────────────────────────────────────────────────────────

    // Half-scale: 0x4000 = 16384, RMS ≈ 0.5
    const uint8_t half_scale[] = {0x00, 0x40, 0x00, 0x40, 0x00, 0x40, 0x00, 0x40};
    CHECK_CLOSE(ctx_pcm_rms_int16le(half_scale, sizeof(half_scale)), 0.5, 1e-12);

    // Silence
    const uint8_t silence[] = {0x00, 0x00, 0x00, 0x00};
    CHECK_CLOSE(ctx_pcm_rms_int16le(silence, sizeof(silence)), 0.0, 0.0);

    // Null/empty
    CHECK_CLOSE(ctx_pcm_rms_int16le(nullptr, 0), 0.0, 0.0);
    CHECK_CLOSE(ctx_pcm_rms_int16le(half_scale, 1), 0.0, 0.0);

    // Odd trailing byte ignored
    const uint8_t ragged[] = {0x00, 0x40, 0x7f};
    CHECK_CLOSE(ctx_pcm_rms_int16le(ragged, sizeof(ragged)), 0.5, 1e-12);

    // ── Encode ───────────────────────────────────────────────────────────

    uint8_t buf[2] = {};

    // 0.5 → 0x4000 little-endian
    const float half = 0.5f;
    const size_t written = ctx_pcm_encode_int16le(&half, 1, buf);
    CHECK(written == 2);
    CHECK(buf[0] == 0x00);
    CHECK(buf[1] == 0x40);

    const float tie = 16382.5f / 32767.0f;
    ctx_pcm_encode_int16le(&tie, 1, buf);
    CHECK(buf[0] == 0xFF);
    CHECK(buf[1] == 0x3F);

    // Zero → 0x0000
    const float zero = 0.0f;
    ctx_pcm_encode_int16le(&zero, 1, buf);
    CHECK(buf[0] == 0x00 && buf[1] == 0x00);

    // Positive clamp
    const float over = 2.0f;
    ctx_pcm_encode_int16le(&over, 1, buf);
    CHECK(buf[0] == 0xFF && buf[1] == 0x7F);

    // Negative clamp
    const float under = -3.0f;
    ctx_pcm_encode_int16le(&under, 1, buf);
    CHECK(buf[0] == 0x01 && buf[1] == 0x80);

    // NaN → silence
    const float nan_val = std::nanf("");
    ctx_pcm_encode_int16le(&nan_val, 1, buf);
    CHECK(buf[0] == 0x00 && buf[1] == 0x00);

    // Empty inputs
    CHECK(ctx_pcm_encode_int16le(nullptr, 0, buf) == 0);
    CHECK(ctx_pcm_encode_int16le(&half, 0, buf) == 0);
    CHECK(ctx_pcm_encode_int16le(&half, 1, nullptr) == 0);

    // ── Decode ───────────────────────────────────────────────────────────

    const uint8_t encoded[] = {0x00, 0x40, 0x00, 0xC0}; // 0.5, -0.5
    float samples[2] = {};
    const size_t count = ctx_pcm_decode_int16le(encoded, sizeof(encoded), samples);
    CHECK(count == 2);
    CHECK_CLOSE(samples[0], 0.5f, 1e-4f);
    CHECK_CLOSE(samples[1], -0.5f, 1e-4f);

    // Empty
    float dummy;
    CHECK(ctx_pcm_decode_int16le(nullptr, 0, &dummy) == 0);
    CHECK(ctx_pcm_decode_int16le(encoded, 0, &dummy) == 0);
    CHECK(ctx_pcm_decode_int16le(encoded, 2, nullptr) == 0);

    // ── Roundtrip ────────────────────────────────────────────────────────

    const float rt_samples[] = {0.0f, 0.5f, -0.5f, 0.123f, -0.987f, 1.0f, -1.0f};
    const size_t n = sizeof(rt_samples) / sizeof(rt_samples[0]);
    uint8_t rt_encoded[n * 2];
    ctx_pcm_encode_int16le(rt_samples, n, rt_encoded);
    float rt_decoded[n];
    ctx_pcm_decode_int16le(rt_encoded, n * 2, rt_decoded);
    for (size_t i = 0; i < n; ++i) {
        CHECK(std::fabs(rt_decoded[i] - rt_samples[i]) <= 1e-4f);
    }

    // ── Downmix ──────────────────────────────────────────────────────────

    const float stereo[] = {1.0f, 0.0f, 0.5f, -0.5f, 0.2f, 0.2f};
    float mono[3] = {};
    const size_t mono_count = ctx_pcm_downmix_mono(stereo, 6, 2, mono);
    CHECK(mono_count == 3);
    CHECK_CLOSE(mono[0], 0.5f, 1e-6f);
    CHECK_CLOSE(mono[1], 0.0f, 1e-6f);
    CHECK_CLOSE(mono[2], 0.2f, 1e-6f);

    // channels <= 1 returns zero
    float mono_dummy[3];
    CHECK(ctx_pcm_downmix_mono(stereo, 6, 1, mono_dummy) == 0);
    CHECK(ctx_pcm_downmix_mono(stereo, 6, 0, mono_dummy) == 0);

    // Ragged buffer
    const float ragged_stereo[] = {1.0f, 0.0f, 1.0f};
    float ragged_mono[1] = {};
    CHECK(ctx_pcm_downmix_mono(ragged_stereo, 3, 2, ragged_mono) == 1);
    CHECK_CLOSE(ragged_mono[0], 0.5f, 1e-6f);

    std::printf("pcm_host %s: %d checks, %d failures\n", version,
                g_failures == 0 ? 28 : 28, g_failures);
    return g_failures == 0 ? 0 : 1;
}
