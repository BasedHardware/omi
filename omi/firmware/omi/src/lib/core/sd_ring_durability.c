#include "sd_ring_durability.h"

#include <errno.h>
#include <limits.h>

static bool cursor_valid(const sd_ring_cursor_t *cursor)
{
    if (!cursor || cursor->write_seq < cursor->read_seq) {
        return false;
    }

    return (cursor->write_seq - cursor->read_seq) <= cursor->capacity_packets;
}

void sd_ring_durability_init(sd_ring_durability_t *state, const sd_ring_cursor_t *mounted)
{
    if (!state || !cursor_valid(mounted)) {
        return;
    }

    state->durable = *mounted;
    state->unsafe_batch_start_seq = 0U;
    state->terminal = false;
    state->unsafe_batch = false;
}

static int commit_metadata(sd_ring_durability_t *state,
                           const sd_ring_cursor_t *candidate,
                           bool sync_requested,
                           const sd_ring_durability_ops_t *ops,
                           void *context)
{
    if (!state || !cursor_valid(candidate) || !ops || !ops->persist_metadata || (sync_requested && !ops->sync_media)) {
        return -EINVAL;
    }

    int ret = ops->persist_metadata(candidate, context);
    if (ret < 0) {
        return ret;
    }

    if (sync_requested) {
        ret = ops->sync_media(context);
        if (ret < 0) {
            return ret;
        }
    }

    state->durable = *candidate;
    return 0;
}

int sd_ring_durability_commit_batch(sd_ring_durability_t *state,
                                    const sd_ring_cursor_t *candidate,
                                    uint64_t batch_start_seq,
                                    bool sync_requested,
                                    const sd_ring_durability_ops_t *ops,
                                    void *context)
{
    if (!state || !cursor_valid(candidate) || !ops || !ops->write_payload || !ops->write_header ||
        !ops->persist_metadata || !ops->sync_media || batch_start_seq > candidate->write_seq) {
        return -EINVAL;
    }

    sd_ring_cursor_t previous = state->durable;
    int ret = ops->write_payload(context);
    if (ret == 0) {
        ret = ops->sync_media(context);
    }
    if (ret == 0) {
        ret = ops->write_header(context);
    }
    if (ret == 0) {
        ret = ops->sync_media(context);
    }
    if (ret < 0) {
        /*
         * A failed multi-sector write may have corrupted any previously
         * durable records in the batch. Hide that tail until a complete retry
         * rewrites it, while retaining the original cursor for that retry.
         */
        if (batch_start_seq < previous.write_seq) {
            state->unsafe_batch_start_seq = batch_start_seq;
            state->unsafe_batch = true;
        }

        /*
         * At wrap, the same partial write may also have overwritten the oldest
         * physical slot. That floor cannot safely be advertised even while the
         * candidate tail remains uncommitted.
         */
        if (candidate->read_seq > previous.read_seq) {
            state->durable.read_seq = candidate->read_seq;
            state->durable.dropped_packets = candidate->dropped_packets;
            state->durable.write_seq = previous.write_seq;
        }
        return ret;
    }

    /* A complete rewrite restores any previously unsafe durable tail. */
    state->unsafe_batch = false;
    state->unsafe_batch_start_seq = 0U;

    /*
     * Once a wrapping batch write succeeds, the overwritten sector cannot be
     * advertised even if the following metadata/sync step fails. Move only
     * the safe read floor; never expose the candidate write tail.
     */
    ret = commit_metadata(state, candidate, sync_requested, ops, context);
    if (ret < 0 && candidate->read_seq > previous.read_seq) {
        state->durable.read_seq = candidate->read_seq;
        state->durable.dropped_packets = candidate->dropped_packets;
        state->durable.write_seq = previous.write_seq;
    }
    return ret;
}

int sd_ring_durability_commit_metadata(sd_ring_durability_t *state,
                                       const sd_ring_cursor_t *candidate,
                                       bool quarantine_active,
                                       bool sync_requested,
                                       const sd_ring_durability_ops_t *ops,
                                       void *context)
{
    if (quarantine_active) {
        return -EBUSY;
    }

    return commit_metadata(state, candidate, sync_requested, ops, context);
}

void sd_ring_durability_enter_terminal(sd_ring_durability_t *state)
{
    if (!state) {
        return;
    }

    state->terminal = true;
}

uint64_t sd_ring_durability_unsafe_packets(const sd_ring_durability_t *state)
{
    if (!state || !state->unsafe_batch) {
        return 0U;
    }

    uint64_t safe_write_seq = state->unsafe_batch_start_seq;
    if (safe_write_seq < state->durable.read_seq) {
        safe_write_seq = state->durable.read_seq;
    } else if (safe_write_seq > state->durable.write_seq) {
        safe_write_seq = state->durable.write_seq;
    }
    return state->durable.write_seq - safe_write_seq;
}

sd_ring_cursor_t sd_ring_durability_info(const sd_ring_durability_t *state)
{
    sd_ring_cursor_t info = {0};
    if (!state) {
        return info;
    }

    info = state->durable;
    if (state->unsafe_batch) {
        uint64_t safe_write_seq = state->unsafe_batch_start_seq;
        if (safe_write_seq < info.read_seq) {
            safe_write_seq = info.read_seq;
        } else if (safe_write_seq > info.write_seq) {
            safe_write_seq = info.write_seq;
        }

        uint64_t unsafe_packets = sd_ring_durability_unsafe_packets(state);
        info.write_seq = safe_write_seq;
        if (UINT64_MAX - info.dropped_packets < unsafe_packets) {
            info.dropped_packets = UINT64_MAX;
        } else {
            info.dropped_packets += unsafe_packets;
        }
    }

    return info;
}

int sd_ring_durability_plan_read(const sd_ring_durability_t *state,
                                 uint64_t start_seq,
                                 uint32_t max_packets,
                                 sd_ring_read_plan_t *plan)
{
    if (!state || !plan) {
        return -EINVAL;
    }

    sd_ring_cursor_t readable = sd_ring_durability_info(state);
    if (start_seq < readable.read_seq || start_seq > readable.write_seq) {
        return -ERANGE;
    }

    uint64_t available = readable.write_seq - start_seq;
    plan->start_seq = start_seq;
    plan->packet_count = available < max_packets ? (uint32_t) available : max_packets;
    return 0;
}
