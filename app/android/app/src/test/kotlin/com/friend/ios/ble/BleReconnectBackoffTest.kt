package com.friend.ios.ble

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class BleReconnectBackoffTest {
    @Test
    fun repeatedFailuresBackOffAndCap() {
        assertEquals(500L, BleReconnectBackoff.delayMillis(attempt = 0, jitterUnit = 0.5))
        assertEquals(1_000L, BleReconnectBackoff.delayMillis(attempt = 1, jitterUnit = 0.5))
        assertEquals(8_000L, BleReconnectBackoff.delayMillis(attempt = 4, jitterUnit = 0.5))
        assertEquals(30_000L, BleReconnectBackoff.delayMillis(attempt = 6, jitterUnit = 0.5))
        assertEquals(30_000L, BleReconnectBackoff.delayMillis(attempt = 100, jitterUnit = 0.5))
    }

    @Test
    fun jitterStaysBoundedAndSeparatesReconnectStorms() {
        val low = BleReconnectBackoff.delayMillis(attempt = 4, jitterUnit = 0.0)
        val middle = BleReconnectBackoff.delayMillis(attempt = 4, jitterUnit = 0.5)
        val high = BleReconnectBackoff.delayMillis(attempt = 4, jitterUnit = 1.0)

        assertEquals(6_400L, low)
        assertEquals(8_000L, middle)
        assertEquals(9_600L, high)
        assertTrue(low < middle && middle < high)
    }

    @Test
    fun physicalConnectDoesNotResetBackoffBeforeTheSessionIsStable() {
        val state = BleReconnectState()

        assertEquals(BleReconnectAttempt(number = 1, delayMillis = 500), state.recordFailure(jitterUnit = 0.5))
        state.markTransportConnected()
        assertEquals(BleReconnectAttempt(number = 2, delayMillis = 1_000), state.recordFailure(jitterUnit = 0.5))

        state.markStable()
        assertEquals(BleReconnectAttempt(number = 1, delayMillis = 500), state.recordFailure(jitterUnit = 0.5))
    }
}
