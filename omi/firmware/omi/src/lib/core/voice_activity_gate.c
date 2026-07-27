#include "voice_activity_gate.h"

#include <stddef.h>

void voice_activity_gate_init(voice_activity_gate_t *gate)
{
    if (!gate) {
        return;
    }

    gate->is_open = false;
    gate->active_streak = 0U;
    gate->last_active_ms = 0;
}

voice_activity_gate_action_t voice_activity_gate_process(voice_activity_gate_t *gate,
                                                         uint32_t average_absolute_amplitude,
                                                         int64_t now_ms,
                                                         uint32_t threshold,
                                                         uint16_t debounce_frames,
                                                         uint32_t hold_ms)
{
    if (!gate || threshold == 0U || debounce_frames == 0U || hold_ms == 0U) {
        return VOICE_ACTIVITY_GATE_BUFFER;
    }

    bool active = average_absolute_amplitude >= threshold;
    if (gate->is_open) {
        if (active) {
            gate->last_active_ms = now_ms;
            return VOICE_ACTIVITY_GATE_FORWARD;
        }

        /*
         * Uptime should be monotonic, but a defensive clamp prevents a clock
         * regression from holding the gate open indefinitely.
         */
        if (now_ms < gate->last_active_ms) {
            gate->last_active_ms = now_ms;
        }
        if ((uint64_t) (now_ms - gate->last_active_ms) < hold_ms) {
            return VOICE_ACTIVITY_GATE_FORWARD;
        }

        gate->is_open = false;
        gate->active_streak = 0U;
        return VOICE_ACTIVITY_GATE_BUFFER;
    }

    if (!active) {
        gate->active_streak = 0U;
        return VOICE_ACTIVITY_GATE_BUFFER;
    }

    if (gate->active_streak < UINT16_MAX) {
        gate->active_streak++;
    }
    gate->last_active_ms = now_ms;
    if (gate->active_streak < debounce_frames) {
        return VOICE_ACTIVITY_GATE_BUFFER;
    }

    gate->is_open = true;
    gate->active_streak = 0U;
    return VOICE_ACTIVITY_GATE_OPEN;
}
