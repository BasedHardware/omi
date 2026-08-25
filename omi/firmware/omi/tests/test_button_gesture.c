#include <stdio.h>
#include <string.h>

#include "../src/lib/core/button_gesture.h"

#define TICK_MS 30

static int failures = 0;

static void check(int condition, const char *what)
{
    if (!condition) {
        printf("FAIL: %s\n", what);
        failures++;
    } else {
        printf("ok: %s\n", what);
    }
}

typedef struct {
    button_gesture_state_t state;
    int64_t uptime_ms;
    bool saw_clear_bonds;
    bool saw_power_off;
    int single_taps;
    int double_taps;
} harness_t;

static void harness_init(harness_t *h)
{
    memset(h, 0, sizeof(*h));
    button_gesture_init(&h->state, TICK_MS);
}

static void run_ticks(harness_t *h, bool pressed, int ticks)
{
    for (int i = 0; i < ticks; i++) {
        button_gesture_result_t r = button_gesture_step(&h->state, pressed, h->uptime_ms);
        h->uptime_ms += TICK_MS;
        if (r.clear_bonds) {
            h->saw_clear_bonds = true;
        }
        if (r.power_off) {
            h->saw_power_off = true;
        }
        if (r.event == BUTTON_GESTURE_SINGLE_TAP) {
            h->single_taps++;
        }
        if (r.event == BUTTON_GESTURE_DOUBLE_TAP) {
            h->double_taps++;
        }
    }
}

static void run_ms(harness_t *h, bool pressed, int ms)
{
    run_ticks(h, pressed, ms / TICK_MS);
}

static void tap(harness_t *h)
{
    run_ms(h, true, 120);
    run_ms(h, false, 120);
}

/*
 * Regression: a single tap followed by a press-and-hold must power the device
 * off, never clear BLE bonds. The first implementation armed the bond clear on
 * the button-down edge of any press that landed inside the double-tap window,
 * so tap-then-hold wiped the bond instead of powering off.
 */
static void test_tap_then_hold_powers_off(void)
{
    harness_t h;
    harness_init(&h);

    tap(&h);
    run_ms(&h, true, 3600);
    run_ms(&h, false, 200);

    check(!h.saw_clear_bonds, "tap-then-hold does not clear bonds");
    check(h.saw_power_off, "tap-then-hold powers off");
}

static void test_double_tap_then_hold_clears_bonds(void)
{
    harness_t h;
    harness_init(&h);

    tap(&h);
    tap(&h);
    check(h.double_taps == 1, "double tap detected");

    run_ms(&h, true, 3600);
    run_ms(&h, false, 200);

    check(h.saw_clear_bonds, "double-tap-then-hold clears bonds");
    check(!h.saw_power_off, "double-tap-then-hold does not power off");
}

static void test_plain_hold_powers_off(void)
{
    harness_t h;
    harness_init(&h);

    run_ms(&h, true, 3600);
    run_ms(&h, false, 200);

    check(h.saw_power_off, "plain hold powers off");
    check(!h.saw_clear_bonds, "plain hold does not clear bonds");
}

static void test_arm_expires_after_window(void)
{
    harness_t h;
    harness_init(&h);

    tap(&h);
    tap(&h);
    check(h.state.unpair_armed, "arm set by double tap");

    run_ms(&h, false, BUTTON_GESTURE_UNPAIR_ARM_WINDOW_MS + 300);
    check(!h.state.unpair_armed, "arm expires after the wall-clock window");

    run_ms(&h, true, 3600);
    run_ms(&h, false, 200);

    check(!h.saw_clear_bonds, "expired arm does not clear bonds");
    check(h.saw_power_off, "expired arm falls back to power off");
}

static void test_single_tap_disarms(void)
{
    harness_t h;
    harness_init(&h);

    tap(&h);
    tap(&h);
    check(h.state.unpair_armed, "arm set by double tap");

    tap(&h);
    run_ms(&h, false, 600);
    check(!h.state.unpair_armed, "a following single tap disarms");

    run_ms(&h, true, 3600);
    run_ms(&h, false, 200);
    check(!h.saw_clear_bonds, "disarmed hold does not clear bonds");
    check(h.saw_power_off, "disarmed hold powers off");
}

static void test_long_press_fires_once(void)
{
    harness_t h;
    harness_init(&h);

    int power_off_edges = 0;
    for (int i = 0; i < 400; i++) {
        button_gesture_result_t r = button_gesture_step(&h.state, true, h.uptime_ms);
        h.uptime_ms += TICK_MS;
        if (r.power_off) {
            power_off_edges++;
        }
    }

    check(power_off_edges == 1, "long press emits power off exactly once while held");
}

int main(void)
{
    test_tap_then_hold_powers_off();
    test_double_tap_then_hold_clears_bonds();
    test_plain_hold_powers_off();
    test_arm_expires_after_window();
    test_single_tap_disarms();
    test_long_press_fires_once();

    if (failures) {
        printf("\n%d check(s) failed\n", failures);
        return 1;
    }
    printf("\nall button gesture checks passed\n");
    return 0;
}
