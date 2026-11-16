#pragma once
#include <assert.h>
typedef struct {
    int unused;
} OpusEncoder;
typedef int opus_int32;
#define OPUS_OK 0
#define OPUS_APPLICATION_RESTRICTED_LOWDELAY 2051
#define OPUS_SIGNAL_VOICE 3001
#define OPUS_SET_BITRATE(x) 1, x
#define OPUS_SET_VBR(x) 2, x
#define OPUS_SET_VBR_CONSTRAINT(x) 3, x
#define OPUS_SET_COMPLEXITY(x) 4, x
#define OPUS_SET_SIGNAL(x) 5, x
#define OPUS_SET_LSB_DEPTH(x) 6, x
#define OPUS_SET_DTX(x) 7, x
#define OPUS_SET_INBAND_FEC(x) 8, x
#define OPUS_SET_PACKET_LOSS_PERC(x) 9, x
static int required_size, size_calls, init_calls, ctl_calls, init_result, fail_ctl, encode_result;
static inline int opus_encoder_get_size(int c)
{
    assert(c == 1);
    ++size_calls;
    return required_size;
}
static inline int opus_encoder_init(OpusEncoder *e, int rate, int c, int a)
{
    (void) e;
    assert(rate == 16000 && c == 1 && a == 2051);
    ++init_calls;
    return init_result;
}
static inline int opus_encoder_ctl(OpusEncoder *e, int req, ...)
{
    (void) e;
    ++ctl_calls;
    return req == fail_ctl ? -3 : 0;
}
static inline int opus_encode(OpusEncoder *e, const int16_t *pcm, int n, uint8_t *o, int cap)
{
    (void) e;
    (void) pcm;
    (void) o;
    assert(n == 320 && cap == 160);
    return encode_result;
}
