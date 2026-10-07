#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>

#include "connected_retention.h"

static unsigned writes, notifications;
static bool durable_write, fail_write, fail_notify;
static int writer(void *context, bool durable)
{
    (void) context;
    ++writes;
    durable_write = durable;
    return fail_write ? -EIO : 0;
}
static int notify(void *context)
{
    (void) context;
    ++notifications;
    return fail_notify ? -EAGAIN : 0;
}
int main(void)
{
    for (unsigned state = 0; state < 64; ++state) {
        /* Charging is orthogonal to transport ownership; it never disables
         * the durable destination. Its AAD rules are tested in test_mic.c. */
        struct cq_inputs in = {.enabled = (state & 1) != 0,
                               .connected = (state & 2) != 0,
                               .subscribed = (state & 4) != 0,
                               .live = (state & 8) != 0,
                               .quiet = (state & 16) != 0};
        writes = notifications = 0;
        fail_write = fail_notify = false;
        assert(cq_route(&in, writer, notify, NULL) == 0);
        bool durable = in.enabled && in.connected && (in.live || in.quiet);
        assert(writes == (unsigned) (durable || !in.connected || !in.subscribed));
        if (writes)
            assert(durable_write == durable);
        assert(notifications == (unsigned) (in.connected && in.subscribed && !in.quiet));
    }
    struct cq_inputs live = {.enabled = true, .connected = true, .subscribed = true, .live = true};
    writes = notifications = 0;
    fail_write = true;
    assert(cq_route(&live, writer, notify, NULL) == -EIO);
    assert(writes == 1 && notifications == 0); /* durable before BLE */
    fail_write = false;
    fail_notify = true;
    assert(cq_route(&live, writer, notify, NULL) == 0); /* SD survives stalled central */
    live.live = false;
    writes = notifications = 0;
    assert(cq_route(&live, writer, notify, NULL) == 0);
    assert(writes == 1 && !durable_write); /* Batch send race -> existing SD writer */
    assert(cq_capability(false, false) == 0);
    assert(cq_capability(false, true) == 0);
    assert(cq_capability(true, false) == 0);
    assert(cq_capability(true, true) == 1);

    uint8_t payload[CQ_PAYLOAD_BYTES], audio[160];
    memset(audio, 33, sizeof(audio));
    struct cq_frame frame = {.sequence = UINT64_C(100000),
                             .captured_ms = 1800000123456ULL,
                             .boot_id = 777,
                             .first_fragment = 65535,
                             .fragments = 2,
                             .flags = 1},
                    decoded;
    assert(cq_pack(payload, audio, sizeof(audio), &frame) == 0);
    assert(cq_unpack(payload, &decoded));
    assert(decoded.sequence == frame.sequence && decoded.captured_ms == frame.captured_ms);
    assert(decoded.boot_id == 777 && decoded.first_fragment == 65535 && decoded.fragments == 2 && decoded.flags == 1);
    /* Match the existing Dart Opus decoder's boundary rule. It sees exactly
     * one frame; CQ01 is padding, never a second fake Opus packet. */
    unsigned frames = 0;
    for (size_t i = 0; i < CQ_PAYLOAD_BYTES - 1;) {
        unsigned size = payload[i];
        if (size == 0) {
            ++i;
            continue;
        }
        if (i + 1 + size >= CQ_PAYLOAD_BYTES)
            break;
        assert(size == sizeof(audio) && memcmp(payload + i + 1, audio, size) == 0);
        ++frames;
        i += size + 1;
    }
    assert(frames == 1);
    assert(cq_pack(payload, audio, 0, &frame) == -EINVAL);
    assert(cq_pack(payload, audio, 161, &frame) == -EINVAL);
    memset(payload, 0, sizeof(payload));
    assert(!cq_unpack(payload, &decoded));
    puts("Connected retention: 64 routing states, durable ordering/fallback, capability truth table and legacy decoder "
         "compatibility passed");
    return 0;
}
