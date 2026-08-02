package com.friend.ios.ble

/**
 * Keeps RSSI polling scoped to the one diagnostics view that requested it.
 *
 * A disconnect pauses polling without losing the subscription, so a reconnect
 * can resume diagnostics without turning RSSI reads into connection keep-alives.
 */
internal class RssiDiagnosticsPolicy {
    @Volatile
    private var subscribedAddress: String? = null

    fun subscribe(address: String) {
        subscribedAddress = address.uppercase()
    }

    fun unsubscribe(address: String): Boolean {
        val normalized = address.uppercase()
        if (subscribedAddress != normalized) return false
        subscribedAddress = null
        return true
    }

    fun shouldPoll(address: String, isConnected: Boolean): Boolean =
        isConnected && subscribedAddress == address.uppercase()

    fun isSubscribed(address: String): Boolean =
        subscribedAddress == address.uppercase()
}

internal fun shouldRecoverAfterGattTimeout(kind: GattOperationKind): Boolean =
    kind != GattOperationKind.READ_RSSI
