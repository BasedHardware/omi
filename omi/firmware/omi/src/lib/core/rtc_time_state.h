#ifndef RTC_TIME_STATE_H
#define RTC_TIME_STATE_H

#include <stdbool.h>
#include <stdint.h>

#define RTC_TIME_MIN_VALID_EPOCH_S UINT64_C(1700000000)
#define RTC_TIME_MIN_VALID_EPOCH_MS (RTC_TIME_MIN_VALID_EPOCH_S * UINT64_C(1000))

typedef struct {
    uint64_t base_epoch_ms;
    int64_t base_uptime_ms;
    bool valid;
} rtc_time_state_t;

/**
 * Restore a persisted epoch as historical context only. Since monotonic uptime
 * does not survive reboot, this state is deliberately invalid until live sync
 * supplies a current epoch.
 */
void rtc_time_state_init_from_persisted(rtc_time_state_t *state, uint64_t persisted_epoch_ms, int64_t now_uptime_ms);

/**
 * Install a current epoch from a live synchronization source.
 *
 * Persisted epochs and elapsed-time estimates cannot call this API. This keeps
 * validity ownership at the live synchronization boundary until firmware has
 * an independently bounded elapsed-time source.
 */
int rtc_time_state_set_live_sync(rtc_time_state_t *state, uint64_t utc_epoch_ms, int64_t now_uptime_ms);

bool rtc_time_state_is_valid(const rtc_time_state_t *state);
uint64_t rtc_time_state_now_ms(const rtc_time_state_t *state, int64_t now_uptime_ms);

#endif
