#include "button_input.h"

#include <stdint.h>
#include <zephyr/kernel.h>

#define DEBOUNCE_MS 40
#define TAP_MS 300
#define DOUBLE_MS 600
#define LONG_MS 3000
#define EDGE_CAPACITY 32
#define NO_DEADLINE INT64_MAX

struct button_edge {
    int64_t at;
    bool pressed;
};

static struct {
    bool raw_pressed;
    bool pressed;
    bool tap_pending;
    bool release_pending;
    bool long_reported;
    int64_t raw_since;
    int64_t pressed_at;
    int64_t last_tap_at;
    int64_t release_at;
} gesture;

static struct k_spinlock input_lock;
static struct button_edge edges[EDGE_CAPACITY];
static unsigned edge_count;
static bool overflowed;
static bool started;
static int64_t work_at = NO_DEADLINE;
static void (*notify_event)(enum button_input_event);

/* The lock covers edge capture, deadline selection and scheduling. Notifications
 * happen after unlocking: Bluetooth and shutdown may block for a long time. */
static enum button_input_event events[EDGE_CAPACITY * 2 + 2];
static unsigned event_count;

static void emit(enum button_input_event event)
{
    events[event_count++] = event;
}

static int64_t next_deadline(void)
{
    if (gesture.raw_pressed != gesture.pressed) {
        return gesture.raw_since + DEBOUNCE_MS;
    }
    if (gesture.pressed) {
        return gesture.long_reported ? NO_DEADLINE : gesture.pressed_at + LONG_MS;
    }
    return gesture.release_pending ? gesture.release_at : NO_DEADLINE;
}

static void advance(int64_t now)
{
    int64_t deadline;
    while ((deadline = next_deadline()) != NO_DEADLINE && deadline <= now) {
        if (gesture.raw_pressed != gesture.pressed) {
            gesture.pressed = gesture.raw_pressed;
            if (gesture.pressed) {
                gesture.pressed_at = gesture.raw_since;
                gesture.long_reported = false;
            } else {
                int64_t duration = gesture.raw_since - gesture.pressed_at;
                gesture.release_pending = true;
                gesture.release_at = gesture.pressed_at + TAP_MS;
                if (duration < TAP_MS) {
                    if (gesture.tap_pending && gesture.raw_since - gesture.last_tap_at < DOUBLE_MS) {
                        emit(BUTTON_INPUT_DOUBLE);
                        gesture.tap_pending = false;
                    } else {
                        gesture.tap_pending = true;
                        gesture.last_tap_at = gesture.raw_since;
                    }
                } else {
                    gesture.tap_pending = false;
                }
                /* A deadline cannot precede the release becoming stable. */
                if (gesture.release_at < deadline) {
                    gesture.release_at = deadline;
                }
            }
        } else if (gesture.pressed) {
            emit(BUTTON_INPUT_LONG);
            gesture.long_reported = true;
        } else if (gesture.tap_pending) {
            emit(BUTTON_INPUT_SINGLE);
            gesture.tap_pending = false;
            gesture.release_at = deadline + DEBOUNCE_MS;
        } else {
            emit(BUTTON_INPUT_RELEASE);
            gesture.release_pending = false;
        }
    }
}

static void reset_gesture(bool pressed, int64_t now)
{
    gesture = (typeof(gesture)) {.raw_pressed = pressed, .raw_since = now};
}

static void process_input(struct k_work *work);
K_WORK_DELAYABLE_DEFINE(input_work, process_input);

static void process_input(struct k_work *work)
{
    ARG_UNUSED(work);
    k_spinlock_key_t key = k_spin_lock(&input_lock);
    work_at = NO_DEADLINE;
    event_count = 0;
    if (overflowed) {
        /* Excessive bounce must not turn a dropped release into a power-off.
         * Restart from the latest physical level, without inventing a tap. */
        reset_gesture(edges[edge_count - 1].pressed, edges[edge_count - 1].at);
        overflowed = false;
    } else {
        for (unsigned i = 0; i < edge_count; ++i) {
            advance(edges[i].at);
            if (gesture.raw_pressed != edges[i].pressed) {
                gesture.raw_pressed = edges[i].pressed;
                gesture.raw_since = edges[i].at;
            }
        }
    }
    edge_count = 0;
    int64_t now = k_uptime_get();
    advance(now);
    int64_t deadline = next_deadline();
    if (deadline != NO_DEADLINE) {
        work_at = deadline;
        k_work_reschedule(&input_work, K_MSEC(deadline - now));
    }
    k_spin_unlock(&input_lock, key);

    for (unsigned i = 0; i < event_count; ++i) {
        notify_event(events[i]);
    }
}

void button_input_start(void (*notify)(enum button_input_event), int (*read_level)(void))
{
    k_spinlock_key_t key = k_spin_lock(&input_lock);
    if (!started) {
        notify_event = notify;
        started = true;
        /* Sample under the same lock as ISR capture: an edge between an initial
         * GPIO read and enabling capture must not strand a stale held level. */
        bool pressed = read_level() == 1;
        reset_gesture(pressed, k_uptime_get());
        if (pressed) {
            work_at = k_uptime_get() + DEBOUNCE_MS;
            k_work_reschedule(&input_work, K_MSEC(DEBOUNCE_MS));
        }
    }
    k_spin_unlock(&input_lock, key);
}

void button_input_edge(bool pressed)
{
    k_spinlock_key_t key = k_spin_lock(&input_lock);
    if (started) {
        if (edge_count == EDGE_CAPACITY) {
            overflowed = true;
            --edge_count;
        }
        int64_t now = k_uptime_get();
        edges[edge_count++] = (struct button_edge) {.at = now, .pressed = pressed};
        /* Bring a distant hold deadline forward for a release, but preserve an
         * earlier deadline and bound wakeups during bouncing edges. */
        if (now + DEBOUNCE_MS < work_at) {
            work_at = now + DEBOUNCE_MS;
            k_work_reschedule(&input_work, K_MSEC(DEBOUNCE_MS));
        }
    }
    k_spin_unlock(&input_lock, key);
}
