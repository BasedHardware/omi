#ifndef SD_RING_RECOVERY_H
#define SD_RING_RECOVERY_H

#include <stdint.h>

#include "sd_ring_durability.h"

/**
 * Remove a corrupt physical batch from a contiguous logical cursor.
 *
 * A corrupt tail clamps write_seq before the batch. A corrupt head/middle
 * advances read_seq beyond it because the wire protocol cannot represent a
 * hole. dropped_packets includes every record made unreachable.
 *
 * @return 1 when the cursor changed, 0 when the batch did not intersect it,
 *         or a negative errno.
 */
int sd_ring_reconcile_corrupt_batch(sd_ring_cursor_t *cursor, uint64_t batch_start_seq, uint32_t batch_packets);

typedef struct {
    uint64_t affected_start_seq;
    uint64_t replacement_start_seq;
    uint64_t attempted_write_seq;
    uint64_t metadata_generation;
    sd_ring_cursor_t baseline;
    uint32_t batch_packets;
    bool preimage_untouched;
    bool replacement_valid;
} sd_ring_quarantine_recovery_t;

/**
 * Reconcile a rebooted write-ahead quarantine exactly once. The persisted
 * metadata generation distinguishes an unreconciled intent from a prior boot
 * that committed the conservative cursor but could not clear MCU NVS.
 */
int sd_ring_reconcile_quarantine(sd_ring_cursor_t *cursor,
                                 uint64_t current_metadata_generation,
                                 const sd_ring_quarantine_recovery_t *quarantine);

/** A retry may include more RAM tail, but can never regress below persisted intent. */
bool sd_ring_quarantine_retry_allowed(uint64_t persisted_attempted_write_seq, uint64_t candidate_write_seq);

#endif
