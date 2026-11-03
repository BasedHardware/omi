#ifndef OMI_RECOVERY_DIAGNOSTICS_H
#define OMI_RECOVERY_DIAGNOSTICS_H

#include <zephyr/sys/byteorder.h>

#include "safe_mode.h"

/* Versioned, little-endian wire format; offsets are documented in gatt-map.md. */
#define OMI_RECOVERY_DIAGNOSTICS_SIZE 16
static inline void recovery_diagnostics_snapshot(uint8_t out[OMI_RECOVERY_DIAGNOSTICS_SIZE])
{
    struct safe_mode_snapshot state;
    safe_mode_snapshot_get(&state);
    out[0] = 1;
    out[1] = state.active;
    out[2] = state.latched;
    out[3] = state.bootstate;
    sys_put_le32(state.boot_count, out + 4);
    sys_put_le32(state.reset_reason, out + 8);
    sys_put_le32(state.latch_reason, out + 12);
}
#endif
