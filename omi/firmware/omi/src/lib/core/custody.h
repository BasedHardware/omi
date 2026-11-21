#ifndef CUSTODY_H
#define CUSTODY_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define OMI_TS_FLAG_UPTIME 0x80000000U /* set: value is uptime seconds, not UTC */
#define OMI_TS_VALUE_MASK 0x7FFFFFFFU
#define OMI_TS_MIN_UTC 1700000000U

#define OMI_CAP_APP_ACK_RECLAIM 0x01U
#define OMI_CAP_LIVE_PERSIST 0x02U
#define OMI_CAP_ADVANCE_IDEMPOTENT 0x04U
#define OMI_CAP_RING_ID 0x08U
#define OMI_CAP_SUPPORTED_MASK 0x0FU
#define OMI_CUSTODY_VERSION 1U

static inline uint32_t omi_record_timestamp(bool rtc_valid, uint32_t utc_s, int64_t uptime_ms)
{
    if (rtc_valid && utc_s >= OMI_TS_MIN_UTC && utc_s <= OMI_TS_VALUE_MASK) {
        return utc_s;
    }

    uint32_t uptime_s = (uint32_t) ((uptime_ms > 0 ? uptime_ms : 0) / 1000);
    return OMI_TS_FLAG_UPTIME | (uptime_s & OMI_TS_VALUE_MASK);
}

typedef struct {
    uint8_t *buf;
    uint16_t capacity;
    uint16_t offset;
    uint32_t record_session;
    uint16_t record_boundary;
    bool invalidate_next;
} omi_live_pack_t;

void omi_live_pack_init(omi_live_pack_t *p, uint8_t *buf, uint16_t capacity);

bool omi_live_pack_frame(omi_live_pack_t *p,
                         const uint8_t *frame,
                         uint16_t frame_size,
                         uint32_t session,
                         uint16_t frame_end_index,
                         uint8_t *out_record,
                         uint32_t *out_session,
                         uint16_t *out_boundary);

bool omi_live_pack_flush(omi_live_pack_t *p, uint8_t *out_record, uint32_t *out_session, uint16_t *out_boundary);

typedef struct {
    uint64_t floor_seq;
    uint32_t floor_session;
    bool floor_valid;
    uint64_t last_seq;
    uint32_t last_session;
    uint16_t last_index;
    bool last_valid;
} omi_live_mark_t;

void omi_live_mark_reset(omi_live_mark_t *m);

void omi_live_mark_note_record(omi_live_mark_t *m, uint64_t seq, uint32_t session, uint16_t live_index);

bool omi_live_mark_eval(const omi_live_mark_t *m,
                        uint64_t committed_seq,
                        uint64_t read_seq,
                        uint64_t *out_ring_seq,
                        uint16_t *out_live_index,
                        uint32_t *out_session);

int omi_advance_eval(uint64_t cur_read_seq,
                     uint64_t cur_write_seq,
                     uint64_t cur_ring_id,
                     uint64_t req_ring_id,
                     bool check_id,
                     uint64_t new_read_seq);

#endif /* CUSTODY_H */
