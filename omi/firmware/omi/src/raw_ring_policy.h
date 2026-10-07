#ifndef OMI_RAW_RING_POLICY_H
#define OMI_RAW_RING_POLICY_H

#include <stdint.h>

/* Raw slots are overwritten as whole batches. Evict the oldest unread batch
 * before publishing a new tail, then bound the unread window to capacity.
 * Both cursor and cumulative loss count are persisted in the existing WAL. */
static inline void raw_ring_commit_window(uint64_t base,
                                          uint32_t count,
                                          uint32_t batch_packets,
                                          uint32_t capacity,
                                          uint64_t *read,
                                          uint64_t *write,
                                          uint64_t *dropped)
{
    uint64_t end = base + count;
    if (*write <= base && base >= capacity) {
        uint64_t overwritten_end = base - capacity + batch_packets;
        if (*read < overwritten_end) {
            *dropped += overwritten_end - *read;
            *read = overwritten_end;
        }
    }
    if (end - *read > capacity) {
        uint64_t overflow = end - *read - capacity;
        *read += overflow;
        *dropped += overflow;
    }
    *write = end;
}

#endif
