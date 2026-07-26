package com.friend.ios.ble

/**
 * Prevents delayed post-discovery work from crossing a GATT replacement.
 *
 * The foreground service checks this guard both when its delayed MTU request
 * starts and when that request completes. A retired session can therefore
 * neither operate on nor publish services for its replacement.
 */
internal class GattReadySessionGuard(
    private val activeSessionId: (String) -> Long?,
) {
    fun runIfCurrent(
        address: String,
        expectedSessionId: Long,
        action: () -> Unit,
    ): Boolean {
        if (activeSessionId(address) != expectedSessionId) return false
        action()
        return true
    }
}
