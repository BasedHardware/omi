package com.friend.ios

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DeviceDiagnosticsLifecyclePolicyTest {
    @Test
    fun processStartRecordsAppLaunchAndFlagsAnOpenPriorProcessRun() {
        assertEquals(listOf("app_launch"), DeviceDiagnosticsLifecyclePolicy.processStartEvents(false))
        assertEquals(
            listOf("previous_run_unclean", "app_launch"),
            DeviceDiagnosticsLifecyclePolicy.processStartEvents(true)
        )
    }

    @Test
    fun runClosesOnlyWhenTheAppFinishesWithoutPersistentBleService() {
        assertTrue(DeviceDiagnosticsLifecyclePolicy.shouldMarkRunClosed(isFinishing = true, bleServiceMustPersist = false))
        assertFalse(DeviceDiagnosticsLifecyclePolicy.shouldMarkRunClosed(isFinishing = false, bleServiceMustPersist = false))
        assertFalse(DeviceDiagnosticsLifecyclePolicy.shouldMarkRunClosed(isFinishing = true, bleServiceMustPersist = true))
    }
}
