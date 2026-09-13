#ifndef OMI_BUTTON_GESTURE_H
#define OMI_BUTTON_GESTURE_H

#include <stdbool.h>
#include <stdint.h>

/*
 * Button gesture recogniser shared by the Omi CV1 (omi/) and DevKit (devkit/)
 * firmware. It is pure C with no RTOS dependency so it can be exercised on the
 * host (see test/button_gesture_test.c). The firmware feeds it the debounced
 * button level on every poll tick together with the current uptime and acts on
 * the returned gesture.
 *
 * Wire mapping (BLE button characteristic 23BA7925-...):
 *   BUTTON_GESTURE_SINGLE_TAP -> 1
 *   BUTTON_GESTURE_DOUBLE_TAP -> 2
 *   BUTTON_GESTURE_RELEASE    -> 5
 *   BUTTON_GESTURE_TRIPLE_TAP -> 6
 *   BUTTON_GESTURE_LONG_PRESS -> not notified; the device powers off.
 */

/* A press shorter than this counts as a tap. */
#define BUTTON_GESTURE_TAP_MAX_MS 300
/* Maximum idle time between taps of the same gesture. A single or double tap is
 * reported once this window elapses without a new press; a triple tap is
 * reported on its third release. */
#define BUTTON_GESTURE_MULTI_TAP_GAP_MS 350
/* Holding the button this long is the (fixed, non-customisable) power-off gesture. */
#define BUTTON_GESTURE_LONG_PRESS_MS 3000
#define BUTTON_GESTURE_MAX_TAPS 3

typedef enum {
    BUTTON_GESTURE_NONE = 0,
    BUTTON_GESTURE_SINGLE_TAP,
    BUTTON_GESTURE_DOUBLE_TAP,
    BUTTON_GESTURE_TRIPLE_TAP,
    BUTTON_GESTURE_LONG_PRESS,
    BUTTON_GESTURE_RELEASE,
} button_gesture_t;

typedef struct {
    bool pressed;
    bool long_press_fired;
    bool release_pending;
    uint8_t tap_count;
    uint32_t press_start_ms;
    uint32_t last_release_ms;
} button_gesture_fsm_t;

void button_gesture_init(button_gesture_fsm_t *fsm);

/* Advance the recogniser by one poll. Returns at most one gesture per call. */
button_gesture_t button_gesture_step(button_gesture_fsm_t *fsm, bool pressed, uint32_t now_ms);

#endif /* OMI_BUTTON_GESTURE_H */
