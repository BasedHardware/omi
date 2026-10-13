package com.friend.ios.ble

/** Per-device probe ownership. Callers serialize transitions with their device lock. */
internal class RetentionProbeLifecycle {
    class Probe internal constructor(internal val connection: Any)

    private var activeProbe: Probe? = null
    val inFlight: Boolean get() = activeProbe != null
    @Volatile var runtimeVerified: Boolean = false
        private set

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
        interrupt()
        return true
    }

    fun interrupt() {
        activeProbe = null
        resetVerification()
    }

    /** Retired attempts and reads from a replaced connection cannot affect a fresh probe. */
    fun result(probe: Probe, currentConnection: Any?, advertised: Boolean, payload: ByteArray?): Boolean {
        if (activeProbe !== probe || currentConnection !== probe.connection) return false
        activeProbe = null
        runtimeVerified = advertised && BleReconnectBackoff.retentionProbeSucceeds(payload)
        return true
    }
}
