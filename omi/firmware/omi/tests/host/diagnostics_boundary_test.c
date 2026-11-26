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
    assert(s.conn_interval == UINT16_MAX && s.conn_latency == UINT16_MAX && s.conn_timeout == UINT16_MAX);
    assert(s.tx_phy == UINT8_MAX && s.rx_phy == UINT8_MAX);
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
    uint8_t buf[OMI_DIAGNOSTICS_SIZE + 2];
    memset(buf, 0xA5, sizeof(buf));
    omi_diagnostics_pack(buf + 1, &s);
    assert(buf[0] == 0xA5 && buf[OMI_DIAGNOSTICS_SIZE + 1] == 0xA5 && rd(buf + 22) == 255);
    uint32_t x = 1;
    for (unsigned i = 0; i < 100000; i++) {
        x = x * 1664525U + 1013904223U;
        s = (struct omi_diagnostics_snapshot){.reset_cause = x,
                                              .uptime_s = ~x,
                                              .battery_mv = (uint16_t) x,
                                              .charging = (uint8_t) x,
                                              .mic_overrun_count = x ^ 0x55555555U,
                                              .ble_tx_drop_count = x ^ 0xaaaaaaaaU,
                                              .storage_error_count = x,
                                              .conn_interval = (uint16_t) x,
                                              .conn_latency = (uint16_t) ~x,
                                              .conn_timeout = (uint16_t) (x >> 16),
                                              .tx_phy = (uint8_t) x,
                                              .rx_phy = (uint8_t) ~x};
        omi_diagnostics_pack(buf + 1, &s);
        assert(buf[1] == 1 && buf[13] == 0 && buf[0] == 0xa5 && buf[OMI_DIAGNOSTICS_SIZE + 1] == 0xa5);
        assert(rd(buf + 2) == s.reset_cause && rd(buf + 6) == s.uptime_s);
        assert(((unsigned) buf[10] | (unsigned) buf[11] << 8) == s.battery_mv && buf[12] == s.charging);
        assert(rd(buf + 14) == s.mic_overrun_count && rd(buf + 18) == s.ble_tx_drop_count &&
               rd(buf + 22) == s.storage_error_count);
        assert(((unsigned) buf[31] | (unsigned) buf[32] << 8) == s.conn_interval);
        assert(((unsigned) buf[33] | (unsigned) buf[34] << 8) == s.conn_latency);
        assert(((unsigned) buf[35] | (unsigned) buf[36] << 8) == s.conn_timeout);
        assert(buf[37] == s.tx_phy && buf[38] == s.rx_phy);
    }
    return 0;
}
