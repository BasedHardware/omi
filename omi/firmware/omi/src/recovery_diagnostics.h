#ifndef OMI_RECOVERY_DIAGNOSTICS_H
#define OMI_RECOVERY_DIAGNOSTICS_H

#include <zephyr/sys/byteorder.h>

#include "boot_telemetry.h"
#include "safe_mode.h"

/* Versioned, little-endian wire format; offsets are documented in gatt-map.md. */
#define OMI_RECOVERY_DIAGNOSTICS_SIZE (16 + OMI_BOOT_RECORD_SIZE)
static inline void recovery_diagnostics_snapshot(uint8_t out[OMI_RECOVERY_DIAGNOSTICS_SIZE])
{
    struct safe_mode_snapshot state;
    safe_mode_snapshot_get(&state);
    out[0] = 2;
    out[1] = state.active;
    out[2] = state.latched;
    out[3] = state.bootstate;
    sys_put_le32(state.boot_count, out + 4);
    sys_put_le32(state.reset_reason, out + 8);
    sys_put_le32(state.latch_reason, out + 12);
    struct omi_boot_record boot;
    omi_boot_telemetry_snapshot(&boot);
    omi_boot_record_encode(out + 16, &boot);
}
#endif
