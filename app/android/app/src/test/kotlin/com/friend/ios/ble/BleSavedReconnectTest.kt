package com.friend.ios.ble

import org.junit.Assert.*
import org.junit.Test

class BleSavedReconnectTest {
    @Test fun supersededCompanionAssociationCannotRecreateOldOwner() {
        assertTrue(matchesManagedDevice("AA", "aa|true"))
        assertFalse(matchesManagedDevice("old", "new|false"))
        assertTrue(matchesManagedDevice("first", null))
    }

    @Test fun manualDisconnectBlocksQueuedStartsUntilExplicitManage() {
        val policy = BleSavedReconnect()
        policy.setEnabled("aa:bb", true)
        policy.block("AA:BB")
        assertTrue(policy.isBlocked("aa:bb"))
        assertNull(policy.event("aa:bb", "attempted", 100))
        policy.allow("aa:bb")
        assertFalse(policy.isBlocked("AA:BB"))
    }

    @Test fun repeatedTicksAreBoundedAndConnectedOutcomeIsReserved() {
        val policy = BleSavedReconnect()
        policy.setEnabled("aa", true)
        assertNotNull(policy.event("aa", "attempted", 0))
        repeat(10000) { assertNull(policy.event("aa", "attempted", it.toLong())) }
        repeat(6) { assertNotNull(policy.event("aa", "failed:$it", 10000)) }
        assertNull(policy.event("aa", "failed:extra", 10000))
        assertNotNull(policy.event("aa", "connected", 10001))
        assertNull(policy.event("aa", "connected", 10002))
        assertNotNull(policy.event("aa", "attempted", 20000))
    }

    @Test fun killingPolicyClearsNewNativeIntentBlocks() {
        val policy = BleSavedReconnect()
        policy.setEnabled("aa", true)
        policy.block("aa")
        assertTrue(policy.isBlocked("aa"))
        policy.setEnabled("aa", false)
        assertFalse(policy.isBlocked("aa"))
    }

    @Test fun onlySavedPairingsEmitAndKillStopsTelemetry() {
        val policy = BleSavedReconnect()
        assertNull(policy.event("other", "attempted", 100))
        policy.setEnabled("aa:bb", true)
        assertEquals(Triple(1L, "attempted", 0L), policy.event("AA:BB", "attempted", 100))
        assertEquals(Triple(1L, "failed:gatt", 50L), policy.event("aa:bb", "failed:gatt", 150))
        assertNull(policy.event("aa:bb", "attempted", 160))
        assertEquals(Triple(2L, "connected", 100L), policy.event("aa:bb", "connected", 200))
        assertEquals(Triple(1L, "attempted", 0L), policy.event("aa:bb", "attempted", 300))
        policy.setEnabled("AA:BB", false)
        assertNull(policy.event("aa:bb", "attempted", 400))
    }
}
