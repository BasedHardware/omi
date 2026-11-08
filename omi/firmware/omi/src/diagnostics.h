#ifndef OMI_DIAGNOSTICS_H
#define OMI_DIAGNOSTICS_H

#include <stdint.h>

#define OMI_DIAGNOSTICS_SIZE 25U

struct omi_diagnostics_snapshot {
    uint32_t reset_cause;
    uint32_t uptime_s;
    uint16_t battery_mv;
    uint8_t charging;
    uint32_t mic_overrun_count;
    uint32_t ble_tx_drop_count;
    uint32_t storage_error_count;
};

/* Pure wire encoder: no Zephyr types or host byte-order assumptions. */
void omi_diagnostics_pack(uint8_t out[OMI_DIAGNOSTICS_SIZE], const struct omi_diagnostics_snapshot *snapshot);

void omi_diagnostics_set_reset_cause(uint32_t cause);
void omi_diagnostics_set_battery_mv(uint16_t millivolts);
void omi_diagnostics_set_charging(uint8_t charging);
void omi_diagnostics_inc_mic_overrun(void);
void omi_diagnostics_inc_ble_tx_drop(void);
void omi_diagnostics_inc_storage_error(void);
void omi_diagnostics_snapshot(struct omi_diagnostics_snapshot *snapshot);

#endif
