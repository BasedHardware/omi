#ifndef RTC_ELAPSED_RECOVERY_H
#define RTC_ELAPSED_RECOVERY_H

#include <stdbool.h>
#include <stdint.h>

#define RTC_ELAPSED_COUNTER_MASK UINT32_C(0x00FFFFFF)
#define RTC_ELAPSED_COUNTER_TICK_US UINT64_C(6400)
#define RTC_ELAPSED_COUNTER_WRAP_MS                                                                                    \
    ((((uint64_t) RTC_ELAPSED_COUNTER_MASK + UINT64_C(1)) * RTC_ELAPSED_COUNTER_TICK_US) / UINT64_C(1000))

typedef struct {
    uint64_t epoch_s;
    uint32_t counter;
} rtc_elapsed_marker_t;

typedef struct {
    int (*load_marker)(rtc_elapsed_marker_t *marker, void *context);
    int (*clear_marker)(void *context);
    int (*save_marker)(const rtc_elapsed_marker_t *marker, void *context);
    int (*power_on)(void *context);
    int (*set_counter_resolution)(void *context);
    int (*enable_counter)(void *context);
    int (*reset_counter)(void *context);
    int (*read_counter)(uint32_t *counter, void *context);
    int (*apply_current_epoch_ms)(uint64_t epoch_ms, void *context);
} rtc_elapsed_recovery_ops_t;

/**
 * Prepare a one-shot elapsed-time marker.
 *
 * max_trusted_elapsed_ms must be a strict, independently enforced upper bound
 * on the upcoming system-off interval and must be less than one counter wrap.
 * Zero means that no sound bound exists, so recovery is disabled. The old
 * marker is consumed before any preparation begins.
 */
int rtc_elapsed_recovery_prepare(uint64_t current_epoch_s,
                                 uint64_t max_trusted_elapsed_ms,
                                 const rtc_elapsed_recovery_ops_t *ops,
                                 void *context);

/**
 * Consume and, when safe, apply a one-shot elapsed-time marker.
 *
 * The marker is cleared before hardware access or apply_current_epoch_ms().
 * A positive return means time was applied, zero means no marker/provenance,
 * and a negative return is a fail-closed error.
 */
int rtc_elapsed_recovery_attempt(bool verified_system_off_wake,
                                 uint64_t max_trusted_elapsed_ms,
                                 const rtc_elapsed_recovery_ops_t *ops,
                                 void *context);

#endif
