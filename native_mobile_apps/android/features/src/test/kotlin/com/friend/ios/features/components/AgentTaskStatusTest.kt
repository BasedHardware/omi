package com.friend.ios.features.components

import com.friend.ios.core.models.ActionItem
import com.friend.ios.core.models.Workstream
import com.friend.ios.features.components.AgentTaskStatus.Detail
import com.friend.ios.features.components.AgentTaskStatus.Kind
import com.friend.ios.service.stores.AgentStore
import com.friend.ios.service.stores.RunFailure
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Instant

/** `AgentTaskStatus(task:agent:)` (`AgentWording.swift`, iOS commit 63ce280): Omi's state on a task, in plain words. */
class AgentTaskStatusTest {
    private val now = Instant.parse("2026-10-08T15:00:00Z")
    private val task = ActionItem("t1", "Send Anna the Thursday follow-up", false, null, null, ActionItem.Owner.User, null, null)

    private fun run(state: AgentStore.RunState, steps: List<String> = emptyList()) =
        AgentStore.Run(id = "t1", taskTitle = task.description, state = state, steps = steps, partialText = "", startedAt = now)

    private fun event(summary: String, minutesAgo: Long) =
        Workstream.Event("e$minutesAgo", "agent_update", summary, now.minusSeconds(minutesAgo * 60))

    @Test
    fun noRunAndNoWorkstreamIsNoStatus() {
        assertNull(AgentTaskStatus.of(task, null, null, null))
    }

    @Test
    fun aWorkstreamNotLoadedYetStillSaysOmiHasIt() {
        val status = AgentTaskStatus.of(task.copy(workstreamID = "w1"), null, null, null)
        assertEquals(AgentTaskStatus(Kind.Working), status)
        assertFalse(status!!.isLive)
    }

    @Test
    fun aLiveRunShowsItsStepAndBreathes() {
        val status = AgentTaskStatus.of(task, null, run(AgentStore.RunState.Working("Checking your calendar")), null)!!
        assertEquals(Kind.Working, status.kind)
        assertEquals(Detail.Text("Checking your calendar"), status.detail)
        assertTrue(status.isLive)
        assertEquals(now, status.updatedAt)
    }

    @Test
    fun aHeartbeatStepFallsBackToTheLastRealStep() {
        val live = run(AgentStore.RunState.Working("Preparing response…"), steps = listOf("Searching your conversations", "Still working…"))
        assertEquals(Detail.Text("Searching your conversations"), AgentTaskStatus.of(task, null, live, null)!!.detail)
    }

    @Test
    fun aRecoveredRunIsNotLiveAndTakesItsTimeFromTheWorkstream() {
        val workstream = Workstream("w1", "a", Workstream.Status.Open, null, listOf(event(AgentStore.STARTED_SUMMARY, 6), event("Checking your calendar", 4)))
        val recovered = run(AgentStore.RunState.Working("Checking your calendar"))
        val status = AgentTaskStatus.of(task.copy(workstreamID = "w1"), workstream, null, recovered)!!
        assertFalse(status.isLive)
        assertEquals(now.minusSeconds(240), status.updatedAt)
    }

    @Test
    fun aKnownFailureReadsInPlainWords() {
        val status = AgentTaskStatus.of(task, null, run(AgentStore.RunState.Failed(RunFailure.ToolLoop.rawValue)), null)!!
        assertEquals(AgentTaskStatus(Kind.Failed, Detail.Failure(RunFailure.ToolLoop)), status)
    }

    @Test
    fun anUnknownFailureSaysWhereOmiStopped() {
        val failed = run(AgentStore.RunState.Failed(AgentStore.FAILED_SUMMARY), steps = listOf("Checking your calendar", "Preparing response…"))
        assertEquals(Detail.StoppedAt("Checking your calendar"), AgentTaskStatus.of(task, null, failed, null)!!.detail)
        // Free text from elsewhere stays as it is.
        val worded = run(AgentStore.RunState.Failed("The calendar refused the invite"))
        assertEquals(Detail.Text("The calendar refused the invite"), AgentTaskStatus.of(task, null, worded, null)!!.detail)
        // Nothing said: the short default.
        assertEquals(AgentTaskStatus(Kind.Failed), AgentTaskStatus.of(task, null, run(AgentStore.RunState.Failed(AgentStore.FAILED_SUMMARY)), null))
    }

    @Test
    fun aFinishedRunIsFinished() {
        assertEquals(Kind.Finished, AgentTaskStatus.of(task, null, run(AgentStore.RunState.Done("Drafted.")), null)!!.kind)
    }

    @Test
    fun onlyWorkShowsItsAge() {
        assertNull(AgentTaskStatus(Kind.Working, updatedAt = now.minusSeconds(10)).age(now))
        assertNull(AgentTaskStatus(Kind.Failed, updatedAt = now.minusSeconds(600)).age(now))
        assertNull(AgentTaskStatus(Kind.Working).age(now))
    }

    @Test
    fun boilerplateIsNeverAStep() {
        assertTrue(AgentWording.isBoilerplate(AgentStore.STARTED_SUMMARY))
        assertTrue(AgentWording.isBoilerplate("Preparing response…"))
        assertTrue(AgentWording.isBoilerplate("search_web"))
        assertTrue(AgentWording.isBoilerplate("Calling the calendar"))
        assertTrue(AgentWording.isBoilerplate(RunFailure.Timeout.eventSummary))
        assertEquals("Searching the web", AgentWording.step("Searching the web…"))
        assertNull(AgentWording.step("Still working…"))
    }
}
