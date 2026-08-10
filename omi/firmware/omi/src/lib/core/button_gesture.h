#ifndef BUTTON_GESTURE_H
#define BUTTON_GESTURE_H

#include <stdbool.h>
#include <stdint.h>

#define BUTTON_GESTURE_TAP_THRESHOLD_MS 300     // 300 ms for single tap
#define BUTTON_GESTURE_DOUBLE_TAP_WINDOW_MS 600 // 600 ms maximum for double-tap
#define BUTTON_GESTURE_LONG_PRESS_MS 3000       // 3000 ms for long press (power off)
#define BUTTON_GESTURE_UNPAIR_ARM_WINDOW_MS 5000

typedef enum {
    BUTTON_GESTURE_NONE = 0,
    BUTTON_GESTURE_SINGLE_TAP,
    BUTTON_GESTURE_DOUBLE_TAP,
    BUTTON_GESTURE_LONG_PRESS,
    BUTTON_GESTURE_RELEASE,
} button_gesture_event_t;

typedef struct {
    uint32_t tick_interval_ms;
    uint32_t current_time;
    uint32_t press_start_time;
    uint32_t release_time;
    uint32_t last_tap_time;
    bool is_pressed;
    bool unpair_armed;
    int64_t unpair_arm_uptime_ms;
    button_gesture_event_t last_event;
} button_gesture_state_t;

typedef struct {
    button_gesture_event_t event;
    bool one_shot;
    bool clear_bonds;
    bool power_off;
} button_gesture_result_t;

static inline void button_gesture_init(button_gesture_state_t *s, uint32_t tick_interval_ms)
{
    const button_gesture_state_t zeroed = {0};
    *s = zeroed;
    s->tick_interval_ms = tick_interval_ms;
}

/*
 * Advances the button gesture state machine by one poll tick.
 *
 * `uptime_ms` is wall-clock milliseconds and is used only for the bond-clear arm
 * window: the tick counter is reset on every release, so it cannot measure a
 * span that crosses releases. Tap and long-press timing stay tick-counted.
 *
 * Bond clear is armed by a completed double-tap and only by a completed
 * double-tap; the long-press that follows within the arm window consumes the arm
 * and clears bonds instead of powering the device off.
 */
static inline button_gesture_result_t button_gesture_step(button_gesture_state_t *s, bool pressed, int64_t uptime_ms)
{
    button_gesture_result_t result = {BUTTON_GESTURE_NONE, false, false, false};
    const uint32_t interval = s->tick_interval_ms;

    s->current_time = s->current_time + 1;

    button_gesture_event_t event = BUTTON_GESTURE_NONE;

    // Debouncing pressed state
    if (pressed && !s->is_pressed) {
        s->is_pressed = true;
        s->press_start_time = s->current_time;
    } else if (!pressed && s->is_pressed) {
        s->is_pressed = false;
        s->release_time = s->current_time;

        // Check for double tap
        uint32_t press_duration = (s->release_time - s->press_start_time) * interval;
        if (press_duration < BUTTON_GESTURE_TAP_THRESHOLD_MS) {
            if (s->last_tap_time > 0 &&
                (s->current_time - s->last_tap_time) * interval < BUTTON_GESTURE_DOUBLE_TAP_WINDOW_MS) {
                event = BUTTON_GESTURE_DOUBLE_TAP;
                s->last_tap_time = 0; // Reset double-tap / single-tap detection
            } else {
                s->last_tap_time = s->current_time;
            }
        }
    }

    if (s->unpair_armed && !s->is_pressed &&
        (uptime_ms - s->unpair_arm_uptime_ms) > BUTTON_GESTURE_UNPAIR_ARM_WINDOW_MS) {
        s->unpair_armed = false;
    }

    // Check for single tap
    if (!pressed && !s->is_pressed) {
        uint32_t press_duration = (s->release_time - s->press_start_time) * interval;
        if (press_duration < BUTTON_GESTURE_TAP_THRESHOLD_MS && s->last_tap_time > 0 &&
            (s->current_time - s->press_start_time) * interval > BUTTON_GESTURE_TAP_THRESHOLD_MS) {
            event = BUTTON_GESTURE_SINGLE_TAP;
            s->last_tap_time = 0;
        } else if ((s->current_time - s->press_start_time) * interval > BUTTON_GESTURE_TAP_THRESHOLD_MS) {
            event = BUTTON_GESTURE_RELEASE;
        }
    }

    // Check for long press
    if (s->is_pressed && (s->current_time - s->press_start_time) * interval >= BUTTON_GESTURE_LONG_PRESS_MS) {
        event = BUTTON_GESTURE_LONG_PRESS;
    }

    result.event = event;

    if (event == BUTTON_GESTURE_SINGLE_TAP) {
        s->last_event = event;
        s->unpair_armed = false;
        result.one_shot = true;
    }

    if (event == BUTTON_GESTURE_DOUBLE_TAP) {
        s->last_event = event;
        s->unpair_armed = true;
        s->unpair_arm_uptime_ms = uptime_ms;
        result.one_shot = true;
    }

    // Long press, one time event
    if (event == BUTTON_GESTURE_LONG_PRESS && s->last_event != BUTTON_GESTURE_LONG_PRESS) {
        s->last_event = event;
        result.one_shot = true;
        if (s->unpair_armed) {
            s->unpair_armed = false;
            result.clear_bonds = true;
        } else {
            result.power_off = true;
        }
    }

    // Releases, one time event
    if (event == BUTTON_GESTURE_RELEASE && s->last_event != BUTTON_GESTURE_RELEASE) {
        s->last_event = event;
        result.one_shot = true;

        // Reset
        s->current_time = 0;
        s->press_start_time = 0;
        s->release_time = 0;
        s->last_tap_time = 0;
    }

    return result;
}

#endif // BUTTON_GESTURE_H
