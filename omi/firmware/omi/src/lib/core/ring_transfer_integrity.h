#ifndef RING_TRANSFER_INTEGRITY_H
#define RING_TRANSFER_INTEGRITY_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define RING_TRANSFER_DONE_BYTES 14U

typedef enum {
    RING_BULK_LINK_ACTION_NONE = 0,
    RING_BULK_LINK_ACTION_REQUEST_BULK,
    RING_BULK_LINK_ACTION_REQUEST_NORMAL,
} ring_bulk_link_action_t;

typedef struct {
    bool bulk_request_attempted;
    bool restore_pending;
} ring_bulk_link_policy_t;

typedef enum {
    RING_ADVANCE_INVALID = 0,
    RING_ADVANCE_IDEMPOTENT,
    RING_ADVANCE_COMMIT,
} ring_advance_action_t;

uint32_t ring_transfer_crc32_update(uint32_t crc, const uint8_t *data, size_t length);

/**
 * Classify an app durable-ACK watermark without mutating ring ownership.
 * Replaying the current watermark is an idempotent success; only a strictly
 * newer in-range watermark may reclaim records.
 */
ring_advance_action_t ring_advance_action(uint64_t read_seq, uint64_t write_seq, uint64_t requested_seq);

/**
 * Invalid/unsynchronized RTC values are represented as timestamp zero. Audio
 * remains durable and the app may place it using its fallback timeline.
 */
uint32_t ring_record_timestamp_or_zero(bool rtc_valid, uint32_t utc_time);

/**
 * Return true when a retained dirty SD batch is due for an autonomous worker
 * retry. A failed attempt keeps dirty=true and supplies a later deadline.
 */
bool ring_storage_flush_retry_due(bool dirty, int64_t now_ms, int64_t next_attempt_ms);

/**
 * Control responses remain owned while the link is connected and notification
 * enqueue is temporarily unavailable.
 */
bool ring_control_response_should_retain(bool connected, int notify_error);

bool ring_snapshot_retry_required(bool connection_active, bool commit_succeeded);

/**
 * A failed power-on enqueue/remount remains pending until either the card is
 * mounted or a newer desired-power-off intent supersedes it.
 */
bool ring_power_on_reconcile_required(bool desired_power_on, bool mounted, int last_result);

/**
 * Keep the faster connection preference across adjacent ring reads. A finished
 * range merely arms an idle restore; the next read cancels it without issuing
 * another parameter request.
 */
void ring_bulk_link_policy_reset(ring_bulk_link_policy_t *policy);
ring_bulk_link_action_t ring_bulk_link_policy_on_read(ring_bulk_link_policy_t *policy);
void ring_bulk_link_policy_on_idle(ring_bulk_link_policy_t *policy);
ring_bulk_link_action_t ring_bulk_link_policy_on_restore_timeout(ring_bulk_link_policy_t *policy);
ring_bulk_link_action_t ring_bulk_link_policy_on_stop(ring_bulk_link_policy_t *policy);

/**
 * Encode [DONE opcode][status][next sequence, BE][DATA CRC32, BE].
 */
size_t ring_transfer_encode_done(uint8_t *out, size_t capacity, uint8_t status, uint64_t next_seq, uint32_t crc);

#endif
