#include <string.h>

#include "boot_telemetry.h"
#include "diagnostics.h"

static void put_u32(uint8_t *out, uint32_t value)
{
    out[0] = (uint8_t) value;
    out[1] = (uint8_t) (value >> 8);
    out[2] = (uint8_t) (value >> 16);
    out[3] = (uint8_t) (value >> 24);
}

void omi_diagnostics_pack(uint8_t out[OMI_DIAGNOSTICS_SIZE], const struct omi_diagnostics_snapshot *snapshot)
{
    out[0] = 1;
    put_u32(out + 1, snapshot->reset_cause);
    put_u32(out + 5, snapshot->uptime_s);
    out[9] = (uint8_t) snapshot->battery_mv;
    out[10] = (uint8_t) (snapshot->battery_mv >> 8);
    out[11] = snapshot->charging;
    out[12] = 0;
    put_u32(out + 13, snapshot->mic_overrun_count);
    put_u32(out + 17, snapshot->ble_tx_drop_count);
    put_u32(out + 21, snapshot->storage_error_count);
}

/* Appended recovery record and settings use the same explicit byte layout. */
#include <string.h>

#include "boot_telemetry.h"

static uint32_t get_u32(const uint8_t *in)
{
    return (uint32_t) in[0] | (uint32_t) in[1] << 8 | (uint32_t) in[2] << 16 | (uint32_t) in[3] << 24;
}

void omi_boot_record_encode(uint8_t out[OMI_BOOT_RECORD_SIZE], const struct omi_boot_record *record)
{
    memset(out, 0, OMI_BOOT_RECORD_SIZE);
    out[0] = 1;
    out[1] = record->flags;
    out[2] = record->outcome;
    out[3] = record->pending_before_boot;
    put_u32(out + 4, record->boot_count);
    put_u32(out + 8, record->reset_reason);
    put_u32(out + 12, record->last_fatal);
    put_u32(out + 16, record->safe_reason);
    put_u32(out + 20, record->nor_read_failures);
    put_u32(out + 24, record->sd_init_failures);
    memcpy(out + 28, record->current.fw, OMI_BOOT_FW_SIZE);
    memcpy(out + 44, record->current.header_version, 8);
    memcpy(out + 52, record->previous.fw, OMI_BOOT_FW_SIZE);
    memcpy(out + 68, record->previous.header_version, 8);
    out[76] = record->upload_pending;
}

bool omi_boot_record_decode(struct omi_boot_record *record, const uint8_t *data, size_t len)
{
    if (len != OMI_BOOT_RECORD_SIZE || data[0] != 1 || !(data[1] & OMI_BOOT_VALID) || (data[1] & ~31U) ||
        data[2] > OMI_UPDATE_NOT_INSTALLED || data[3] > 1 || get_u32(data + 12) > 1 || get_u32(data + 16) > 3 ||
        !memchr(data + 28, 0, OMI_BOOT_FW_SIZE) || !memchr(data + 52, 0, OMI_BOOT_FW_SIZE) || data[76] > 1 ||
        data[77] || data[78] || data[79]) {
        return false;
    }
    *record = (struct omi_boot_record){.flags = data[1],
                                       .outcome = data[2],
                                       .pending_before_boot = data[3],
                                       .boot_count = get_u32(data + 4),
                                       .reset_reason = get_u32(data + 8),
                                       .last_fatal = get_u32(data + 12),
                                       .safe_reason = get_u32(data + 16),
                                       .nor_read_failures = get_u32(data + 20),
                                       .sd_init_failures = get_u32(data + 24),
                                       .upload_pending = data[76]};
    memcpy(record->current.fw, data + 28, OMI_BOOT_FW_SIZE);
    memcpy(record->current.header_version, data + 44, 8);
    memcpy(record->previous.fw, data + 52, OMI_BOOT_FW_SIZE);
    memcpy(record->previous.header_version, data + 68, 8);
    return true;
}
