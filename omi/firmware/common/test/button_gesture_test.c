/*
 * Host-side behavioural test for the shared button gesture recogniser.
 * Build and run with ./run.sh (also registered in .github/checks-manifest.yaml).
 */
#include <stdio.h>
#include <stdlib.h>

#include "button_gesture.h"

#define TICK_MS 40

static int failures = 0;
static const char *current_test = "";

#define EXPECT_EQ(actual, expected)                                                                                    \
    do {                                                                                                               \
        int a_ = (int) (actual);                                                                                       \
        int e_ = (int) (expected);                                                                                     \
        if (a_ != e_) {                                                                                                \
            failures++;                                                                                                \
            fprintf(stderr,                                                                                            \
                    "FAIL %s (%s:%d): %s == %d, expected %d\n",                                                        \
                    current_test,                                                                                      \
                    __FILE__,                                                                                          \
                    __LINE__,                                                                                          \
                    #actual,                                                                                           \
                    a_,                                                                                                \
                    e_);                                                                                               \
        }                                                                                                              \
    } while (0)

typedef struct {
    button_gesture_fsm_t fsm;
    uint32_t now_ms;
    button_gesture_t log[16];
    int log_len;
} sim_t;

static void sim_init(sim_t *sim)
{
    button_gesture_init(&sim->fsm);
    sim->now_ms = 10000; /* arbitrary non-zero uptime */
    sim->log_len = 0;
}

static void sim_tick(sim_t *sim, bool pressed)
{
    sim->now_ms += TICK_MS;
    button_gesture_t g = button_gesture_step(&sim->fsm, pressed, sim->now_ms);
    if (g != BUTTON_GESTURE_NONE && sim->log_len < (int) (sizeof(sim->log) / sizeof(sim->log[0]))) {
        sim->log[sim->log_len++] = g;
    }
}

static void sim_hold(sim_t *sim, bool pressed, uint32_t duration_ms)
{
    for (uint32_t t = 0; t < duration_ms; t += TICK_MS) {
        sim_tick(sim, pressed);
    }
}

/* One tap = press for `press_ms`, then release for `gap_ms`. */
static void sim_tap(sim_t *sim, uint32_t press_ms, uint32_t gap_ms)
{
    sim_hold(sim, true, press_ms);
    sim_hold(sim, false, gap_ms);
}

static void settle(sim_t *sim)
{
    sim_hold(sim, false, BUTTON_GESTURE_MULTI_TAP_GAP_MS + 4 * TICK_MS);
}

static void test_single_tap_reports_single_then_release(void)
{
    current_test = __func__;
    sim_t sim;
    sim_init(&sim);

    sim_tap(&sim, 120, 0);
    EXPECT_EQ(sim.log_len, 0); /* nothing until the multi-tap window closes */
    settle(&sim);

    EXPECT_EQ(sim.log_len, 2);
    EXPECT_EQ(sim.log[0], BUTTON_GESTURE_SINGLE_TAP);
    EXPECT_EQ(sim.log[1], BUTTON_GESTURE_RELEASE);
}

static void test_single_tap_latency_is_bounded(void)
{
    current_test = __func__;
    sim_t sim;
    sim_init(&sim);

    sim_hold(&sim, true, 120);
    sim_tick(&sim, false); /* release edge */
    uint32_t released_at = sim.now_ms;
    while (sim.log_len == 0 && sim.now_ms - released_at < 2000) {
        sim_tick(&sim, false);
    }
    EXPECT_EQ(sim.log[0], BUTTON_GESTURE_SINGLE_TAP);
    /* Reported within one tick of the gap window closing. */
    uint32_t latency = sim.now_ms - released_at;
    EXPECT_EQ(latency >= BUTTON_GESTURE_MULTI_TAP_GAP_MS, 1);
    EXPECT_EQ(latency <= BUTTON_GESTURE_MULTI_TAP_GAP_MS + TICK_MS, 1);
}

static void test_double_tap_reports_double_then_release(void)
{
    current_test = __func__;
    sim_t sim;
    sim_init(&sim);

    sim_tap(&sim, 120, 160);
    sim_tap(&sim, 120, 0);
    EXPECT_EQ(sim.log_len, 0);
    settle(&sim);

    EXPECT_EQ(sim.log_len, 2);
    EXPECT_EQ(sim.log[0], BUTTON_GESTURE_DOUBLE_TAP);
    EXPECT_EQ(sim.log[1], BUTTON_GESTURE_RELEASE);
}

