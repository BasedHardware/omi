#include "audio_packet_logic.h"

#include <string.h>

size_t audio_fragment_payload_size(uint16_t mtu, size_t remaining)
{
    const size_t overhead = AUDIO_ATT_OVERHEAD + AUDIO_FRAGMENT_HEADER_BYTES;
    if (mtu <= overhead) {
        return 0;
    }
    size_t available = (size_t) mtu - overhead;
    return remaining < available ? remaining : available;
}

enum audio_pack_result audio_pack_frame(uint8_t *block,
                                        size_t capacity,
                                        size_t *offset,
                                        const uint8_t *frame,
                                        size_t length,
                                        audio_block_enqueue_fn enqueue,
                                        void *ctx)
{
    if (!block || !offset || !frame || !enqueue || capacity < 2U || length > UINT8_MAX || length > capacity - 2U ||
        *offset >= capacity) {
        return AUDIO_PACK_INVALID;
    }
    size_t packet_size = length + 1U;
    size_t room = capacity - 1U - *offset;
    if (packet_size > room) {
        /* Preserve the legacy boundary marker and next-block layout. */
        block[*offset] = (uint8_t) length;
        size_t accepted = enqueue(ctx, block, capacity);
        block[0] = (uint8_t) length;
        memcpy(block + 1U, frame, length);
        *offset = packet_size;
        return accepted == capacity ? AUDIO_PACK_ENQUEUED : AUDIO_PACK_DROPPED;
    }
    block[*offset] = (uint8_t) length;
    memcpy(block + *offset + 1U, frame, length);
    *offset += packet_size;
    if (packet_size == room) {
        *offset = 0;
        return enqueue(ctx, block, capacity) == capacity ? AUDIO_PACK_ENQUEUED : AUDIO_PACK_DROPPED;
    }
    return AUDIO_PACK_BUFFERED;
}
