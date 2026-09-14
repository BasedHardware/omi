#ifndef TAP_SEQUENCE_H
#define TAP_SEQUENCE_H

#include <stdbool.h>
#include <stdint.h>

#define TAP_SEQUENCE_MAX_PRESS_MS 300
#define TAP_SEQUENCE_GAP_MS 350

enum tap_sequence_event {
    TAP_SEQUENCE_NONE = 0,
    TAP_SEQUENCE_TAP = 1,
    TAP_SEQUENCE_END = 2,
};

struct tap_sequence {
    bool pressed;
    uint32_t press_ms;
    uint32_t release_ms;
    uint8_t count;
};

static inline enum tap_sequence_event
tap_sequence_update(struct tap_sequence *seq, bool pressed, uint32_t now_ms, uint8_t *count)
{
    if (pressed && !seq->pressed) {
        seq->pressed = true;
        seq->press_ms = now_ms;
        return TAP_SEQUENCE_NONE;
    }

    if (pressed) {
        if (seq->count > 0 && now_ms - seq->press_ms >= TAP_SEQUENCE_MAX_PRESS_MS) {
            *count = seq->count;
            seq->count = 0;
            return TAP_SEQUENCE_END;
        }
        return TAP_SEQUENCE_NONE;
    }

    if (seq->pressed) {
        seq->pressed = false;
        if (now_ms - seq->press_ms < TAP_SEQUENCE_MAX_PRESS_MS) {
            if (seq->count < UINT8_MAX) {
                seq->count++;
            }
            seq->release_ms = now_ms;
            *count = seq->count;
            return TAP_SEQUENCE_TAP;
        }
        return TAP_SEQUENCE_NONE;
    }

    if (seq->count > 0 && now_ms - seq->release_ms > TAP_SEQUENCE_GAP_MS) {
        *count = seq->count;
        seq->count = 0;
        return TAP_SEQUENCE_END;
    }

    return TAP_SEQUENCE_NONE;
}

#endif
