/*
 * Host-side simulation of the button tap FSM (check_button_level) from the Omi and devkit firmware.
 * run.sh extracts the real FSM code from the firmware sources and compiles it against these stubs,
 * so this exercises the shipped logic rather than a copy. No Zephyr / nRF Connect SDK required.
 */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

struct k_work {
    int unused;
};
static struct k_work button_work;
static uint32_t fake_now;
static uint32_t k_uptime_get_32(void) { return fake_now; }
static void k_work_reschedule(struct k_work *w, int ms) { (void) w; (void) ms; }
#define K_MSEC(x) (x)
#define LOG_INF(...)
#define LOG_PRINTK(...)
#define BUTTON_CHECK_INTERVAL 40

static volatile bool was_pressed;
static bool is_off;
static void bt_off(void) {}

static char events[256];
static uint32_t last_event_time;
static void rec(char c) { size_t n = strlen(events); events[n] = c; events[n + 1] = 0; last_event_time = fake_now; }
static void notify_tap(void) { rec('S'); }
static void notify_double_tap(void) { rec('D'); }
static void notify_triple_tap(void) { rec('T'); }
static void notify_unpress(void) { rec('R'); }
static int turnoffs;
static void turnoff_all(void) { turnoffs++; rec('L'); }

#include "fsm_extracted.inc"
}

/* Drive the FSM at the firmware poll rate (40 ms). Script: list of (pressed, duration_ms). */
static void run(const int *script, int n)
{
    for (int i = 0; i < n; i += 2) {
        was_pressed = script[i];
        for (int t = 0; t < script[i + 1]; t += BUTTON_CHECK_INTERVAL) {
            fake_now += BUTTON_CHECK_INTERVAL;
            check_button_level(&button_work);
        }
    }
}

static int failures;
static void expect(const char *name, const int *script, int n, const char *want)
{
    events[0] = 0;
    turnoffs = 0;
    run(script, n);
    /* idle long enough for any pending sequence to resolve */
    int idle[] = {0, 2000};
    run(idle, 2);
    bool ok = strcmp(events, want) == 0;
    printf("%s %-40s got=%-6s want=%s\n", ok ? "PASS" : "FAIL", name, events, want);
    if (!ok)
        failures++;
}

int main(void)
{
    int single[] = {1, 120, 0, 10};
    expect("single tap", single, 4, "S");
    int dbl[] = {1, 120, 0, 200, 1, 120, 0, 10};
    expect("double tap (200ms gap)", dbl, 8, "D");
    int tpl[] = {1, 120, 0, 200, 1, 120, 0, 200, 1, 120, 0, 10};
    expect("triple tap (200ms gaps)", tpl, 12, "T");
    int split[] = {1, 120, 0, 480, 1, 120, 0, 10};
    expect("two taps 480ms apart -> two singles", split, 8, "SS");
    int hold[] = {1, 800, 0, 10};
    expect("800ms hold -> release only", hold, 4, "R");
    int lng[] = {1, 3200, 0, 10};
    expect("3.2s hold -> one power-off, then release", lng, 4, "LR");
    int four[] = {1, 120, 0, 200, 1, 120, 0, 200, 1, 120, 0, 200, 1, 120, 0, 10};
    expect("four taps -> triple then single", four, 16, "TS");

    /* Single-press latency: time from release to SINGLE_TAP notification. */
    events[0] = 0;
    int press[] = {1, 120};
    run(press, 2);
    uint32_t released_at = fake_now;
    int rel[] = {0, 1000};
    run(rel, 2);
    uint32_t latency = last_event_time - released_at;
    printf("INFO single-tap latency after release: %u ms (window %d ms, poll %d ms)\n", latency,
           MULTI_TAP_WINDOW_MS, BUTTON_CHECK_INTERVAL);
    if (latency <= MULTI_TAP_WINDOW_MS || latency > MULTI_TAP_WINDOW_MS + 2 * BUTTON_CHECK_INTERVAL) {
        printf("FAIL latency out of expected range\n");
        failures++;
    }
    return failures ? 1 : 0;
}
