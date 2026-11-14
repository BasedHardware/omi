package com.friend.ios.ble

/**
 * Retires a radio-connected link whose GATT service discovery failed terminally (#19453).
 *
 * The OS keeps such a link connected without ever delivering
 * onConnectionStateChange(STATE_DISCONNECTED), so the managed service never sees a
 * disconnect and saved reconnect never resumes — the app shows the saved pendant
 * disconnected until the user manually resets it. Retiring the unusable link reports a
 * disconnect that the service's existing retry path handles, mirroring the iOS fix in
 * #23872.
 *
 * Pure decisions over injected effects; called only on the GATT callback handler thread.
 */
internal class DiscoveryFailureRetire<G : Any>(
    private val releaseTrackedLink: (G) -> Boolean,
    private val cleanupPeripheral: (String) -> Unit,
    private val disconnectLink: (G) -> Unit,
    private val closeLink: (G) -> Unit,
    private val onTeardownError: (stage: String, error: Exception) -> Unit = { _, _ -> },
    private val notifyDisconnected: (address: String, gattHash: Int, status: Int) -> Unit,
) {
    /**
     * Handles one failed onServicesDiscovered for [gatt]. Releasing the tracked link is
     * the latch: it succeeds only for the current link's first terminal failure, so
     * duplicate or late callbacks — and failures from an already-disconnected or
     * superseded link — are ignored, while a replacement link stays fully eligible.
     */
    fun onDiscoveryFailed(gatt: G, address: String, gattHash: Int, status: Int) {
        if (!releaseTrackedLink(gatt)) return
        cleanupPeripheral(address)
        try {
            disconnectLink(gatt)
        } catch (e: Exception) {
            onTeardownError("disconnect", e)
        }
        try {
            closeLink(gatt)
        } catch (e: Exception) {
            onTeardownError("close", e)
        }
        // Teardown precedes the notify: the service re-enters connectToDevice from this
        // callback and must not observe the dead link as still connected.
        notifyDisconnected(address, gattHash, status)
    }
}
