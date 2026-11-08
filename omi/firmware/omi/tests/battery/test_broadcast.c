#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

#include "../../src/lib/core/lib/battery/battery.h"
#define BATTERY_REFRESH_INTERVAL_CONNECTED 3000
#define BATTERY_REFRESH_INTERVAL_DISCONNECTED 3000
#define CONFIG_OMI_BATTERY_REFRESH_INTERVAL_CHARGING 1000
#define CONFIG_OMI_BATTERY_CRITICAL_MV 3400
#define LOG_INF(...)
#define LOG_PRINTK(...)
#define LOG_WRN(...)
#define LOG_ERR(...)
#define K_MSEC(n) (n)
struct k_work {
    int unused;
};
static struct k_work battery_work;
static bool is_connected;
static void *current_connection;
static uint8_t battery_percentage, bas;
static uint16_t diagnostic_mv, voltage = 3900;
static int adc_error, notify_count, shutdowns;
static void omi_diagnostics_set_battery_mv(uint16_t mv)
{
    diagnostic_mv = mv;
}
int battery_get_millivolt(uint16_t *mv)
{
    *mv = voltage;
    return adc_error;
}
int battery_get_percentage(uint8_t *percent, uint16_t mv)
{
    (void) mv;
    *percent = 42;
    return 0;
}
void battery_get_diagnostics(struct battery_diagnostics *d)
{
    d->millivolts = 4000;
}
static int bt_bas_set_battery_level(uint8_t percent)
{
    bas = percent;
    return 0;
}
static int notify_charging_status(void *conn, bool force)
{
    (void) conn;
    (void) force;
    notify_count++;
    return 0;
}
static void turnoff_all(void)
{
    shutdowns++;
}
static void k_work_reschedule(struct k_work *w, int delay)
{
    (void) w;
    assert(delay > 0);
}
/* Extracted verbatim by run.sh; not a reimplementation of the production path. */
#include "broadcast.inc"
int main(void)
{
    broadcast_battery_level(NULL);
    assert(bas == 42 && notify_count == 0 && diagnostic_mv == 4000);
    is_connected = true;
    current_connection = &bas;
    broadcast_battery_level(NULL);
    assert(notify_count == 1 && bas == 42);
    voltage = 3300;
    broadcast_battery_level(NULL);
    assert(shutdowns == 1); /* critical shutdown still uses corrected curve voltage */
    adc_error = -1;
    broadcast_battery_level(NULL);
    assert(diagnostic_mv == UINT16_MAX);
    puts("disconnected BAS, raw diagnostics and critical shutdown passed");
}
