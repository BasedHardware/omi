/* Classifies observed image identities and bounds counters and NVS checkpoint frequency. */
#include <string.h>

#include "boot_telemetry.h"

uint32_t omi_counter_increment(uint32_t value)
{
    return value == UINT32_MAX ? value : value + 1;
}

enum omi_update_outcome
omi_update_classify(const struct omi_boot_record *previous, const struct omi_image_identity *running, bool header_valid)
{
    if (!(previous->flags & OMI_BOOT_VALID)) {
        return OMI_UPDATE_UNKNOWN;
    }
    if (memcmp(previous->current.fw, running->fw, OMI_BOOT_FW_SIZE)) {
        return OMI_UPDATE_UPDATED;
    }
    if (!header_valid || !(previous->flags & OMI_BOOT_HEADER_VALID)) {
        return OMI_UPDATE_UNKNOWN;
    }
    if (memcmp(previous->current.header_version, running->header_version, 8)) {
        return OMI_UPDATE_UPDATED;
    }
    return previous->upload_pending ? OMI_UPDATE_NOT_INSTALLED : OMI_UPDATE_UNCHANGED;
}

bool omi_boot_save_due(bool dirty, bool attempted, int64_t last_attempt_ms, int64_t now_ms)
{
    return dirty &&
           (!attempted || (now_ms >= last_attempt_ms && now_ms - last_attempt_ms >= OMI_BOOT_SAVE_INTERVAL_MS));
}
