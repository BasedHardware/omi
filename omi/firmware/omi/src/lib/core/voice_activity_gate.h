#ifndef VOICE_ACTIVITY_GATE_H
#define VOICE_ACTIVITY_GATE_H

#include <stdbool.h>
#include <stdint.h>

typedef enum {
    VOICE_ACTIVITY_GATE_BUFFER = 0,
    VOICE_ACTIVITY_GATE_OPEN,
    VOICE_ACTIVITY_GATE_FORWARD,
} voice_activity_gate_action_t;

typedef struct {
    bool is_open;
    uint16_t active_streak;
    int64_t last_active_ms;
} voice_activity_gate_t;

void voice_activity_gate_init(voice_activity_gate_t *gate);

voice_activity_gate_action_t voice_activity_gate_process(voice_activity_gate_t *gate,
                                                         uint32_t average_absolute_amplitude,
                                                         int64_t now_ms,
                                                         uint32_t threshold,
                                                         uint16_t debounce_frames,
                                                         uint32_t hold_ms);

#endif
