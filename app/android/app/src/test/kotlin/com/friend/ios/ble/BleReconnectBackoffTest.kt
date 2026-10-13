package com.friend.ios.ble

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class BleReconnectBackoffTest {
    @Test
    fun `ordinary failures back off and then stay at the cap`() {
        val backoff = BleReconnectBackoff()
        assertEquals(
            listOf(3_000L, 6_000L, 12_000L, 30_000L, 60_000L),
            List(5) { backoff.nextDelayMs("AA:BB:CC:DD:EE:FF") },
        )
        repeat(100) { assertEquals(60_000L, backoff.nextDelayMs("AA:BB:CC:DD:EE:FF")) }
    }

    @Test
    fun `devices keep independent schedules`() {
        val backoff = BleReconnectBackoff()
        assertEquals(3_000L, backoff.nextDelayMs("A"))
        assertEquals(6_000L, backoff.nextDelayMs("A"))
        assertEquals(3_000L, backoff.nextDelayMs("B"))
        assertEquals(12_000L, backoff.nextDelayMs("a"))
        assertEquals(6_000L, backoff.nextDelayMs("b"))
    }

    @Test
    fun `successful connection and explicit retry return to the fastest interval`() {
        val backoff = BleReconnectBackoff()
        repeat(8) { backoff.nextDelayMs("AA:BB") }
        repeat(8) { backoff.nextDelayMs("BB:AA") }
        assertEquals(60_000L, backoff.nextDelayMs("AA:BB"))
        assertEquals(60_000L, backoff.nextDelayMs("BB:AA"))

        backoff.reset("aa:bb")
        assertEquals(3_000L, backoff.nextDelayMs("AA:BB"))
        assertEquals(60_000L, backoff.nextDelayMs("BB:AA"))
    }

    @Test
    fun `foreground pulls a long pending wait forward and leaves an already-fast one`() {
        val backoff = BleReconnectBackoff()
        repeat(6) { backoff.nextDelayMs("A") }

        assertNull(backoff.foregroundDelayMs(null))
        assertNull(backoff.foregroundDelayMs(BleReconnectBackoff.FASTEST_DELAY_MS))
        assertEquals(3_000L, backoff.foregroundDelayMs(12_000L))
        assertEquals(3_000L, backoff.foregroundDelayMs(60_000L))

        backoff.reset("A")
        assertEquals(3_000L, backoff.nextDelayMs("A"))
    }

    @Test
    fun `foreground compares the remaining wait not the scheduled duration`() {
        val backoff = BleReconnectBackoff()
        repeat(6) { backoff.nextDelayMs("A") }

        // 5s into a 6s wait: 1s remains, which is shorter than the fastest
        // interval, so foregroundDelayMs must decline to replace the timer.
        assertEquals(1_000L, backoff.remainingDelayMs(scheduledDelayMs = 6_000L, elapsedMs = 5_000L))
        assertNull(backoff.foregroundDelayMs(backoff.remainingDelayMs(6_000L, 5_000L)))

        // 1s into a 60s wait: 59s remains, so it is pulled forward to 3s.
        assertEquals(59_000L, backoff.remainingDelayMs(60_000L, 1_000L))
        assertEquals(3_000L, backoff.foregroundDelayMs(backoff.remainingDelayMs(60_000L, 1_000L)))

        // Elapsed can never exceed the schedule.
        assertEquals(0L, backoff.remainingDelayMs(3_000L, 10_000L))
        assertNull(backoff.foregroundDelayMs(backoff.remainingDelayMs(3_000L, 10_000L)))
    }

    @Test
    fun `CCCD recovery does not advance or replenish the ordinary schedule`() {
        val backoff = BleReconnectBackoff()
        assertEquals(3_000L, backoff.delayForFailure("A", cccdTimeout = true, cccdDelayMs = 3_000L))
        assertEquals(6_000L, backoff.delayForFailure("A", cccdTimeout = true, cccdDelayMs = 6_000L))
        assertNull(backoff.delayForFailure("A", cccdTimeout = true, cccdDelayMs = null))

        assertEquals(3_000L, backoff.delayForFailure("A", cccdTimeout = false, cccdDelayMs = null))
        assertEquals(6_000L, backoff.delayForFailure("A", cccdTimeout = false, cccdDelayMs = 3_000L))
        repeat(3) { backoff.delayForFailure("A", cccdTimeout = true, cccdDelayMs = null) }
        assertEquals(12_000L, backoff.delayForFailure("A", cccdTimeout = false, cccdDelayMs = null))
    }

    @Test
    fun `unverified retention keeps the legacy flat cadence and never escalates`() {
        // INV-CAP-1: a device whose firmware has not advertised a storage-drain
        // service must keep the pre-backoff 3s retry loop; stretching the gap
        // would park out-of-range audio behind a wait it cannot afford.
        val backoff = BleReconnectBackoff()
        repeat(50) {
            assertEquals(3_000L, backoff.delayForFailure("AA:BB:CC:DD:EE:FF", cccdTimeout = false, cccdDelayMs = null, retentionVerified = false))
        }
    }

    @Test
    fun `flat cadence leaves no stale step so a later verified device escalates from the fastest interval`() {
        val backoff = BleReconnectBackoff()
        repeat(10) { backoff.delayForFailure("A", cccdTimeout = false, cccdDelayMs = null, retentionVerified = false) }
        // The same device later advertises retention (e.g. firmware upgrade):
        // it must start the escalated schedule from the fastest interval.
        assertEquals(3_000L, backoff.delayForFailure("A", cccdTimeout = false, cccdDelayMs = null, retentionVerified = true))
        assertEquals(6_000L, backoff.delayForFailure("A", cccdTimeout = false, cccdDelayMs = null, retentionVerified = true))
    }

    @Test
    fun `CCCD timeout passes its own delay through regardless of retention verification`() {
        val backoff = BleReconnectBackoff()
        assertEquals(6_000L, backoff.delayForFailure("A", cccdTimeout = true, cccdDelayMs = 6_000L, retentionVerified = false))
        assertNull(backoff.delayForFailure("A", cccdTimeout = true, cccdDelayMs = null, retentionVerified = false))
        // CCCD pass-through must not consume or advance the ordinary schedule.
        assertEquals(3_000L, backoff.delayForFailure("A", cccdTimeout = false, cccdDelayMs = null, retentionVerified = true))
    }
}
