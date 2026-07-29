#ifndef AUDIO_STORAGE_PACKER_H
#define AUDIO_STORAGE_PACKER_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define AUDIO_STORAGE_RECORD_BYTES 440U

typedef size_t (*audio_storage_writer_t)(const uint8_t *record, size_t length, void *context);

typedef struct {
    uint8_t record[AUDIO_STORAGE_RECORD_BYTES];
    size_t used;
} audio_storage_packer_t;

typedef enum {
    AUDIO_STORAGE_PACKER_INVALID = -1,
    AUDIO_STORAGE_PACKER_BLOCKED = 0,
    AUDIO_STORAGE_PACKER_ACCEPTED = 1,
} audio_storage_packer_result_t;

typedef enum {
    AUDIO_DELIVERY_DROP = 0,
    AUDIO_DELIVERY_STORAGE,
    AUDIO_DELIVERY_LIVE_AND_STORAGE,
} audio_delivery_route_t;

/**
 * Select the owners for one popped frame. Storage remains authoritative until
 * the app explicitly advances the durable ring; live delivery is only a
 * best-effort duplicate of a storage-owned frame.
 */
audio_delivery_route_t audio_delivery_route(bool live_available, bool storage_available);

void audio_storage_packer_init(audio_storage_packer_t *packer);

/**
 * Append one encoded audio frame to the current storage record.
 *
 * A full record is retained until writer accepts all 440 bytes. BLOCKED means
 * the new frame was not consumed and may be retried without duplication.
 * ACCEPTED means the frame is owned by the packer, even if its completed
 * record is still waiting for the writer.
 */
audio_storage_packer_result_t audio_storage_packer_push(audio_storage_packer_t *packer,
                                                        const uint8_t *frame,
                                                        size_t frame_length,
                                                        audio_storage_writer_t writer,
                                                        void *context);

/**
 * Pad and submit the current partial record. Failed submissions leave the
 * complete record intact for a later retry.
 */
bool audio_storage_packer_flush(audio_storage_packer_t *packer, audio_storage_writer_t writer, void *context);

size_t audio_storage_packer_pending_bytes(const audio_storage_packer_t *packer);

#endif
