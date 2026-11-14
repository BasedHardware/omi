/* Exercise production ADC/SOC/edge paths with explicit host hardware shims. */
#include <host.h>
#include <stdio.h>
bool is_charging;
int test_charge_pin = 1, test_adc_mv = 1230, test_adc_error;
void (*test_adc_hook)(void);
static uint8_t diagnostic_charging;
void omi_diagnostics_set_charging(uint8_t v)
{
    diagnostic_charging = v;
}
#include "../../src/battery.c"

static uint8_t sample(int mv)
{
    uint16_t voltage;
    uint8_t percent;
    test_adc_mv = mv;
    assert(battery_get_millivolt(&voltage) == 0);
    assert(battery_get_percentage(&percent, voltage) == 0);
    return percent;
}
static void edge(int pin)
{
    test_charge_pin = pin;
    assert(battery_charging_state_read() == 0);
}
static void bounce(void)
{
    edge(0);
    edge(1);
}
int main(int argc, char **argv)
{
    (void) argv;
    /* Separate process covers boot on charger with no off-charger history. */
    test_charge_pin = argc > 1 ? 0 : 1;
    assert(battery_init() == 0);
    uint16_t voltage;
    uint8_t percent;
    assert(battery_get_millivolt(&voltage) == -EAGAIN);
    if (argc > 1) {
        uint8_t a = sample(1250), b = sample(1320);
        assert(b > a && !soc_frozen);
        edge(1);
        uint8_t off = sample(1230);
        assert(off < b && !soc_frozen);
        puts("battery charger-boot fallback passed");
        return 0;
    }
    uint8_t off = sample(1230);
    assert(off > 0 && off < 100);
    edge(0);
    assert(sample(1320) == off && soc_frozen);
    assert(sample(1280) == off);
    struct battery_diagnostics diag;
    battery_get_diagnostics(&diag);
    assert(diag.charge_pin == 1 && diag.soc_frozen && diag.charge_edge_count == 1);
    /* Diagnostics keep raw ADC mV; shutdown/curve input keeps correction. */
    assert(diag.millivolts == (uint16_t) (1280 * ((float) 1590 / 499)));
    edge(1);
    uint8_t unplugged = sample(1280);
    assert(unplugged > off && !soc_frozen);
    assert(sample(1300) <= unplugged); /* no rising off-charger SOC */
    test_adc_hook = bounce;
    assert(battery_get_millivolt(&voltage) == -EAGAIN);
    assert(battery_get_percentage(&percent, voltage) == -EAGAIN);
    test_adc_hook = NULL;
    assert(sample(1230) < unplugged);
    assert(battery_get_millivolt(&voltage) == 0);
    edge(0); /* edge after ADC but before percentage also invalidates */
    assert(battery_get_percentage(&percent, voltage) == -EAGAIN);
    test_charge_pin = -EIO;
    assert(battery_charging_state_read() == -EIO && diagnostic_charging == UINT8_MAX);
    assert(battery_get_millivolt(&voltage) == -EAGAIN);
    edge(1);
    test_adc_error = -EIO;
    assert(battery_get_millivolt(&voltage) == -EIO);
    assert(battery_get_percentage(&percent, voltage) == -EAGAIN);
    test_adc_error = 0;
    (void) sample(1230);
    charge_edge_count = UINT16_MAX - 1;
    edge(0);
    edge(1);
    battery_get_diagnostics(&diag);
    assert(diag.charge_edge_count == UINT16_MAX - 1 && diag.charge_pin == 0);
    puts("battery freeze, unplug, bounce, read failure and saturation passed");
    return 0;
}
