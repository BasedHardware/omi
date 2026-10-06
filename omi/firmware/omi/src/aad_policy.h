#ifndef OMI_AAD_POLICY_H
#define OMI_AAD_POLICY_H

#include <stdbool.h>
#include <stdint.h>

struct aad_policy_inputs {
    bool connected_quiet_enabled;
    bool connected;
    bool subscribed;
    bool live_mode;
    bool charging;
    bool transfer_active;
};

/* Behavior matrix (audio only; never changes BLE parameters or subscriptions):
 * disconnected: existing offline AAD hold;
 * connected/live/subscribed: speech resets the timer, quiet uses the long hold;
 * connected/continuous recording or unsubscribed: no hardware sleep;
 * charging: existing AAD policy, independent of this opt-in feature;
 * storage sync: existing veto in every mode.
 * CCC alone cannot distinguish phone-side Transcribe Later from live capture.
 * The session therefore defaults to continuous recording until explicitly set
 * to live by the central. Zero means that sleep is forbidden.
 */
static inline int64_t aad_policy_timeout(const struct aad_policy_inputs *in, int64_t offline_ms, int64_t live_ms)
{
    if (in->transfer_active) {
        return 0;
    }
    if (!in->connected_quiet_enabled || in->charging || !in->connected) {
        return offline_ms;
    }
    return in->subscribed && in->live_mode ? live_ms : 0;
}

#endif
