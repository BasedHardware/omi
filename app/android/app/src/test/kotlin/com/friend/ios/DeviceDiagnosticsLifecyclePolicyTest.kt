package com.friend.ios

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.json.JSONObject

class DeviceDiagnosticsLifecyclePolicyTest {
    private fun exit(pid: Int = 2, timestamp: Long = 500, main: Boolean = true, reason: Int = 0) = JSONObject()
        .put("pid", pid).put("timestamp_ms", timestamp).put("main_process", main)
        .put("reason", reason).put("status", 0).put("importance", 100)

    @Test fun boundedExitHistoryDeduplicatesAndDoesNotInterpretUnknownReasonsAsCrashes() {
        val rows = (1..20).map { exit(timestamp = it.toLong(), reason = 9876) }
        val result = ProcessExitDiagnostics.collection(ExitCollectionOutcome.SUCCEEDED, 1000, rows + rows)
        assertEquals(10, result.getJSONArray("records").length())
        assertEquals(9876, result.getJSONArray("records").getJSONObject(0).getInt("reason"))
        assertFalse(result.toString().contains("description"))
        assertFalse(result.toString().contains("stack"))
    }

    @Test fun exitJoinRequiresMatchingMainProcessPidRunWindowAndIdentity() {
        val previous = JSONObject().put("pid", 2).put("started_at_ms", 100).put("identity_epoch", 7)
        val result = ProcessExitDiagnostics.collection(ExitCollectionOutcome.SUCCEEDED, 1000,
            listOf(exit(pid = 3), exit(main = false), exit(timestamp = 99), exit()))
        assertEquals(500, ProcessExitDiagnostics.matchPrevious(result, previous, 7, 1000)!!.getInt("timestamp_ms"))
        assertTrue(ProcessExitDiagnostics.matchPrevious(result, previous, 8, 1000) == null)
        assertTrue(ProcessExitDiagnostics.matchPrevious(result, JSONObject(), 7, 1000) == null)
        val ambiguous = ProcessExitDiagnostics.collection(ExitCollectionOutcome.SUCCEEDED, 1000, listOf(exit(), exit(timestamp = 600)))
        assertTrue(ProcessExitDiagnostics.matchPrevious(ambiguous, previous, 7, 1000) == null)
        for (outcome in ExitCollectionOutcome.entries.filter { it != ExitCollectionOutcome.SUCCEEDED }) {
            assertTrue(ProcessExitDiagnostics.matchPrevious(ProcessExitDiagnostics.collection(outcome, 1000), previous, 7, 1000) == null)
        }
        // Legacy unfinished-run events survive, including intentional closure in persistent mode.
        assertEquals(listOf("previous_run_unclean", "app_launch"), DeviceDiagnosticsLifecyclePolicy.processStartEvents(true))
    }

    @Test fun exitHistoryExpiresOldAndFutureRecords() {
        val result = ProcessExitDiagnostics.collection(ExitCollectionOutcome.SUCCEEDED, 1000,
            listOf(exit(timestamp = -8L * 24 * 3600 * 1000), exit(timestamp = 1001)))
        assertEquals(0, result.getJSONArray("records").length())
    }
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
