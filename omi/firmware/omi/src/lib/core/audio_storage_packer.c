#include "audio_storage_packer.h"

#include <string.h>

audio_delivery_route_t audio_delivery_route(bool live_queued, bool storage_available)
{
    if (live_queued) {
        return AUDIO_DELIVERY_LIVE;
    }
    return storage_available ? AUDIO_DELIVERY_STORAGE : AUDIO_DELIVERY_DROP;
}

audio_storage_first_decision_t audio_storage_first_decision(bool storage_accepted,
                                                            bool storage_terminal,
                                                            bool live_available,
                                                            bool live_preview_enabled)
{
    if (storage_accepted) {
        return live_available && live_preview_enabled ? AUDIO_STORAGE_FIRST_STORED_AND_LIVE
                                                      : AUDIO_STORAGE_FIRST_STORED;
    }
    if (!storage_terminal) {
        return AUDIO_STORAGE_FIRST_RETAIN;
    }
    return live_available ? AUDIO_STORAGE_FIRST_LIVE_FALLBACK : AUDIO_STORAGE_FIRST_DROP;
}

static bool submit_record(audio_storage_packer_t *packer, audio_storage_writer_t writer, void *context)
{
    if (packer->used == 0U) {
        return true;
    }

    if (packer->used < sizeof(packer->record)) {
        memset(packer->record + packer->used, 0, sizeof(packer->record) - packer->used);
    }

    if (writer(packer->record, sizeof(packer->record), packer->timestamp, context) != sizeof(packer->record)) {
        /*
         * Keep used at the record size after padding. A later push will retry
         * this exact record before consuming another frame.
         */
        packer->used = sizeof(packer->record);
        return false;
    }

    memset(packer->record, 0, sizeof(packer->record));
    packer->used = 0U;
    packer->timestamp = 0U;
    return true;
}

void audio_storage_packer_init(audio_storage_packer_t *packer)
{
    if (!packer) {
        return;
    }

    memset(packer, 0, sizeof(*packer));
}

audio_storage_packer_result_t audio_storage_packer_push(audio_storage_packer_t *packer,
                                                        const uint8_t *frame,
                                                        size_t frame_length,
                                                        uint32_t frame_timestamp,
                                                        audio_storage_writer_t writer,
                                                        void *context)
{
    if (!packer || !frame || !writer || frame_length == 0U || frame_length > UINT8_MAX ||
        frame_length + 1U > sizeof(packer->record)) {
        return AUDIO_STORAGE_PACKER_INVALID;
    }

    if (packer->used == sizeof(packer->record) && !submit_record(packer, writer, context)) {
        return AUDIO_STORAGE_PACKER_BLOCKED;
    }

    size_t packed_length = frame_length + 1U;
    /*
     * Keep the legacy storage invariant that a frame never exactly consumes
     * the final byte of a record. Existing decoders use the zero-padded tail as
     * the record terminator, so equality starts a new record too.
     */
    if (packer->used + packed_length >= sizeof(packer->record) && !submit_record(packer, writer, context)) {
        return AUDIO_STORAGE_PACKER_BLOCKED;
    }

    if (packer->used == 0U) {
        packer->timestamp = frame_timestamp;
    }
    packer->record[packer->used] = (uint8_t) frame_length;
    memcpy(packer->record + packer->used + 1U, frame, frame_length);
    packer->used += packed_length;

    return AUDIO_STORAGE_PACKER_ACCEPTED;
}

bool audio_storage_packer_flush(audio_storage_packer_t *packer, audio_storage_writer_t writer, void *context)
{
    if (!packer || !writer) {
        return false;
    }

    return submit_record(packer, writer, context);
}

size_t audio_storage_packer_pending_bytes(const audio_storage_packer_t *packer)
{
    return packer ? packer->used : 0U;
}
