package com.friend.ios.ble

/**
 * Pacing for ordinary BLE disconnect retries (pendant out of range, GATT 133, and
 * the other failures that are not a CCCD timeout).
 *
 * The schedule is 3s, 6s, 12s, 30s, then a 60s cap. The per-device step is stored
 * as an index into that table, so a device that never comes back cannot grow an
 * unbounded counter. CCCD timeout recovery keeps its own budget and must not move
 * this schedule.
 *
 * [reset] returns the device to the fastest interval. Callers use it after a
 * successful connection, when the app comes to the foreground, and before an
 * explicit connect or retry. A manual retry connects immediately; this class
 * only answers how long an automatic retry should wait.
 */
internal class BleReconnectBackoff(
    private val stepsMs: LongArray = DEFAULT_STEPS_MS,
) {
    init {
        require(stepsMs.isNotEmpty()) { "reconnect backoff needs at least one step" }
        require(stepsMs.all { it > 0L }) { "reconnect backoff steps must be positive" }
    }

    private val lock = Any()
    private val stepByAddress = HashMap<String, Int>()

    val maxTrackedFailures: Int get() = stepsMs.size

    /**
     * Delay for the next automatic retry, then advance one step (capped).
     * A CCCD timeout passes [cccdDelayMs] through and leaves the ordinary step alone,
     * including when that delay is null because the CCCD budget is spent.
     */
    fun delayForFailure(address: String, cccdTimeout: Boolean, cccdDelayMs: Long?): Long? {
        if (cccdTimeout) return cccdDelayMs
        return nextDelayMs(address)
    }

    fun nextDelayMs(address: String): Long = synchronized(lock) {
        val key = address.uppercase()
        val index = (stepByAddress[key] ?: 0).coerceIn(0, stepsMs.lastIndex)
        stepByAddress[key] = (index + 1).coerceAtMost(stepsMs.lastIndex)
        stepsMs[index]
    }

    fun reset(address: String) {
        synchronized(lock) { stepByAddress.remove(address.uppercase()) }
    }

    /**
     * How soon a pending automatic retry should run once the app is in the foreground.
     * Null means there is nothing to pull forward: no retry is waiting, or it is
     * already scheduled at the fastest interval.
     */
    fun foregroundDelayMs(pendingDelayMs: Long?): Long? {
        val fastest = stepsMs[0]
        if (pendingDelayMs == null || pendingDelayMs <= fastest) return null
        return fastest
    }

    companion object {
        val DEFAULT_STEPS_MS = longArrayOf(3_000L, 6_000L, 12_000L, 30_000L, 60_000L)
        const val FASTEST_DELAY_MS = 3_000L
    }
}
