package com.friend.ios.ble

/**
 * Per-device retention probe ownership and its completed proof. Callers
 * serialize transitions with their device lock.
 *
 * Proof lifecycle (INV-CAP-1): a successful read verifies the GATT link it ran
 * on, and that proof must survive the disconnected retry attempts that follow —
 * a proof erased at every disconnect makes the escalated schedule unreachable
 * because retry selection always runs after the link is already gone. Each NEW
 * connection resets the proof before any retry logic on the new link can
 * consume it, and reads retired by a replacement connection can never verify
 * their successor.
 */
internal class RetentionProbeLifecycle {
    class Probe internal constructor(internal val connection: Any)

    private var activeProbe: Probe? = null
    val inFlight: Boolean get() = activeProbe != null
    @Volatile var runtimeVerified: Boolean = false
        private set

    /** Clears the completed proof. Called when a new GATT connects and when a
     *  fresh ready event must re-prove storage for its own link. */
    fun resetVerification() {
        runtimeVerified = false
    }

    fun start(connection: Any): Probe? {
        if (inFlight) return null
        resetVerification()
        return Probe(connection).also { activeProbe = it }
    }

    fun timeout(probe: Probe): Boolean {
        if (activeProbe !== probe) return false
        cancel()
        return true
    }

    /** Retires an in-flight probe only. A completed verification survives:
     *  it is reset when the next GATT connects, not when this one drops. */
    fun cancel() {
        activeProbe = null
    }

    /** Retired attempts and reads from a replaced connection cannot affect a fresh probe. */
    fun result(probe: Probe, currentConnection: Any?, advertised: Boolean, payload: ByteArray?): Boolean {
        if (activeProbe !== probe || currentConnection !== probe.connection) return false
        activeProbe = null
        runtimeVerified = advertised && BleReconnectBackoff.retentionProbeSucceeds(payload)
        return true
    }
}
