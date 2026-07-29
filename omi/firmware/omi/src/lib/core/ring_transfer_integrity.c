#include "ring_transfer_integrity.h"

#include <errno.h>

#include "rtc_time_state.h"

#define RING_NOTIFY_DONE 0x04U
#define CRC32_IEEE_POLYNOMIAL 0xEDB88320U

uint32_t ring_transfer_crc32_update(uint32_t crc, const uint8_t *data, size_t length)
{
    if (!data && length != 0U) {
        return crc;
    }

    crc = ~crc;
    for (size_t i = 0; i < length; i++) {
        crc ^= data[i];
        for (uint8_t bit = 0; bit < 8U; bit++) {
            uint32_t mask = 0U - (crc & 1U);
            crc = (crc >> 1U) ^ (CRC32_IEEE_POLYNOMIAL & mask);
        }
    }
    return ~crc;
}

uint32_t ring_record_timestamp_or_zero(bool rtc_valid, uint32_t utc_time)
{
    return rtc_valid && (uint64_t) utc_time >= RTC_TIME_MIN_VALID_EPOCH_S ? utc_time : 0U;
}

bool ring_storage_flush_retry_due(bool dirty, int64_t now_ms, int64_t next_attempt_ms)
{
    return dirty && now_ms >= next_attempt_ms;
}

bool ring_control_response_should_retain(bool connected, int notify_error)
{
    return connected && (notify_error == -ENOMEM || notify_error == -EAGAIN || notify_error == -EBUSY);
}

bool ring_snapshot_retry_required(bool connection_active, bool commit_succeeded)
{
    return connection_active && !commit_succeeded;
}

bool ring_storage_frame_should_retain(bool storage_terminal)
{
    return !storage_terminal;
}

bool ring_storage_terminal_flush_resolved(bool storage_terminal)
{
    return storage_terminal;
}

bool ring_storage_media_mutation_allowed(bool storage_terminal)
{
    return !storage_terminal;
}

bool ring_power_on_reconcile_required(bool desired_power_on, bool mounted, int last_result)
{
    return desired_power_on && !mounted && last_result < 0;
}

void ring_bulk_link_policy_reset(ring_bulk_link_policy_t *policy)
{
    if (!policy) {
        return;
    }

    policy->bulk_request_attempted = false;
    policy->restore_pending = false;
}

ring_bulk_link_action_t ring_bulk_link_policy_on_read(ring_bulk_link_policy_t *policy)
{
    if (!policy) {
        return RING_BULK_LINK_ACTION_NONE;
    }

    policy->restore_pending = false;
    if (policy->bulk_request_attempted) {
        return RING_BULK_LINK_ACTION_NONE;
    }

    policy->bulk_request_attempted = true;
    return RING_BULK_LINK_ACTION_REQUEST_BULK;
}

void ring_bulk_link_policy_on_idle(ring_bulk_link_policy_t *policy)
{
    if (policy && policy->bulk_request_attempted) {
        policy->restore_pending = true;
    }
}

ring_bulk_link_action_t ring_bulk_link_policy_on_restore_timeout(ring_bulk_link_policy_t *policy)
{
    if (!policy || !policy->restore_pending) {
        return RING_BULK_LINK_ACTION_NONE;
    }

    ring_bulk_link_policy_reset(policy);
    return RING_BULK_LINK_ACTION_REQUEST_NORMAL;
}

ring_bulk_link_action_t ring_bulk_link_policy_on_stop(ring_bulk_link_policy_t *policy)
{
    if (!policy || !policy->bulk_request_attempted) {
        ring_bulk_link_policy_reset(policy);
        return RING_BULK_LINK_ACTION_NONE;
    }

    ring_bulk_link_policy_reset(policy);
    return RING_BULK_LINK_ACTION_REQUEST_NORMAL;
}

static void put_be32(uint32_t value, uint8_t *out)
{
    out[0] = (uint8_t) (value >> 24U);
    out[1] = (uint8_t) (value >> 16U);
    out[2] = (uint8_t) (value >> 8U);
    out[3] = (uint8_t) value;
}

static void put_be64(uint64_t value, uint8_t *out)
{
    put_be32((uint32_t) (value >> 32U), out);
    put_be32((uint32_t) value, out + 4U);
}

size_t ring_transfer_encode_done(uint8_t *out, size_t capacity, uint8_t status, uint64_t next_seq, uint32_t crc)
{
    if (!out || capacity < RING_TRANSFER_DONE_BYTES) {
        return 0U;
    }

    out[0] = RING_NOTIFY_DONE;
    out[1] = status;
    put_be64(next_seq, out + 2U);
    put_be32(crc, out + 10U);
    return RING_TRANSFER_DONE_BYTES;
}
