#include "button_gesture.h"

void button_gesture_init(button_gesture_fsm_t *fsm)
{
    fsm->pressed = false;
    fsm->long_press_fired = false;
    fsm->release_pending = false;
    fsm->tap_count = 0;
    fsm->press_start_ms = 0;
    fsm->last_release_ms = 0;
}

static button_gesture_t gesture_for_taps(uint8_t taps)
{
    switch (taps) {
    case 1:
        return BUTTON_GESTURE_SINGLE_TAP;
    case 2:
        return BUTTON_GESTURE_DOUBLE_TAP;
    default:
        return BUTTON_GESTURE_TRIPLE_TAP;
    }
}

button_gesture_t button_gesture_step(button_gesture_fsm_t *fsm, bool pressed, uint32_t now_ms)
{
    if (pressed && !fsm->pressed) {
        /* Press edge. */
        fsm->pressed = true;
        fsm->press_start_ms = now_ms;
        fsm->long_press_fired = false;
        return BUTTON_GESTURE_NONE;
    }

    if (pressed) {
        /* Held. Long press is a one-shot: fire once and swallow any taps that led up to it. */
        if (!fsm->long_press_fired && (now_ms - fsm->press_start_ms) >= BUTTON_GESTURE_LONG_PRESS_MS) {
            fsm->long_press_fired = true;
            fsm->tap_count = 0;
            fsm->release_pending = false;
            return BUTTON_GESTURE_LONG_PRESS;
        }
        return BUTTON_GESTURE_NONE;
    }

    if (fsm->pressed) {
        /* Release edge. */
        fsm->pressed = false;
        if (fsm->long_press_fired) {
            /* The long press already fired (device is powering off); nothing to report. */
            fsm->long_press_fired = false;
            return BUTTON_GESTURE_NONE;
        }

        uint32_t held_ms = now_ms - fsm->press_start_ms;
        if (held_ms < BUTTON_GESTURE_TAP_MAX_MS) {
            fsm->tap_count++;
            fsm->last_release_ms = now_ms;
            if (fsm->tap_count >= BUTTON_GESTURE_MAX_TAPS) {
                fsm->tap_count = 0;
                fsm->release_pending = true;
                return BUTTON_GESTURE_TRIPLE_TAP;
            }
            return BUTTON_GESTURE_NONE;
        }

        /* Held longer than a tap but released before the long-press threshold:
         * report a plain release and drop any taps that preceded it. */
        fsm->tap_count = 0;
        fsm->release_pending = false;
        return BUTTON_GESTURE_RELEASE;
    }

    /* Idle. */
    if (fsm->tap_count > 0 && (now_ms - fsm->last_release_ms) >= BUTTON_GESTURE_MULTI_TAP_GAP_MS) {
        button_gesture_t gesture = gesture_for_taps(fsm->tap_count);
        fsm->tap_count = 0;
        fsm->release_pending = true;
        return gesture;
    }

    if (fsm->release_pending) {
        /* Trailing release after a tap gesture keeps the wire sequence (gesture, then 5)
         * that clients have always observed. */
        fsm->release_pending = false;
        return BUTTON_GESTURE_RELEASE;
    }

    return BUTTON_GESTURE_NONE;
}
