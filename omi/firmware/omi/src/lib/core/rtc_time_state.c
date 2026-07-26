#include "rtc_time_state.h"

#include <errno.h>

void rtc_time_state_init_from_persisted(rtc_time_state_t *state, uint64_t persisted_epoch_ms, int64_t now_uptime_ms)
{
    if (!state) {
        return;
    }

    state->base_epoch_ms = persisted_epoch_ms;
    state->base_uptime_ms = now_uptime_ms;
    state->valid = false;
}

int rtc_time_state_set_live_sync(rtc_time_state_t *state, uint64_t utc_epoch_ms, int64_t now_uptime_ms)
{
    if (!state || utc_epoch_ms < RTC_TIME_MIN_VALID_EPOCH_MS || now_uptime_ms < 0) {
        return -EINVAL;
    }

    state->base_epoch_ms = utc_epoch_ms;
    state->base_uptime_ms = now_uptime_ms;
    state->valid = true;
    return 0;
}

bool rtc_time_state_is_valid(const rtc_time_state_t *state)
{
    return state && state->valid;
}

uint64_t rtc_time_state_now_ms(const rtc_time_state_t *state, int64_t now_uptime_ms)
{
    if (!rtc_time_state_is_valid(state)) {
        return 0U;
    }

    uint64_t delta_ms = 0U;
    if (now_uptime_ms >= 0 && state->base_uptime_ms >= 0 && now_uptime_ms > state->base_uptime_ms) {
        delta_ms = (uint64_t) now_uptime_ms - (uint64_t) state->base_uptime_ms;
    }

    if (delta_ms > UINT64_MAX - state->base_epoch_ms) {
        return UINT64_MAX;
    }
    return state->base_epoch_ms + delta_ms;
}
