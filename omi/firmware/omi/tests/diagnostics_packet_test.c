#include <assert.h>
#include <string.h>

#include "diagnostics.h"

int main(void)
{
    const struct omi_diagnostics_snapshot snapshot = {
        .reset_cause = 0x12345678,
        .uptime_s = 0x90ABCDEF,
        .battery_mv = 0x1357,
        .charging = 1,
        .mic_overrun_count = 0x10203040,
        .ble_tx_drop_count = 0x50607080,
        .storage_error_count = 0xA0B0C0D0,
        .conn_interval = 0x1234,
        .conn_latency = 0x5678,
        .conn_timeout = 600,
        .tx_phy = 2,
        .rx_phy = 4,
    };
    const uint8_t expected[OMI_DIAGNOSTICS_SIZE] = {
        1,    0x78, 0x56, 0x34, 0x12, 0xEF, 0xCD, 0xAB, 0x90, 0x57, 0x13, 1,    0,
        0x40, 0x30, 0x20, 0x10, 0x80, 0x70, 0x60, 0x50, 0xD0, 0xC0, 0xB0, 0xA0, 0xff,
        0xff, 0xff, 0xff, 0xff, 0x34, 0x12, 0x78, 0x56, 0x58, 2,    2,    4,
    };
    uint8_t actual[OMI_DIAGNOSTICS_SIZE];
    omi_diagnostics_pack(actual, &snapshot);
    assert(memcmp(actual, expected, sizeof(actual)) == 0);

    const struct omi_diagnostics_snapshot unavailable = {
        .reset_cause = UINT32_MAX,
        .battery_mv = UINT16_MAX,
        .charging = UINT8_MAX,
        .conn_interval = UINT16_MAX,
        .conn_latency = UINT16_MAX,
        .conn_timeout = UINT16_MAX,
        .tx_phy = UINT8_MAX,
        .rx_phy = UINT8_MAX,
    };
    omi_diagnostics_pack(actual, &unavailable);
    assert(actual[0] == 1 && actual[12] == 0);
    assert(actual[1] == 0xFF && actual[4] == 0xFF);
    assert(actual[9] == 0xFF && actual[10] == 0xFF && actual[11] == 0xFF);
    for (unsigned i = 25; i < OMI_DIAGNOSTICS_SIZE; i++) {
        assert(actual[i] == 0xff);
    }
    return 0;
}
