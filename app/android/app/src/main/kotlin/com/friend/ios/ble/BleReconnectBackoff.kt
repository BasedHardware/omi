package com.friend.ios.ble

import kotlin.math.roundToLong

internal object BleReconnectBackoff {
    private const val INITIAL_DELAY_MS = 500L
    private const val MAX_DELAY_MS = 30_000L
    private const val JITTER_FRACTION = 0.20

    /**
     * Exponential reconnect delay with bounded jitter.
     *
     * [jitterUnit] is injected so production can spread radio work while tests
     * remain deterministic: 0 maps to -20%, 0.5 to no jitter, and 1 to +20%.
     */
    fun delayMillis(attempt: Int, jitterUnit: Double): Long {
        val boundedAttempt = attempt.coerceIn(0, 30)
        val multiplier = 1L shl boundedAttempt
        val base = (INITIAL_DELAY_MS * multiplier).coerceAtMost(MAX_DELAY_MS)
        val boundedJitter = jitterUnit.coerceIn(0.0, 1.0)
        val factor = 1.0 - JITTER_FRACTION + (2.0 * JITTER_FRACTION * boundedJitter)
        return (base * factor).roundToLong().coerceAtMost(MAX_DELAY_MS)
    }
}

internal data class BleReconnectAttempt(
    val number: Int,
    val delayMillis: Long,
)

/**
 * Reconnect lifecycle ownership. Reaching L2CAP is not success: discovery,
 * MTU, and subscriptions may still fail. Only a stable session (or an
 * explicit user/OS reconnect signal) resets the failure history.
 */
internal class BleReconnectState {
    private var failedAttempts = 0

    fun recordFailure(jitterUnit: Double): BleReconnectAttempt {
        val attempt = failedAttempts
        failedAttempts = (attempt + 1).coerceAtMost(30)
        return BleReconnectAttempt(
            number = attempt + 1,
            delayMillis = BleReconnectBackoff.delayMillis(attempt, jitterUnit),
        )
    }

    fun markTransportConnected() {
        // Intentionally retained: setup may still fail after physical connect.
    }

    fun markStable() {
        failedAttempts = 0
    }

    fun resetForExplicitRequest() {
        failedAttempts = 0
    }
}
