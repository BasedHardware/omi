package com.friend.ios.ble

/**
 * Bounded backoff for links retired after failed GATT service discovery (#19453).
 *
 * A discovery failure retires the radio-connected link and re-enters the ordinary
 * disconnect path, which retries at a fixed 3 s with no attempt limit — a persistent
 * discovery failure (e.g. status 133) then reconnects, fails discovery, and retires
 * forever (PR #23882 review). This policy gives those retirements the iOS
 * saved-reconnect backoff (#23872): ~1 s doubling to a 60 s long tail, reset only by
 * a successful discovery. In-memory by design: process restart begins a fresh ladder,
 * unlike the durable [CccdReconnectPolicy] budget, which discovery failures never spend.
 */
internal class DiscoveryReconnectPolicy(
    private val baseDelayMs: Long = 1_000L,
    private val longTailDelayMs: Long = 60_000L,
) {
    private val consecutiveFailures = mutableMapOf<String, Int>()
    private val pendingRetirement = mutableSetOf<String>()

    /**
     * Counts one latch-confirmed discovery failure and arms the marker consumed while
     * the resulting disconnect is processed. Duplicate or late discovery failures never
     * reach here ([DiscoveryFailureRetire] rejects them before notifying).
     */
    fun onDiscoveryRetirement(address: String) {
        val key = address.uppercase()
        consecutiveFailures[key] = (consecutiveFailures[key] ?: 0) + 1
        pendingRetirement.add(key)
    }

    /**
     * The backoff delay for the disconnect the caller is now processing, or null when
     * that disconnect is ordinary (radio drop, CCCD retirement). Non-null exactly once
     * per retirement, so a later genuine disconnect of the retried link keeps its own
     * path. The original GATT status is unaffected: diagnostics never see this policy.
     */
    fun consumeRetirementBackoffMs(address: String): Long? {
        val key = address.uppercase()
        if (!pendingRetirement.remove(key)) return null
        val attempt = consecutiveFailures[key] ?: 1
        // min(60 s, 2^min(attempt-1, 6)) — the iOS OmiBleConnectionPolicy.savedRetryDelay ladder.
        return minOf(longTailDelayMs, baseDelayMs shl minOf(attempt - 1, SHIFT_CAP))
    }

    /** A complete successful discovery clears the ladder and any stale marker. */
    fun onDiscoverySucceeded(address: String) {
        val key = address.uppercase()
        consecutiveFailures.remove(key)
        pendingRetirement.remove(key)
    }

    /** A fresh connect attempt invalidates any unconsumed marker but keeps the ladder. */
    fun onConnectAttempt(address: String) {
        pendingRetirement.remove(address.uppercase())
    }

    private companion object {
        const val SHIFT_CAP = 6
    }
}
