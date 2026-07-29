#ifndef AUDIO_STORAGE_PACKER_H
#define AUDIO_STORAGE_PACKER_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define AUDIO_STORAGE_RECORD_BYTES 440U

typedef size_t (*audio_storage_writer_t)(const uint8_t *record, size_t length, uint32_t timestamp, void *context);

typedef struct {
    uint8_t record[AUDIO_STORAGE_RECORD_BYTES];
    size_t used;
    uint32_t timestamp;
} audio_storage_packer_t;

typedef enum {
    AUDIO_STORAGE_PACKER_INVALID = -1,
    AUDIO_STORAGE_PACKER_BLOCKED = 0,
    AUDIO_STORAGE_PACKER_ACCEPTED = 1,
} audio_storage_packer_result_t;

typedef enum {
    AUDIO_DELIVERY_DROP = 0,
    AUDIO_DELIVERY_LIVE,
    AUDIO_DELIVERY_STORAGE,
} audio_delivery_route_t;

typedef enum {
    AUDIO_STORAGE_FIRST_DROP = 0,
    AUDIO_STORAGE_FIRST_RETAIN,
    AUDIO_STORAGE_FIRST_STORED,
    AUDIO_STORAGE_FIRST_STORED_AND_LIVE,
    AUDIO_STORAGE_FIRST_LIVE_FALLBACK,
} audio_storage_first_decision_t;

/**
 * Select the authoritative owner for one popped frame. A failed/unavailable
 * live enqueue must fall back to storage whenever storage is available.
 */
audio_delivery_route_t audio_delivery_route(bool live_queued, bool storage_available);

/**
 * Resolve one frame after the storage-first path has attempted local ownership.
 *
 * Temporary storage failure retains the exact frame and never leaks it to the
 * live preview ahead of durable ordering. Terminal storage failure is the only
 * escape hatch: live BLE may then own the frame so simultaneous SD failure does
 * not force avoidable loss.
 */
audio_storage_first_decision_t audio_storage_first_decision(bool storage_accepted,
                                                            bool storage_terminal,
                                                            bool live_available,
                                                            bool live_preview_enabled);

void audio_storage_packer_init(audio_storage_packer_t *packer);

/**
 * Append one encoded audio frame to the current storage record.
 *
 * A full record is retained until writer accepts all 440 bytes. BLOCKED means
 * the new frame was not consumed and may be retried without duplication.
 * ACCEPTED means the frame is owned by the packer, even if its completed
 * record is still waiting for the writer. The record retains the capture
 * timestamp of its first frame across delayed flushes and writer retries.
 */
audio_storage_packer_result_t audio_storage_packer_push(audio_storage_packer_t *packer,
                                                        const uint8_t *frame,
                                                        size_t frame_length,
                                                        uint32_t frame_timestamp,
                                                        audio_storage_writer_t writer,
                                                        void *context);

/**
 * Pad and submit the current partial record. Failed submissions leave the
 * complete record intact for a later retry.
 */
bool audio_storage_packer_flush(audio_storage_packer_t *packer, audio_storage_writer_t writer, void *context);

size_t audio_storage_packer_pending_bytes(const audio_storage_packer_t *packer);

#endif
