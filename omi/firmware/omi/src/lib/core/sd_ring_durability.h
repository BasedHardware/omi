#ifndef SD_RING_DURABILITY_H
#define SD_RING_DURABILITY_H

#include <stdbool.h>
#include <stdint.h>

typedef struct {
    uint64_t read_seq;
    uint64_t write_seq;
    uint64_t dropped_packets;
    uint32_t capacity_packets;
} sd_ring_cursor_t;

typedef struct {
    sd_ring_cursor_t durable;
    uint64_t unsafe_batch_start_seq;
    bool terminal;
    bool unsafe_batch;
} sd_ring_durability_t;

typedef struct {
    int (*write_payload)(void *context);
    int (*write_header)(void *context);
    int (*persist_metadata)(const sd_ring_cursor_t *candidate, void *context);
    int (*sync_media)(void *context);
} sd_ring_durability_ops_t;

typedef struct {
    uint64_t start_seq;
    uint32_t packet_count;
} sd_ring_read_plan_t;

void sd_ring_durability_init(sd_ring_durability_t *state, const sd_ring_cursor_t *mounted);

/**
 * Commit one batch transaction. The durable cursor changes only after the
 * batch, metadata, and optional media sync all succeed.
 */
int sd_ring_durability_commit_batch(sd_ring_durability_t *state,
                                    const sd_ring_cursor_t *candidate,
                                    uint64_t batch_start_seq,
                                    bool sync_requested,
                                    const sd_ring_durability_ops_t *ops,
                                    void *context);

/**
 * Commit a metadata-only transaction (ADVANCE/CLEAR). An unresolved
 * quarantine fences every external metadata mutation before any persistence
 * callback runs. Failure leaves the durable cursor unchanged.
 */
int sd_ring_durability_commit_metadata(sd_ring_durability_t *state,
                                       const sd_ring_cursor_t *candidate,
                                       bool quarantine_active,
                                       bool sync_requested,
                                       const sd_ring_durability_ops_t *ops,
                                       void *context);

void sd_ring_durability_enter_terminal(sd_ring_durability_t *state);
uint64_t sd_ring_durability_unsafe_packets(const sd_ring_durability_t *state);
sd_ring_cursor_t sd_ring_durability_info(const sd_ring_durability_t *state);

/**
 * Bound a read strictly to the last-known-durable cursor. This function never
 * invokes persistence callbacks and therefore cannot expose a dirty RAM tail.
 */
int sd_ring_durability_plan_read(const sd_ring_durability_t *state,
                                 uint64_t start_seq,
                                 uint32_t max_packets,
                                 sd_ring_read_plan_t *plan);

#endif
