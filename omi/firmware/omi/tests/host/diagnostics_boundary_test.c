#include <assert.h>
#include <stdint.h>
#include <string.h>

#include "diagnostics.h"
int64_t test_uptime;
static uint32_t rd(const uint8_t *p)
{
    return (uint32_t) p[0] | (uint32_t) p[1] << 8 | (uint32_t) p[2] << 16 | (uint32_t) p[3] << 24;
}
int main(void)
{
    struct omi_diagnostics_snapshot s;
    omi_diagnostics_snapshot(&s);
    assert(s.reset_cause == UINT32_MAX && s.battery_mv == UINT16_MAX && s.charging == UINT8_MAX);
    assert(s.uptime_s == 0 && s.mic_overrun_count == 0 && s.ble_tx_drop_count == 0 && s.storage_error_count == 0);
    test_uptime = 1999;
    omi_diagnostics_set_reset_cause(0x80000000U);
    omi_diagnostics_set_battery_mv(4200);
    omi_diagnostics_set_charging(1);
    omi_diagnostics_inc_mic_overrun();
    omi_diagnostics_inc_ble_tx_drop();
    omi_diagnostics_inc_ble_tx_drop();
    for (unsigned i = 0; i < 255; i++)
        omi_diagnostics_inc_storage_error();
    omi_diagnostics_snapshot(&s);
    assert(s.uptime_s == 1 && s.reset_cause == 0x80000000U && s.battery_mv == 4200 && s.charging == 1);
    assert(s.mic_overrun_count == 1 && s.ble_tx_drop_count == 2 && s.storage_error_count == 255);
    uint8_t buf[27];
    memset(buf, 0xA5, sizeof(buf));
    omi_diagnostics_pack(buf + 1, &s);
    assert(buf[0] == 0xA5 && buf[26] == 0xA5 && rd(buf + 22) == 255);
    uint32_t x = 1;
    for (unsigned i = 0; i < 100000; i++) {
        x = x * 1664525U + 1013904223U;
        s = (struct omi_diagnostics_snapshot){x, ~x, (uint16_t) x, (uint8_t) x, x ^ 0x55555555U, x ^ 0xaaaaaaaaU, x};
        omi_diagnostics_pack(buf + 1, &s);
        assert(buf[1] == 1 && buf[13] == 0 && buf[0] == 0xa5 && buf[26] == 0xa5);
        assert(rd(buf + 2) == s.reset_cause && rd(buf + 6) == s.uptime_s);
        assert(((unsigned) buf[10] | (unsigned) buf[11] << 8) == s.battery_mv && buf[12] == s.charging);
        assert(rd(buf + 14) == s.mic_overrun_count && rd(buf + 18) == s.ble_tx_drop_count &&
               rd(buf + 22) == s.storage_error_count);
    }
    return 0;
}
