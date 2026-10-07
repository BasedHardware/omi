#include "connected_retention.h"

#include <errno.h>
#include <string.h>

uint8_t cq_capability(bool enabled, bool ready)
{
    return enabled && ready ? OMI_CAP_CONNECTED_RETENTION_V1 : 0;
}

int cq_route(const struct cq_inputs *in, cq_write_fn write, cq_notify_fn notify, void *context)
{
    bool durable = in->enabled && in->connected && (in->live || in->quiet);
    bool stored = false;
    if (durable || !in->connected || !in->subscribed) {
        int err = write(context, durable);
        if (err) {
            return err;
        }
        stored = true;
    }
    if (in->connected && in->subscribed && !in->quiet) {
        int err = notify(context);
        if (err && !stored) {
            /* Includes CCC removal between the snapshot and notification. */
            return write(context, in->enabled && in->live);
        }
    }
    return 0;
}

static void put_be(uint8_t *out, uint64_t value, unsigned bytes)
{
    for (unsigned i = 0; i < bytes; ++i) {
        out[bytes - 1U - i] = (uint8_t) value;
        value >>= 8;
    }
}

static uint64_t get_be(const uint8_t *in, unsigned bytes)
{
    uint64_t value = 0;
    for (unsigned i = 0; i < bytes; ++i) {
        value = (value << 8) | in[i];
    }
    return value;
}

int cq_pack(uint8_t payload[CQ_PAYLOAD_BYTES], const uint8_t *audio, size_t size, const struct cq_frame *frame)
{
    if (!audio || !frame || size == 0 || size > CQ_MAX_FRAME_BYTES || frame->fragments == 0) {
        return -EINVAL;
    }
    memset(payload, 0, CQ_PAYLOAD_BYTES);
    payload[0] = (uint8_t) size;
    memcpy(payload + 1, audio, size);
    /* Existing phone parser walks zero padding then stops at this impossible
     * length. Thus the trailer is invisible to legacy Opus parsing. */
    uint8_t *t = payload + CQ_TRAILER_OFFSET;
    t[0] = 255;
    memcpy(t + 1, "CQ01", 4);
    put_be(t + 5, frame->first_fragment, 2);
    t[7] = frame->fragments;
    put_be(t + 8, frame->sequence, 8);
    put_be(t + 16, frame->captured_ms, 8);
    put_be(t + 24, frame->boot_id, 4);
    t[28] = frame->flags;
    return 0;
}

bool cq_unpack(const uint8_t payload[CQ_PAYLOAD_BYTES], struct cq_frame *frame)
{
    const uint8_t *t = payload + CQ_TRAILER_OFFSET;
    if (t[0] != 255 || memcmp(t + 1, "CQ01", 4) != 0 || t[7] == 0) {
        return false;
    }
    frame->first_fragment = (uint16_t) get_be(t + 5, 2);
    frame->fragments = t[7];
    frame->sequence = get_be(t + 8, 8);
    frame->captured_ms = get_be(t + 16, 8);
    frame->boot_id = (uint32_t) get_be(t + 24, 4);
    frame->flags = t[28];
    return true;
}
