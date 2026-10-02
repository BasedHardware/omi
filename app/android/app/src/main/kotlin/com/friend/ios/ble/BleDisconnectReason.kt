package com.friend.ios.ble

/** Maps native HCI statuses to the existing diagnostics/analytics reason vocabulary. */
internal object BleDisconnectReason {
    fun fromStatus(status: Int): String = when (status) {
        0 -> "clean_disconnect"
        8, 0x22 -> "connection_timeout" // 0x22: LMP/LL response timeout.
        19 -> "remote_device_terminated"
        -1 -> "app_closed"
        // 0x16 is local termination; 0x3e is failed establishment, not Instant Passed (0x28).
        // Keep their codes without inventing a cause outside the existing reason vocabulary.
        else -> "gatt_error_$status"
    }
}