static void test_triple_tap_reports_immediately_on_third_release(void)
{
    current_test = __func__;
    sim_t sim;
    sim_init(&sim);

    sim_tap(&sim, 120, 160);
    sim_tap(&sim, 120, 160);
    sim_hold(&sim, true, 120);
    EXPECT_EQ(sim.log_len, 0);
    sim_tick(&sim, false); /* third release */

    EXPECT_EQ(sim.log_len, 1);
    EXPECT_EQ(sim.log[0], BUTTON_GESTURE_TRIPLE_TAP);
    settle(&sim);
    EXPECT_EQ(sim.log_len, 2);
    EXPECT_EQ(sim.log[1], BUTTON_GESTURE_RELEASE);
}

static void test_taps_separated_by_more_than_the_gap_are_two_singles(void)
{
    current_test = __func__;
    sim_t sim;
    sim_init(&sim);

    sim_tap(&sim, 120, BUTTON_GESTURE_MULTI_TAP_GAP_MS + 2 * TICK_MS);
    sim_tap(&sim, 120, 0);
    settle(&sim);

    EXPECT_EQ(sim.log_len, 4);
    EXPECT_EQ(sim.log[0], BUTTON_GESTURE_SINGLE_TAP);
    EXPECT_EQ(sim.log[1], BUTTON_GESTURE_RELEASE);
    EXPECT_EQ(sim.log[2], BUTTON_GESTURE_SINGLE_TAP);
    EXPECT_EQ(sim.log[3], BUTTON_GESTURE_RELEASE);
}

static void test_long_press_fires_once_and_swallows_release(void)
{
    current_test = __func__;
    sim_t sim;
    sim_init(&sim);

    sim_hold(&sim, true, BUTTON_GESTURE_LONG_PRESS_MS + 10 * TICK_MS);
    EXPECT_EQ(sim.log_len, 1);
    EXPECT_EQ(sim.log[0], BUTTON_GESTURE_LONG_PRESS);

    sim_hold(&sim, false, 1000);
    EXPECT_EQ(sim.log_len, 1); /* no tap or release after a long press */
}

static void test_tap_then_long_press_only_reports_long_press(void)
{
    current_test = __func__;
    sim_t sim;
    sim_init(&sim);

    sim_tap(&sim, 120, 160);
    sim_hold(&sim, true, BUTTON_GESTURE_LONG_PRESS_MS + 2 * TICK_MS);
    sim_hold(&sim, false, 1000);

    EXPECT_EQ(sim.log_len, 1);
    EXPECT_EQ(sim.log[0], BUTTON_GESTURE_LONG_PRESS);
}

static void test_medium_hold_is_a_plain_release(void)
{
    current_test = __func__;
    sim_t sim;
    sim_init(&sim);

    sim_hold(&sim, true, 1000);
    sim_hold(&sim, false, 1000);

    EXPECT_EQ(sim.log_len, 1);
    EXPECT_EQ(sim.log[0], BUTTON_GESTURE_RELEASE);
}

static void test_tap_followed_by_medium_hold_drops_the_tap(void)
{
    current_test = __func__;
    sim_t sim;
    sim_init(&sim);

    sim_tap(&sim, 120, 160);
    sim_hold(&sim, true, 1000);
    sim_hold(&sim, false, 1000);

    EXPECT_EQ(sim.log_len, 1);
    EXPECT_EQ(sim.log[0], BUTTON_GESTURE_RELEASE);
}

static void test_uptime_wraparound_does_not_break_timing(void)
{
    current_test = __func__;
    sim_t sim;
    sim_init(&sim);
    sim.now_ms = UINT32_MAX - 100; /* wraps during the multi-tap window */

    sim_tap(&sim, 120, 0);
    settle(&sim);

    EXPECT_EQ(sim.log_len, 2);
    EXPECT_EQ(sim.log[0], BUTTON_GESTURE_SINGLE_TAP);
    EXPECT_EQ(sim.log[1], BUTTON_GESTURE_RELEASE);
}

int main(void)
{
    test_single_tap_reports_single_then_release();
    test_single_tap_latency_is_bounded();
    test_double_tap_reports_double_then_release();
    test_triple_tap_reports_immediately_on_third_release();
    test_taps_separated_by_more_than_the_gap_are_two_singles();
    test_long_press_fires_once_and_swallows_release();
    test_tap_then_long_press_only_reports_long_press();
    test_medium_hold_is_a_plain_release();
    test_tap_followed_by_medium_hold_drops_the_tap();
    test_uptime_wraparound_does_not_break_timing();

    if (failures != 0) {
        fprintf(stderr, "%d failure(s)\n", failures);
        return EXIT_FAILURE;
    }
    printf("button_gesture_test: all tests passed\n");
    return EXIT_SUCCESS;
}
