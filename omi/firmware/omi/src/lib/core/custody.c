#include "custody.h"

#include <errno.h>
#include <string.h>

void omi_live_pack_init(omi_live_pack_t *p, uint8_t *buf, uint16_t capacity)
{
    memset(p, 0, sizeof(*p));
    p->buf = buf;
    p->capacity = capacity;
}

static void pack_note_frame(omi_live_pack_t *p, bool first_frame, uint32_t session, uint16_t frame_end_index)
{
    uint32_t effective = p->invalidate_next ? 0U : session;
    p->invalidate_next = false;

    if (first_frame) {
        p->record_session = effective;
    } else if (effective != p->record_session) {
        p->record_session = 0U;
    }

    p->record_boundary = frame_end_index;
}

/* A record always keeps its last byte zero: the app-side parser stops when a
 * frame would reach the record end, so an exactly-full record must still hold
 * a zero terminator at index capacity-1. */
static void pack_emit(const omi_live_pack_t *p, uint8_t *out_record, uint32_t *out_session, uint16_t *out_boundary)
{
    memcpy(out_record, p->buf, p->offset);
    memset(out_record + p->offset, 0, p->capacity - p->offset);
    *out_session = p->record_session;
    *out_boundary = p->record_boundary;
}

bool omi_live_pack_frame(omi_live_pack_t *p,
                         const uint8_t *frame,
                         uint16_t frame_size,
                         uint32_t session,
                         uint16_t frame_end_index,
                         uint8_t *out_record,
                         uint32_t *out_session,
                         uint16_t *out_boundary)
{
    if (!p || !frame || !out_record || !out_session || !out_boundary || frame_size == 0U || frame_size > 0xFFU) {
        return false;
    }

    uint32_t entry = 1U + frame_size;
    uint32_t limit = (uint32_t) p->capacity - 1U;
    if (entry > limit) {
        return false;
    }

    bool produced = false;

    if (p->offset + entry > limit && p->offset > 0U) {
        pack_emit(p, out_record, out_session, out_boundary);
        p->offset = 0;
        p->record_session = 0;
        p->record_boundary = 0;
        produced = true;
    }

    bool first_frame = (p->offset == 0U);
    p->buf[p->offset] = (uint8_t) frame_size;
    memcpy(p->buf + p->offset + 1U, frame, frame_size);
    p->offset += (uint16_t) entry;
    pack_note_frame(p, first_frame, session, frame_end_index);

    if (p->offset == limit && !produced) {
        pack_emit(p, out_record, out_session, out_boundary);
        p->offset = 0;
        p->record_session = 0;
        p->record_boundary = 0;
        produced = true;
    }
    /* If this frame both forced a submit AND exactly completed a second
     * record, only one out_record is available per call: the completed record
     * stays pending in buf and is emitted by the next frame or flush. */

    return produced;
}

bool omi_live_pack_flush(omi_live_pack_t *p, uint8_t *out_record, uint32_t *out_session, uint16_t *out_boundary)
{
    if (!p || !out_record || !out_session || !out_boundary || p->offset == 0U) {
        return false;
    }

    pack_emit(p, out_record, out_session, out_boundary);
    p->offset = 0;
    p->record_session = 0;
    p->record_boundary = 0;
    return true;
}

void omi_live_mark_reset(omi_live_mark_t *m)
{
    memset(m, 0, sizeof(*m));
}

void omi_live_mark_note_record(omi_live_mark_t *m, uint64_t seq, uint32_t session, uint16_t live_index)
{
    if (!m) {
        return;
    }

    if (session == 0U) {
        m->floor_valid = false;
        m->floor_session = 0;
        return;
    }

    if (!m->floor_valid || m->floor_session != session) {
        m->floor_seq = seq;
        m->floor_session = session;
        m->floor_valid = true;
    }

    m->last_seq = seq;
    m->last_session = session;
    m->last_index = live_index;
    m->last_valid = true;
}

bool omi_live_mark_eval(const omi_live_mark_t *m,
                        uint64_t committed_seq,
                        uint64_t read_seq,
                        uint64_t *out_ring_seq,
                        uint16_t *out_live_index,
                        uint32_t *out_session)
{
    if (!m || !out_ring_seq || !out_live_index || !out_session) {
        return false;
    }

    if (!m->floor_valid || !m->last_valid || m->last_session != m->floor_session) {
        return false;
    }

    if (m->last_seq + 1U > committed_seq) {
        return false;
    }

    if (read_seq < m->floor_seq) {
        return false;
    }

    *out_ring_seq = m->last_seq + 1U;
    *out_live_index = m->last_index;
    *out_session = m->last_session;
    return true;
}

int omi_advance_eval(uint64_t cur_read_seq,
                     uint64_t cur_write_seq,
                     uint64_t cur_ring_id,
                     uint64_t req_ring_id,
                     bool check_id,
                     uint64_t new_read_seq)
{
    if (check_id && req_ring_id != cur_ring_id) {
        return -ESTALE;
    }

    if (new_read_seq <= cur_read_seq) {
        return 0;
    }

    if (new_read_seq > cur_write_seq) {
        return -ERANGE;
    }

    return 0;
}
