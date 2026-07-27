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
    uint32_t minimum_threshold;
    uint32_t noise_margin;
    uint8_t noise_rise_shift;
    uint8_t noise_fall_shift;
    uint16_t debounce_frames;
    uint32_t hold_ms;
} voice_activity_gate_config_t;

typedef struct {
    bool is_open;
    bool frame_active;
    bool noise_floor_initialized;
    uint16_t active_streak;
    int64_t last_active_ms;
    uint32_t noise_floor;
    uint32_t active_threshold;
} voice_activity_gate_t;

void voice_activity_gate_init(voice_activity_gate_t *gate);

voice_activity_gate_action_t voice_activity_gate_process(voice_activity_gate_t *gate,
                                                         uint32_t average_absolute_amplitude,
                                                         int64_t now_ms,
                                                         const voice_activity_gate_config_t *config);

#endif
