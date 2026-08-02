package com.friend.ios.ble

/**
 * Coalesces notification requests for one CCCD.
 *
 * Android callbacks do not expose a request ID or the value written. Keeping
 * only one transition in flight and remembering the latest desired state
 * avoids redundant same-state writes when native/background and Flutter
 * subscribers attach to the same characteristic.
 */
internal class NotificationTransitionState {
    private var confirmed: Boolean? = null
    private var desired: Boolean? = null
    private var inFlight: Boolean? = null

    @Synchronized
    fun request(enabled: Boolean): Boolean? {
        desired = enabled
        if (inFlight != null || confirmed == enabled) return null
        inFlight = enabled
        return enabled
    }

    @Synchronized
    fun currentInFlight(): Boolean? = inFlight

    /**
     * Returns the next coalesced transition, already marked in-flight.
     * Failures are left to session recovery rather than retried on a GATT that
     * may no longer be usable.
     */
    @Synchronized
    fun complete(attempted: Boolean, success: Boolean): Boolean? {
        if (inFlight != attempted) return null
        inFlight = null
        if (!success) return null
        confirmed = attempted

        val next = desired
        if (next == null || next == confirmed) return null
        inFlight = next
        return next
    }
}
