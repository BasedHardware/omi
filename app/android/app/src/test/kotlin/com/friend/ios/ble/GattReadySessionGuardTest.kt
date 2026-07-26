package com.friend.ios.ble

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class GattReadySessionGuardTest {
    @Test
    fun retiredDelayedPipelineCannotStartOrPublishForReplacementSession() {
        var activeSessionId: Long? = 41L
        val events = mutableListOf<String>()
        val guard = GattReadySessionGuard { activeSessionId }

        assertTrue(
            guard.runIfCurrent("aa:bb:cc:dd:ee:ff", 41L) {
                events.add("old MTU started")
            },
        )

        activeSessionId = 42L

        assertFalse(
            guard.runIfCurrent("aa:bb:cc:dd:ee:ff", 41L) {
                events.add("old services published")
            },
        )
        assertTrue(
            guard.runIfCurrent("aa:bb:cc:dd:ee:ff", 42L) {
                events.add("replacement services published")
            },
        )

        assertEquals(
            listOf("old MTU started", "replacement services published"),
            events,
        )
    }

    @Test
    fun retiredSessionCannotStartAfterDelay() {
        var activeSessionId: Long? = 7L
        var starts = 0
        val guard = GattReadySessionGuard { activeSessionId }

        activeSessionId = 8L

        assertFalse(
            guard.runIfCurrent("AA:BB:CC:DD:EE:FF", 7L) {
                starts++
            },
        )
        assertEquals(0, starts)
    }
}
