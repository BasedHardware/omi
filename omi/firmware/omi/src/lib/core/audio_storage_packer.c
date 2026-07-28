#include "audio_storage_packer.h"

#include <string.h>

audio_delivery_route_t audio_delivery_route(bool live_available, bool storage_available)
{
    if (!storage_available) {
        return AUDIO_DELIVERY_DROP;
    }
    return live_available ? AUDIO_DELIVERY_LIVE_AND_STORAGE : AUDIO_DELIVERY_STORAGE;
}

static bool submit_record(audio_storage_packer_t *packer, audio_storage_writer_t writer, void *context)
{
    if (packer->used == 0U) {
        return true;
    }

    if (packer->used < sizeof(packer->record)) {
        memset(packer->record + packer->used, 0, sizeof(packer->record) - packer->used);
    }

    if (writer(packer->record, sizeof(packer->record), context) != sizeof(packer->record)) {
        /*
         * Keep used at the record size after padding. A later push will retry
         * this exact record before consuming another frame.
         */
        packer->used = sizeof(packer->record);
        return false;
    }

    memset(packer->record, 0, sizeof(packer->record));
    packer->used = 0U;
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
