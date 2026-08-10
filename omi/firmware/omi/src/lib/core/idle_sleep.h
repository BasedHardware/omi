#ifndef IDLE_SLEEP_H
#define IDLE_SLEEP_H

#include <stdbool.h>
#include <stdint.h>

/**
 * @brief Inputs the idle auto-sleep policy needs to decide whether the device is busy.
 *
 * Zephyr-free so the policy can be exercised by a host test.
 */
struct omi_idle_inputs {
    bool charging;
    bool connected;
    bool audio_subscribed;
    bool storage_transfer_active;
    bool offline_capture_possible;
};

/**
 * @brief Return true when the device must be held awake.
 *
 * The device is busy while it is charging, while a central is streaming audio,
 * while a storage sync transfer is running, and whenever the build can be
 * capturing to SD without a BLE link (the firmware cannot tell an idle pendant
 * from one mid-recording, so it must never power off in that build).
 */
static inline bool omi_idle_is_busy(const struct omi_idle_inputs *in)
{
    if (in == NULL) {
        return true;
    }
    return in->charging || in->offline_capture_possible || in->storage_transfer_active ||
           (in->connected && in->audio_subscribed);
}

/**
 * @brief Advance the idle counter by one tick and report whether to power off.
 *
 * @param in Current activity inputs.
 * @param tick_seconds Seconds elapsed since the previous call.
 * @param timeout_seconds Idle seconds required before sleeping (0 disables sleep).
 * @param idle_seconds In/out accumulated idle seconds.
 * @return true when the caller should enter system off.
 */
static inline bool
omi_idle_tick(const struct omi_idle_inputs *in, uint32_t tick_seconds, uint32_t timeout_seconds, uint32_t *idle_seconds)
{
    if (idle_seconds == NULL) {
        return false;
    }
    if (omi_idle_is_busy(in)) {
        *idle_seconds = 0;
        return false;
    }
    if (timeout_seconds == 0) {
        return false;
    }

    uint32_t next = *idle_seconds + tick_seconds;
    if (next < *idle_seconds) {
        next = UINT32_MAX;
    }
    *idle_seconds = next;
    return next >= timeout_seconds;
}

#endif // IDLE_SLEEP_H
