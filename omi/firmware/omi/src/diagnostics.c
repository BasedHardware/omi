#include "diagnostics.h"

#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>

static atomic_t reset_cause = ATOMIC_INIT(-1);
static atomic_t battery_mv = ATOMIC_INIT(UINT16_MAX);
static atomic_t charging = ATOMIC_INIT(UINT8_MAX);
static atomic_t mic_overrun_count;
static atomic_t ble_tx_drop_count;
static atomic_t storage_error_count;

void omi_diagnostics_set_reset_cause(uint32_t cause)
{
    atomic_set(&reset_cause, cause);
}

void omi_diagnostics_set_battery_mv(uint16_t millivolts)
{
    atomic_set(&battery_mv, millivolts);
}

void omi_diagnostics_set_charging(uint8_t value)
{
    atomic_set(&charging, value);
}

void omi_diagnostics_inc_mic_overrun(void)
{
    atomic_inc(&mic_overrun_count);
}

void omi_diagnostics_inc_ble_tx_drop(void)
{
    atomic_inc(&ble_tx_drop_count);
}

void omi_diagnostics_inc_storage_error(void)
{
    atomic_inc(&storage_error_count);
}

void omi_diagnostics_snapshot(struct omi_diagnostics_snapshot *snapshot)
{
    snapshot->reset_cause = (uint32_t) atomic_get(&reset_cause);
    snapshot->uptime_s = (uint32_t) (k_uptime_get() / 1000);
    snapshot->battery_mv = (uint16_t) atomic_get(&battery_mv);
    snapshot->charging = (uint8_t) atomic_get(&charging);
    snapshot->mic_overrun_count = (uint32_t) atomic_get(&mic_overrun_count);
    snapshot->ble_tx_drop_count = (uint32_t) atomic_get(&ble_tx_drop_count);
    snapshot->storage_error_count = (uint32_t) atomic_get(&storage_error_count);
}
