#include "rtc_elapsed_recovery.h"

#include <errno.h>
#include <stddef.h>

#include "rtc_time_state.h"

static bool trusted_bound_is_sound(uint64_t max_trusted_elapsed_ms)
{
    return max_trusted_elapsed_ms > 0U && max_trusted_elapsed_ms < RTC_ELAPSED_COUNTER_WRAP_MS;
}

static int clear_after_failure(const rtc_elapsed_recovery_ops_t *ops, void *context, int original_error)
{
    int clear_error = ops->clear_marker(context);
    return clear_error ? clear_error : original_error;
}

static int validate_prepare_ops(const rtc_elapsed_recovery_ops_t *ops)
{
    if (!ops || !ops->clear_marker || !ops->save_marker || !ops->power_on || !ops->set_counter_resolution ||
        !ops->enable_counter || !ops->reset_counter || !ops->read_counter) {
        return -EINVAL;
    }
    return 0;
}

static int validate_attempt_ops(const rtc_elapsed_recovery_ops_t *ops)
{
    if (!ops || !ops->load_marker || !ops->clear_marker || !ops->power_on || !ops->set_counter_resolution ||
        !ops->enable_counter || !ops->read_counter || !ops->apply_current_epoch_ms) {
        return -EINVAL;
    }
    return 0;
}

int rtc_elapsed_recovery_prepare(uint64_t current_epoch_s,
                                 uint64_t max_trusted_elapsed_ms,
                                 const rtc_elapsed_recovery_ops_t *ops,
                                 void *context)
{
    int err = validate_prepare_ops(ops);
    if (err) {
        return err;
    }

    /*
     * Consume first. A previous attempt must never survive a failed new
     * preparation and later masquerade as the new system-off interval.
     */
    err = ops->clear_marker(context);
    if (err) {
        return err;
    }

    if (current_epoch_s < RTC_TIME_MIN_VALID_EPOCH_S) {
        return -EINVAL;
    }
    if (!trusted_bound_is_sound(max_trusted_elapsed_ms)) {
        return -ENOTSUP;
    }

    err = ops->power_on(context);
    if (err) {
        return clear_after_failure(ops, context, err);
    }
    err = ops->set_counter_resolution(context);
    if (err) {
        return clear_after_failure(ops, context, err);
    }
    err = ops->enable_counter(context);
    if (err) {
        return clear_after_failure(ops, context, err);
    }
    err = ops->reset_counter(context);
    if (err) {
        return clear_after_failure(ops, context, err);
    }

    uint32_t counter;
    err = ops->read_counter(&counter, context);
    if (err) {
        return clear_after_failure(ops, context, err);
    }

    rtc_elapsed_marker_t marker = {
        .epoch_s = current_epoch_s,
        .counter = counter & RTC_ELAPSED_COUNTER_MASK,
    };
    err = ops->save_marker(&marker, context);
    if (err) {
        return clear_after_failure(ops, context, err);
    }
    return 0;
}

int rtc_elapsed_recovery_attempt(bool verified_system_off_wake,
                                 uint64_t max_trusted_elapsed_ms,
                                 const rtc_elapsed_recovery_ops_t *ops,
                                 void *context)
{
    int err = validate_attempt_ops(ops);
    if (err) {
        return err;
    }

    rtc_elapsed_marker_t marker = {0};
    err = ops->load_marker(&marker, context);
    if (err) {
        return clear_after_failure(ops, context, err);
    }
    if (marker.epoch_s == 0U) {
        return 0;
    }

    /*
     * Consume before checking hardware or making time valid. A reset at any
     * later instruction loses this recovery attempt instead of replaying it.
     */
    err = ops->clear_marker(context);
    if (err) {
        return err;
    }

    if (!verified_system_off_wake) {
        return 0;
    }
    if (!trusted_bound_is_sound(max_trusted_elapsed_ms)) {
        return -ENOTSUP;
    }
    if (marker.epoch_s < RTC_TIME_MIN_VALID_EPOCH_S) {
        return -EINVAL;
    }

    err = ops->power_on(context);
    if (err) {
        return err;
    }
    err = ops->set_counter_resolution(context);
    if (err) {
        return err;
    }
    err = ops->enable_counter(context);
    if (err) {
        return err;
    }

    uint32_t current_counter;
    err = ops->read_counter(&current_counter, context);
    if (err) {
        return err;
    }

    uint32_t delta_ticks = (current_counter - marker.counter) & RTC_ELAPSED_COUNTER_MASK;
    uint64_t delta_ms = ((uint64_t) delta_ticks * RTC_ELAPSED_COUNTER_TICK_US) / UINT64_C(1000);
    if (delta_ms > max_trusted_elapsed_ms) {
        return -ERANGE;
    }
    if (marker.epoch_s > UINT64_MAX / UINT64_C(1000)) {
        return -ERANGE;
    }

    uint64_t base_epoch_ms = marker.epoch_s * UINT64_C(1000);
    if (delta_ms > UINT64_MAX - base_epoch_ms) {
        return -ERANGE;
    }

    err = ops->apply_current_epoch_ms(base_epoch_ms + delta_ms, context);
    if (err) {
        return err;
    }
    return 1;
}
