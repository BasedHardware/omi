#include "sd_ring_recovery.h"

#include <errno.h>
#include <limits.h>

static void add_dropped(sd_ring_cursor_t *cursor, uint64_t count)
{
    if (UINT64_MAX - cursor->dropped_packets < count) {
        cursor->dropped_packets = UINT64_MAX;
    } else {
        cursor->dropped_packets += count;
    }
}

int sd_ring_reconcile_corrupt_batch(sd_ring_cursor_t *cursor, uint64_t batch_start_seq, uint32_t batch_packets)
{
    if (!cursor || batch_packets == 0U || cursor->write_seq < cursor->read_seq ||
        UINT64_MAX - batch_start_seq < batch_packets) {
        return -EINVAL;
    }

    uint64_t batch_end_seq = batch_start_seq + batch_packets;
    if (batch_end_seq <= cursor->read_seq || batch_start_seq >= cursor->write_seq) {
        return 0;
    }

    if (batch_end_seq >= cursor->write_seq) {
        uint64_t safe_write_seq = batch_start_seq < cursor->read_seq ? cursor->read_seq : batch_start_seq;
        add_dropped(cursor, cursor->write_seq - safe_write_seq);
        cursor->write_seq = safe_write_seq;
        return 1;
    }

    uint64_t safe_read_seq = batch_end_seq > cursor->read_seq ? batch_end_seq : cursor->read_seq;
    if (safe_read_seq > cursor->write_seq) {
        safe_read_seq = cursor->write_seq;
    }
    add_dropped(cursor, safe_read_seq - cursor->read_seq);
    cursor->read_seq = safe_read_seq;
    return 1;
}

int sd_ring_reconcile_quarantine(sd_ring_cursor_t *cursor,
                                 uint64_t current_metadata_generation,
                                 const sd_ring_quarantine_recovery_t *quarantine)
{
    if (!cursor || !quarantine || quarantine->batch_packets == 0U ||
        current_metadata_generation < quarantine->metadata_generation ||
        quarantine->baseline.write_seq < quarantine->baseline.read_seq) {
        return -EINVAL;
    }

    sd_ring_cursor_t target = quarantine->baseline;
    bool aliases_older_window = quarantine->affected_start_seq != quarantine->replacement_start_seq;
    if (!quarantine->preimage_untouched && (!quarantine->replacement_valid || aliases_older_window)) {
        int ret = sd_ring_reconcile_corrupt_batch(&target, quarantine->affected_start_seq, quarantine->batch_packets);
        if (ret < 0) {
            return ret;
        }
    }

    bool cursor_is_target = cursor->read_seq == target.read_seq && cursor->write_seq == target.write_seq &&
                            cursor->dropped_packets == target.dropped_packets &&
                            cursor->capacity_packets == target.capacity_packets;
    if (current_metadata_generation > quarantine->metadata_generation) {
        if (cursor->write_seq >= quarantine->attempted_write_seq || cursor_is_target) {
            return 0;
        }
        return -EIO;
    }

    bool cursor_is_baseline = cursor->read_seq == quarantine->baseline.read_seq &&
                              cursor->write_seq == quarantine->baseline.write_seq &&
                              cursor->dropped_packets == quarantine->baseline.dropped_packets &&
                              cursor->capacity_packets == quarantine->baseline.capacity_packets;
    if (!cursor_is_baseline) {
        return -EIO;
    }

    *cursor = target;
    return cursor_is_target ? 0 : 1;
}

bool sd_ring_quarantine_retry_allowed(uint64_t persisted_attempted_write_seq, uint64_t candidate_write_seq)
{
    return candidate_write_seq >= persisted_attempted_write_seq;
}
