#include <unity.h>

#include <math.h>
#include <stdint.h>

#include "audio_preprocess.h"

static void test_downsample_48k_to_16k_sample_count()
{
    int16_t in[480];
    for (int i = 0; i < 480; i++) {
        in[i] = (int16_t)(i % 200);
    }

    int16_t out[160];
    size_t out_samples = 0;
    bool ok = audio_preprocess_process(in, 480, 100, out, 160, &out_samples);
    TEST_ASSERT_TRUE(ok);
    TEST_ASSERT_EQUAL_UINT32(160, (uint32_t)out_samples);
}

static void test_low_battery_bypasses_denoise()
{
    int16_t in[480];
    for (int i = 0; i < 480; i++) {
        in[i] = (int16_t)((i % 100) - 50);
    }

    int16_t out_low[160];
    size_t out_samples_low = 0;
    bool ok_low = audio_preprocess_process(in, 480, 10, out_low, 160, &out_samples_low);
    TEST_ASSERT_TRUE(ok_low);
    TEST_ASSERT_EQUAL_UINT32(160, (uint32_t)out_samples_low);

    for (int i = 0; i < 160; i++) {
        int32_t s0 = in[i * 3 + 0];
        int32_t s1 = in[i * 3 + 1];
        int32_t s2 = in[i * 3 + 2];
        int16_t ref = (int16_t)((s0 + s1 + s2) / 3);
        TEST_ASSERT_EQUAL_INT16(ref, out_low[i]);
    }
}

static void test_denoise_improves_snr_proxy()
{
    const float freq_hz = 300.0f;
    const float amp = 12000.0f;
    const float noise_amp = 9000.0f;

    int16_t in48[480];
    for (int i = 0; i < 480; i++) {
        const float t = (float)i / 48000.0f;
        float clean = sinf(2.0f * 3.1415926f * freq_hz * t) * amp;
        float noise = sinf(2.0f * 3.1415926f * 1000.0f * t) * noise_amp;
        float v = clean + noise;
        if (v > 32767.0f)
            v = 32767.0f;
        if (v < -32768.0f)
            v = -32768.0f;
        in48[i] = (int16_t)v;
    }

    int16_t out_bypass[160];
    size_t out_bypass_n = 0;
    TEST_ASSERT_TRUE(audio_preprocess_process(in48, 480, 10, out_bypass, 160, &out_bypass_n));
    TEST_ASSERT_EQUAL_UINT32(160, (uint32_t)out_bypass_n);

    int16_t out_dn[160];
    size_t out_dn_n = 0;
    TEST_ASSERT_TRUE(audio_preprocess_process(in48, 480, 100, out_dn, 160, &out_dn_n));
    TEST_ASSERT_EQUAL_UINT32(160, (uint32_t)out_dn_n);

    int16_t clean16[160];
    for (int i = 0; i < 160; i++) {
        const float t = (float)i / 16000.0f;
        float clean = sinf(2.0f * 3.1415926f * freq_hz * t) * amp;
        if (clean > 32767.0f)
            clean = 32767.0f;
        if (clean < -32768.0f)
            clean = -32768.0f;
        clean16[i] = (int16_t)clean;
    }

    double err_b = 0.0;
    double err_d = 0.0;
    for (int i = 0; i < 160; i++) {
        double eb = ((double)(out_bypass[i] - clean16[i])) / 32768.0;
        double ed = ((double)(out_dn[i] - clean16[i])) / 32768.0;
        err_b += eb * eb;
        err_d += ed * ed;
    }

    TEST_ASSERT_TRUE(err_d < err_b * 0.7);
}

void setup()
{
    UNITY_BEGIN();
    test_downsample_48k_to_16k_sample_count();
    test_low_battery_bypasses_denoise();
    test_denoise_improves_snr_proxy();
    UNITY_END();
}

void loop() {}
