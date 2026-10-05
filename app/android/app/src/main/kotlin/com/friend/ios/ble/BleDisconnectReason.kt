package com.friend.ios.ble

/** Maps native HCI statuses to the existing diagnostics/analytics reason vocabulary. */
internal object BleDisconnectReason {
    /** Error delivered to Flutter when a disconnect interrupts device readiness. */
    fun connectionErrorFromStatus(status: Int, retrying: Boolean = true): String? = when {
        status == OmiBleManager.CCCD_TIMEOUT_STATUS && !retrying -> "cccd_timeout_exhausted"
        status == OmiBleManager.CCCD_TIMEOUT_STATUS -> "cccd_timeout"
        status == 137 -> "pairing_lost"
        status != 0 -> "gatt_status_$status"
        else -> null
    }

    fun fromStatus(status: Int): String = when (status) {
        0 -> "clean_disconnect"
        8, 0x22 -> "connection_timeout" // 0x22: LMP/LL response timeout.
        19 -> "remote_device_terminated"
        -1 -> "app_closed"
        OmiBleManager.CCCD_TIMEOUT_STATUS -> "cccd_ack_timeout"
        // 0x16 is local termination; 0x3e is failed establishment, not Instant Passed (0x28).
        // Keep their codes without inventing a cause outside the existing reason vocabulary.
        else -> "gatt_error_$status"
    }
}
