#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

#include "audio_packet_logic.h"

struct sink {
    size_t calls;
    size_t accepted;
    size_t length;
    uint8_t bytes[440];
};
static size_t enqueue(void *ctx, uint8_t *block, size_t length)
{
    struct sink *s = ctx;
    s->calls++;
    s->length = length;
    memcpy(s->bytes, block, length);
    return s->accepted;
}
/* Literal old packing behavior, used only as a compatibility oracle. */
static void
legacy_pack(uint8_t *block, size_t capacity, size_t *offset, const uint8_t *frame, size_t length, struct sink *sink)
{
    size_t packet = length + 1;
    if (*offset + packet > capacity - 1) {
        block[*offset] = length;
        enqueue(sink, block, capacity);
        *offset = packet;
        block[0] = length;
        memcpy(block + 1, frame, length);
    } else if (*offset + packet == capacity - 1) {
        block[*offset] = length;
        memcpy(block + *offset + 1, frame, length);
        *offset = 0;
        enqueue(sink, block, capacity);
    } else {
        block[*offset] = length;
        memcpy(block + *offset + 1, frame, length);
        *offset += packet;
    }
}
int main(void)
{
    size_t cases = 0;
    const uint16_t mtus[] = {0, 3, 5, 6, 7, 23, 100, 247, 517};
    for (size_t m = 0; m < sizeof(mtus) / sizeof(mtus[0]); m++) {
        for (size_t n = 0; n <= 1024; n++) {
            size_t p = audio_fragment_payload_size(mtus[m], n);
            assert(p <= n);
            if (mtus[m] <= 6)
                assert(p == 0);
            else {
                assert(p + AUDIO_FRAGMENT_HEADER_BYTES <= (size_t) mtus[m] - AUDIO_ATT_OVERHEAD);
                assert(p == (n < (size_t) mtus[m] - 6 ? n : (size_t) mtus[m] - 6));
            }
            cases++;
        }
    }
    /* Full 160-byte codec frame at MTU 100 must split 94 + 66, not 97 + 63. */
    assert(audio_fragment_payload_size(100, 160) == 94);
    assert(audio_fragment_payload_size(100, 66) == 66);
    uint8_t frame[256];
    for (size_t i = 0; i < sizeof(frame); i++)
        frame[i] = (uint8_t) i;
    /* Every reachable byte boundary, codec length, and queue result. Verify
     * exact legacy wire bytes, including its unchanged stale padding behavior. */
    for (size_t off = 0; off < 440; off++) {
        for (size_t n = 0; n <= 160; n++) {
            for (size_t admission = 0; admission < 3; admission++) {
                uint8_t a[440], b[440];
                memset(a, 0xa5, sizeof(a));
                memcpy(b, a, sizeof(a));
                size_t oa = off, ob = off;
                struct sink sa = {.accepted = admission == 0 ? 0 : admission == 1 ? 439 : 440};
                struct sink sb = sa;
                enum audio_pack_result r = audio_pack_frame(a, sizeof(a), &oa, frame, n, enqueue, &sa);
                legacy_pack(b, sizeof(b), &ob, frame, n, &sb);
                assert(oa == ob && memcmp(a, b, sizeof(a)) == 0);
                assert(sa.calls == sb.calls && sa.length == sb.length);
                assert(memcmp(sa.bytes, sb.bytes, sizeof(sa.bytes)) == 0);
                assert(r == (sa.calls ? (sa.accepted == 440 ? AUDIO_PACK_ENQUEUED : AUDIO_PACK_DROPPED)
                                      : AUDIO_PACK_BUFFERED));
                cases++;
            }
        }
    }
    /* Real multi-frame trajectory through repeated full-queue failures. */
    uint8_t block[440] = {0};
    size_t off = 0;
    struct sink sink = {.accepted = 0};
    for (size_t i = 0; i < 1000; i++) {
        enum audio_pack_result r = audio_pack_frame(block, sizeof(block), &off, frame, 160, enqueue, &sink);
        assert(r == AUDIO_PACK_BUFFERED || r == AUDIO_PACK_DROPPED);
        assert(off < sizeof(block));
        cases++;
    }
    size_t calls = sink.calls;
    assert(audio_pack_frame(NULL, 440, &off, frame, 1, enqueue, &sink) == AUDIO_PACK_INVALID);
    assert(audio_pack_frame(block, 440, NULL, frame, 1, enqueue, &sink) == AUDIO_PACK_INVALID);
    assert(audio_pack_frame(block, 440, &off, NULL, 1, enqueue, &sink) == AUDIO_PACK_INVALID);
    assert(audio_pack_frame(block, 440, &off, frame, 1, NULL, &sink) == AUDIO_PACK_INVALID);
    assert(audio_pack_frame(block, 440, &off, frame, 256, enqueue, &sink) == AUDIO_PACK_INVALID);
    assert(audio_pack_frame(block, 1, &off, frame, 1, enqueue, &sink) == AUDIO_PACK_INVALID);
    off = 440;
    assert(audio_pack_frame(block, 440, &off, frame, 1, enqueue, &sink) == AUDIO_PACK_INVALID);
    assert(sink.calls == calls);
    printf("PASS: %zu deterministic MTU/packing cases plus boundary and invalid-input assertions\n", cases);
    return 0;
}
