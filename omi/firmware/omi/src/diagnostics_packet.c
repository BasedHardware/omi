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
