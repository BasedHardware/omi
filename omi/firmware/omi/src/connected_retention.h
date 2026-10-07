#ifndef OMI_CONNECTED_RETENTION_H
#define OMI_CONNECTED_RETENTION_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* Separate namespace: features characteristic byte 4, bit 0. */
#define OMI_CAP_CONNECTED_RETENTION_V1 0x01U
#define CQ_PAYLOAD_BYTES 440U
#define CQ_TRAILER_OFFSET 408U
#define CQ_MAX_FRAME_BYTES 160U

struct cq_frame {
    uint64_t sequence;    /* Codec frames, including retained frames; boot scoped. */
    uint64_t captured_ms; /* UTC if valid, otherwise uptime (flags bit 0). */
    uint32_t boot_id;
    uint16_t first_fragment;
    uint8_t fragments;
    uint8_t flags;
};

struct cq_inputs {
    bool enabled;
    bool connected;
    bool subscribed;
    bool live;
    bool quiet;
};

typedef int (*cq_write_fn)(void *context, bool durable);
typedef int (*cq_notify_fn)(void *context);

uint8_t cq_capability(bool enabled, bool ready);
/* Write before notify in live mode: a BLE TX completion is not an app receipt.
 * A failed write is returned to the caller, which must keep/retry this frame.
 * Legacy offline/batch packing is selected with durable=false. */
int cq_route(const struct cq_inputs *in, cq_write_fn write, cq_notify_fn notify, void *context);
int cq_pack(uint8_t payload[CQ_PAYLOAD_BYTES], const uint8_t *audio, size_t size, const struct cq_frame *frame);
bool cq_unpack(const uint8_t payload[CQ_PAYLOAD_BYTES], struct cq_frame *frame);

#endif
