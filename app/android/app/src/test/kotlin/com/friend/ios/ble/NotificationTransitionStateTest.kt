package com.friend.ios.ble

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class NotificationTransitionStateTest {
    @Test
    fun redundantSameStateRequestsCoalesceIntoOneCccdWrite() {
        val state = NotificationTransitionState()

        assertEquals(true, state.request(true))
        assertNull(state.request(true))
        assertNull(state.complete(attempted = true, success = true))
        assertNull(state.request(true))
    }

    @Test
    fun latestDesiredStateRunsAfterTheActiveTransition() {
        val state = NotificationTransitionState()

        assertEquals(true, state.request(true))
        assertNull(state.request(false))
        assertEquals(false, state.complete(attempted = true, success = true))
        assertEquals(false, state.currentInFlight())
        assertNull(state.complete(attempted = false, success = true))
    }

    @Test
    fun enableDisableEnableBurstAvoidsAnUnnecessaryToggle() {
        val state = NotificationTransitionState()

        assertEquals(true, state.request(true))
        assertNull(state.request(false))
        assertNull(state.request(true))
        assertNull(state.complete(attempted = true, success = true))
        assertNull(state.request(true))
    }

    @Test
    fun failedTransitionWaitsForGattSessionRecovery() {
        val state = NotificationTransitionState()

        assertEquals(true, state.request(true))
        assertNull(state.complete(attempted = true, success = false))
        assertNull(state.currentInFlight())
    }
}
