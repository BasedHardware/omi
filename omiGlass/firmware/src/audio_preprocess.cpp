#include "audio_preprocess.h"

#include <math.h>

#include "config.h"

#ifndef CONFIG_AUDIO_DENOISE_RNNOISE
#define CONFIG_AUDIO_DENOISE_RNNOISE 0
#endif

#if CONFIG_AUDIO_DENOISE_RNNOISE
#include <rnnoise.h>
#endif

static inline int16_t clamp_i16(int32_t v)
{
    if (v > 32767)
        return 32767;
    if (v < -32768)
        return -32768;
    return (int16_t)v;
}

bool audio_preprocess_process(
    const int16_t* in,
    size_t in_samples,
    int battery_percent,
    int16_t* out,
    size_t out_capacity_samples,
    size_t* out_samples)
{
    if (out_samples == nullptr || in == nullptr || out == nullptr) {
        return false;
    }
    *out_samples = 0;

    if (in_samples == 0) {
        return true;
    }

    if ((in_samples % 3u) != 0u) {
        return false;
    }

    const size_t needed = in_samples / 3u;
    if (needed > out_capacity_samples) {
        return false;
    }

#if CONFIG_AUDIO_DENOISE_RNNOISE
    const bool enable_denoise = battery_percent >= 20;
    if (enable_denoise) {
        const int frame = rnnoise_get_frame_size();
        if (frame <= 0 || (in_samples % (size_t)frame) != 0u) {
            return false;
        }

        static bool rnnoise_ready = false;
        static bool rnnoise_failed = false;
        static unsigned char state_buf[22000];
        static DenoiseState* st = nullptr;

        if (!rnnoise_ready && !rnnoise_failed) {
            if (rnnoise_get_size() > (int)sizeof(state_buf)) {
                rnnoise_failed = true;
            } else {
                st = (DenoiseState*)state_buf;
                if (rnnoise_init(st, nullptr) != 0) {
                    rnnoise_failed = true;
                } else {
                    rnnoise_ready = true;
                }
            }
        }

        if (rnnoise_ready) {
            float fin[480];
            float fout[480];

            size_t write_pos = 0;
            for (size_t off = 0; off < in_samples; off += (size_t)frame) {
                for (int i = 0; i < frame; i++) {
                    fin[i] = (float)in[off + (size_t)i] / 32768.0f;
                }

                rnnoise_process_frame(st, fout, fin);

                for (int i = 0; i < frame; i += 3) {
                    float v = (fout[i] + fout[i + 1] + fout[i + 2]) * (1.0f / 3.0f);
                    int32_t s = (int32_t)lrintf(v * 32768.0f);
                    out[write_pos++] = clamp_i16(s);
                }
            }

            *out_samples = needed;
            return true;
        }
    }
#endif

    for (size_t i = 0; i < needed; i++) {
        const int32_t s0 = in[i * 3u + 0u];
        const int32_t s1 = in[i * 3u + 1u];
        const int32_t s2 = in[i * 3u + 2u];
        out[i] = clamp_i16((s0 + s1 + s2) / 3);
    }

    *out_samples = needed;
    return true;
}
