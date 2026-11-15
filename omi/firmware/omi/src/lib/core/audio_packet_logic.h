#ifndef AUDIO_PACKET_LOGIC_H
#define AUDIO_PACKET_LOGIC_H

#include <stddef.h>
#include <stdint.h>

/* ATT notification overhead and Omi's sequence/fragment header are distinct. */
#define AUDIO_ATT_OVERHEAD 3U
#define AUDIO_FRAGMENT_HEADER_BYTES 3U
size_t audio_fragment_payload_size(uint16_t mtu, size_t remaining);

enum audio_pack_result { AUDIO_PACK_INVALID, AUDIO_PACK_BUFFERED, AUDIO_PACK_ENQUEUED, AUDIO_PACK_DROPPED };
/* enqueue must copy the block before returning; return accepted byte count.
 * ENQUEUED means queued, not durable. DROPPED means the emitted block was
 * rejected. Preserve the bounded lossy policy: never retry it here. On overflow
 * the incoming frame remains buffered even if the preceding block was dropped.
 */
typedef size_t (*audio_block_enqueue_fn)(void *ctx, uint8_t *block, size_t length);
enum audio_pack_result audio_pack_frame(uint8_t *block,
                                        size_t capacity,
                                        size_t *offset,
                                        const uint8_t *frame,
                                        size_t length,
                                        audio_block_enqueue_fn enqueue,
                                        void *ctx);
#endif
