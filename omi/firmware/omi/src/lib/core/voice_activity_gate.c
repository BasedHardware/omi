#include "voice_activity_gate.h"

#include <limits.h>
#include <stddef.h>

static uint32_t saturating_add_u32(uint32_t left, uint32_t right)
{
    return left > UINT32_MAX - right ? UINT32_MAX : left + right;
}

static uint32_t adaptive_step(uint32_t delta, uint8_t shift)
{
    if (delta == 0U) {
        return 0U;
    }
    if (shift >= 32U) {
        return 1U;
    }

    uint32_t step = delta >> shift;
    return step == 0U ? 1U : step;
}

static uint32_t active_threshold(const voice_activity_gate_t *gate, const voice_activity_gate_config_t *config)
{
    uint32_t threshold = saturating_add_u32(gate->noise_floor, config->noise_margin);
    return threshold < config->minimum_threshold ? config->minimum_threshold : threshold;
}

static void update_noise_floor(voice_activity_gate_t *gate,
                               uint32_t average_absolute_amplitude,
                               const voice_activity_gate_config_t *config)
{
    if (!gate->noise_floor_initialized) {
        /*
         * A loud first frame may be speech. Seed below the opening threshold
         * rather than learning that speech as the ambient floor.
         */
        uint32_t maximum_seed =
            config->minimum_threshold > config->noise_margin ? config->minimum_threshold - config->noise_margin : 0U;
        gate->noise_floor = average_absolute_amplitude < maximum_seed ? average_absolute_amplitude : maximum_seed;
        gate->noise_floor_initialized = true;
        return;
    }

    if (average_absolute_amplitude > gate->noise_floor) {
        gate->noise_floor += adaptive_step(average_absolute_amplitude - gate->noise_floor, config->noise_rise_shift);
    } else {
        gate->noise_floor -= adaptive_step(gate->noise_floor - average_absolute_amplitude, config->noise_fall_shift);
    }
}

void voice_activity_gate_init(voice_activity_gate_t *gate)
{
    if (!gate) {
        return;
    }

    gate->is_open = false;
    gate->frame_active = false;
    gate->noise_floor_initialized = false;
    gate->active_streak = 0U;
    gate->last_active_ms = 0;
    gate->noise_floor = 0U;
    gate->active_threshold = 0U;
}

voice_activity_gate_action_t voice_activity_gate_process(voice_activity_gate_t *gate,
                                                         uint32_t average_absolute_amplitude,
                                                         int64_t now_ms,
                                                         const voice_activity_gate_config_t *config)
{
    if (!gate || !config || config->minimum_threshold == 0U || config->noise_margin == 0U ||
        config->debounce_frames == 0U || config->hold_ms == 0U) {
        return VOICE_ACTIVITY_GATE_BUFFER;
    }

    if (!gate->noise_floor_initialized) {
        update_noise_floor(gate, average_absolute_amplitude, config);
    }
    gate->active_threshold = active_threshold(gate, config);
    gate->frame_active = average_absolute_amplitude >= gate->active_threshold;

    if (gate->is_open) {
        if (gate->frame_active) {
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
        if ((uint64_t) (now_ms - gate->last_active_ms) < config->hold_ms) {
            return VOICE_ACTIVITY_GATE_FORWARD;
        }

        gate->is_open = false;
        gate->active_streak = 0U;
        return VOICE_ACTIVITY_GATE_BUFFER;
    }

    if (!gate->frame_active) {
        gate->active_streak = 0U;
        update_noise_floor(gate, average_absolute_amplitude, config);
        gate->active_threshold = active_threshold(gate, config);
        return VOICE_ACTIVITY_GATE_BUFFER;
    }

    if (gate->active_streak < UINT16_MAX) {
        gate->active_streak++;
    }
    gate->last_active_ms = now_ms;
    if (gate->active_streak < config->debounce_frames) {
        return VOICE_ACTIVITY_GATE_BUFFER;
    }

    gate->is_open = true;
    gate->active_streak = 0U;
    return VOICE_ACTIVITY_GATE_OPEN;
}
